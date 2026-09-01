import json
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from app.models import Machine, SensorReading, Anomaly, EnergyEvent
from app.schemas import SensorReadingCreate
from app.pipeline.telemetry_processor import TelemetryProcessor
from app.pipeline.event_manager import EventManager
from app.ml.model_manager import ModelManager
from app.ml.config import ANOMALY_THRESHOLD_LOW, ANOMALY_THRESHOLD_MEDIUM, ANOMALY_THRESHOLD_HIGH, CHANGE_DETECTION_INTERVAL
from app.energy.tariff import load_tariff
from app.energy.config import ENERGY_CHANGE_THRESHOLD, ENERGY_MIN_DURATION
from app.ml.baseline_manager import BaselineManager
from app.diagnosis.diagnosis_engine import DiagnosisEngine
from app.health.health_engine import HealthEngine

# Keep readings for rolling window
KEEP_READINGS_HOURS = 2
ENERGY_PERSISTENCE: Dict[str, Dict[str, Any]] = {}

class PipelineService:
    @classmethod
    def ingest_and_process(
        cls, 
        db: Session, 
        reading_in: SensorReadingCreate
    ) -> Tuple[SensorReading, Dict[str, Any]]:
        """
        Full end-to-end telemetry ingestion and intelligence pipeline:
        1. Validate telemetry against nominal ranges & verify machine
        2. Track operating state transitions -> Emit MACHINE_STATE_CHANGED event
        3. Store sensor reading in SQLite
        4. Run ML point anomaly inference -> Emit/Resolve ANOMALY_DETECTED event
        5. Run periodic behavioral drift detection -> Emit/Resolve BEHAVIOR_CHANGE event
        6. Run energy analysis -> Emit/Resolve ENERGY_INEFFICIENCY event
        7. Run diagnostic hypothesis engine -> Emit/Resolve DIAGNOSIS_AVAILABLE event
        8. Run machine health & priority triage -> Emit/Resolve HEALTH_CHANGED event
        9. Auto-prune old readings outside rolling retention window
        """
        # Step 1: Validate telemetry
        machine = TelemetryProcessor.validate_reading(db, reading_in)
        machine_id = machine.machine_id

        # Step 2: Check for machine state transition
        transition = TelemetryProcessor.check_state_transition(db, machine_id, reading_in.operating_state)
        if transition:
            prev_s, new_s = transition
            EventManager.create_or_update_event(
                db=db,
                machine_id=machine_id,
                event_type="MACHINE_STATE_CHANGED",
                severity="INFO",
                title=f"{machine_id} State Changed: {prev_s} → {new_s}",
                description=f"Machine transitioned operating state from {prev_s} to {new_s}.",
                evidence={"previous_state": prev_s, "new_state": new_s, "power_kw": reading_in.power}
            )

        # Step 3: Store raw reading
        db_reading = SensorReading(
            machine_id=machine_id,
            timestamp=reading_in.timestamp,
            voltage=reading_in.voltage,
            current=reading_in.current,
            power=reading_in.power,
            temperature=reading_in.temperature,
            vibration=reading_in.vibration,
            power_factor=reading_in.power_factor,
            operating_state=reading_in.operating_state
        )
        db.add(db_reading)
        db.commit()
        db.refresh(db_reading)

        # Step 4: ML Anomaly Detection
        anomaly_info = None
        if ModelManager.model_exists(machine_id):
            try:
                model_data = ModelManager.load_model(machine_id)
                detector = model_data["detector"]
                
                x = [
                    float(db_reading.voltage),
                    float(db_reading.current),
                    float(db_reading.power),
                    float(db_reading.temperature),
                    float(db_reading.vibration),
                    float(db_reading.power_factor)
                ]
                
                is_anomaly = detector.predict_single(x)
                score = detector.get_anomaly_score(x)
                deviations = detector.calculate_deviations(x)
                
                if not is_anomaly or score < ANOMALY_THRESHOLD_LOW:
                    severity = "NORMAL"
                elif score < ANOMALY_THRESHOLD_MEDIUM:
                    severity = "LOW"
                elif score < ANOMALY_THRESHOLD_HIGH:
                    severity = "MEDIUM"
                else:
                    severity = "HIGH"

                if severity != "NORMAL":
                    db_anomaly = Anomaly(
                        machine_id=machine_id,
                        reading_id=db_reading.id,
                        timestamp=db_reading.timestamp,
                        anomaly_score=score,
                        severity=severity,
                        affected_parameters=json.dumps(deviations)
                    )
                    db.add(db_anomaly)
                    db.commit()

                    EventManager.create_or_update_event(
                        db=db,
                        machine_id=machine_id,
                        event_type="ANOMALY_DETECTED",
                        severity=severity,
                        title=f"{machine_id} Anomaly Detected ({severity})",
                        description=f"Isolation Forest flagged telemetry with score {score:.2f} ({severity} severity).",
                        evidence={"score": score, "severity": severity, "deviations": deviations}
                    )
                else:
                    EventManager.resolve_active_event(db, machine_id, "ANOMALY_DETECTED")

                anomaly_info = {
                    "is_anomaly": severity != "NORMAL",
                    "anomaly_score": round(score, 2),
                    "severity": severity,
                    "parameter_deviations": deviations
                }
            except Exception as e:
                print(f"[Pipeline ML Error] Anomaly evaluation failed for {machine_id}: {e}")
                anomaly_info = {
                    "status": "error",
                    "reason": f"Anomaly detection failed: {e}"
                }
        else:
            anomaly_info = {
                "status": "not_available",
                "reason": "Machine model has not been trained"
            }

        # Step 5: Database auto-pruning
        try:
            cutoff = datetime.utcnow() - timedelta(hours=KEEP_READINGS_HOURS)
            db.query(SensorReading).filter(SensorReading.timestamp < cutoff).delete()
            db.commit()
        except Exception as e:
            print(f"[Pipeline Pruning Error] Cleanup failed: {e}")
            db.rollback()

        # Step 6: Periodic Behavioral Change Detection
        try:
            from app.routes.change_detection import analyze_machine_behavior
            machine_reading_count = db.query(SensorReading).filter(SensorReading.machine_id == machine_id).count()
            if machine_reading_count % CHANGE_DETECTION_INTERVAL == 0:
                active_changes = analyze_machine_behavior(machine_id=machine_id, db=db)
                if active_changes:
                    shifts_desc = ", ".join([f"{c.parameter} ({c.percentage_change:+.1f}%)" for c in active_changes])
                    EventManager.create_or_update_event(
                        db=db,
                        machine_id=machine_id,
                        event_type="BEHAVIOR_CHANGE",
                        severity="HIGH" if any(abs(c.percentage_change) >= 25 for c in active_changes) else "MEDIUM",
                        title=f"{machine_id} Behavioral Shift Detected",
                        description=f"Persistent parameter drift confirmed: {shifts_desc}.",
                        evidence={"shifts": [{"parameter": c.parameter, "baseline": c.baseline_value, "recent": c.recent_value, "change": c.percentage_change} for c in active_changes]}
                    )
                else:
                    EventManager.resolve_active_event(db, machine_id, "BEHAVIOR_CHANGE")
        except Exception as e:
            print(f"[Pipeline Change Error] Behavioral change analysis failed for {machine_id}: {e}")

        # Step 7: Energy Intelligence
        try:
            if db_reading.operating_state.upper() == "RUNNING":
                baseline_stats = BaselineManager.calculate_baseline_statistics(db, machine_id, machine.machine_type)
                if baseline_stats and "power" in baseline_stats:
                    expected_power = baseline_stats["power"]["mean"]
                    actual_power = db_reading.power

                    if expected_power > 0:
                        diff_pct = (actual_power - expected_power) / expected_power
                        now = db_reading.timestamp

                        if diff_pct >= ENERGY_CHANGE_THRESHOLD:
                            if machine_id not in ENERGY_PERSISTENCE:
                                ENERGY_PERSISTENCE[machine_id] = {
                                    "start_time": now,
                                    "last_time": now,
                                    "total_excess_energy": 0.0
                                }
                            else:
                                state = ENERGY_PERSISTENCE[machine_id]
                                dt_hours = (now - state["last_time"]).total_seconds() / 3600.0
                                if dt_hours > 0:
                                    excess_power_kw = actual_power - expected_power
                                    state["total_excess_energy"] += excess_power_kw * dt_hours
                                state["last_time"] = now

                                duration_secs = (now - state["start_time"]).total_seconds()
                                if duration_secs >= ENERGY_MIN_DURATION:
                                    tariff = load_tariff()
                                    excess_kwh = state["total_excess_energy"]
                                    excess_cost = excess_kwh * tariff
                                    excess_power_kw = actual_power - expected_power

                                    active_energy_event = db.query(EnergyEvent)\
                                        .filter(EnergyEvent.machine_id == machine_id)\
                                        .filter(EnergyEvent.status == "ACTIVE")\
                                        .first()

                                    if not active_energy_event:
                                        active_energy_event = EnergyEvent(
                                            machine_id=machine_id,
                                            detected_at=now,
                                            expected_power=round(expected_power, 2),
                                            actual_power=round(actual_power, 2),
                                            excess_power=round(excess_power_kw, 2),
                                            excess_energy_kwh=round(excess_kwh, 2),
                                            estimated_cost=round(excess_cost, 2),
                                            status="ACTIVE"
                                        )
                                        db.add(active_energy_event)
                                    else:
                                        active_energy_event.actual_power = round(actual_power, 2)
                                        active_energy_event.excess_power = round(excess_power_kw, 2)
                                        active_energy_event.excess_energy_kwh = round(excess_kwh, 2)
                                        active_energy_event.estimated_cost = round(excess_cost, 2)
                                    db.commit()

                                    EventManager.create_or_update_event(
                                        db=db,
                                        machine_id=machine_id,
                                        event_type="ENERGY_INEFFICIENCY",
                                        severity="MEDIUM",
                                        title=f"{machine_id} Energy Inefficiency Detected",
                                        description=f"Power draw {actual_power:.2f}kW is +{(diff_pct*100):.1f}% above expected baseline ({expected_power:.2f}kW). Excess cost: ₹{excess_cost:.2f}.",
                                        evidence={
                                            "expected_power_kw": expected_power,
                                            "actual_power_kw": actual_power,
                                            "excess_kwh": excess_kwh,
                                            "estimated_cost": excess_cost
                                        }
                                    )
                        else:
                            if machine_id in ENERGY_PERSISTENCE:
                                del ENERGY_PERSISTENCE[machine_id]
                            active_event = db.query(EnergyEvent).filter(EnergyEvent.machine_id == machine_id, EnergyEvent.status == "ACTIVE").first()
                            if active_event:
                                active_event.status = "RESOLVED"
                                db.commit()
                            EventManager.resolve_active_event(db, machine_id, "ENERGY_INEFFICIENCY")
        except Exception as e:
            print(f"[Pipeline Energy Error] Energy intelligence analysis failed for {machine_id}: {e}")

        # Step 8: AI-Assisted Fault Diagnosis
        try:
            diag_res = DiagnosisEngine.analyze_machine(db, machine_id)
            if diag_res and diag_res.primary_cause and diag_res.primary_cause != "UNKNOWN" and diag_res.evidence_score and diag_res.evidence_score >= 0.35:
                cause_str = diag_res.primary_cause.replace("_", " ").title()
                score_pct = int(diag_res.evidence_score * 100)
                EventManager.create_or_update_event(
                    db=db,
                    machine_id=machine_id,
                    event_type="DIAGNOSIS_AVAILABLE",
                    severity="HIGH",
                    title=f"{machine_id} Possible {cause_str} ({score_pct}% Match)",
                    description=diag_res.explanation,
                    evidence={"primary_cause": diag_res.primary_cause, "score": diag_res.evidence_score}
                )
            else:
                EventManager.resolve_active_event(db, machine_id, "DIAGNOSIS_AVAILABLE")
        except Exception as e:
            print(f"[Pipeline Diagnosis Error] Fault diagnosis failed for {machine_id}: {e}")

        # Step 9: Machine Health & Priority Evaluation
        try:
            health_res = HealthEngine.evaluate_machine(db, machine_id)
            if health_res and health_res.health_status != "HEALTHY":
                sev_map = {"CRITICAL": "CRITICAL", "ATTENTION": "HIGH", "WATCH": "MEDIUM", "HEALTHY": "INFO"}
                EventManager.create_or_update_event(
                    db=db,
                    machine_id=machine_id,
                    event_type="HEALTH_CHANGED",
                    severity=sev_map.get(health_res.health_status, "INFO"),
                    title=f"{machine_id} Health Alert: {health_res.health_status} (Priority: {health_res.priority_score}/100)",
                    description=health_res.primary_reason,
                    evidence={
                        "health_status": health_res.health_status,
                        "priority_score": health_res.priority_score,
                        "primary_reason": health_res.primary_reason
                    }
                )
            else:
                EventManager.resolve_active_event(db, machine_id, "HEALTH_CHANGED")
        except Exception as e:
            print(f"[Pipeline Health Error] Health evaluation failed for {machine_id}: {e}")

        return db_reading, anomaly_info
