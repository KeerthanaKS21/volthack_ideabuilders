import json
from datetime import datetime
from typing import Dict, List, Any, Optional
from sqlalchemy.orm import Session

from app.models import Machine, SensorReading, Anomaly, BehaviorChange, EnergyEvent, DiagnosisEvent, MachineHealthEvent
from app.ml.baseline_manager import BaselineManager
from app.health.priority_engine import PriorityEngine
from app.health.health_schemas import MachineHealthResponse, HealthOverviewResponse, HealthOverviewItem, SignalScoreItem

# In-memory persistence tracker for consecutive abnormal states per machine
HEALTH_PERSISTENCE: Dict[str, int] = {}

class HealthEngine:
    @classmethod
    def evaluate_machine(cls, db: Session, machine_id: str) -> MachineHealthResponse:
        """
        Gathers multi-engine intelligence for a machine, computes health & priority,
        updates database events without duplication, and returns structured response.
        """
        machine_id_upper = machine_id.upper()
        machine = db.query(Machine).filter(Machine.machine_id == machine_id_upper).first()
        if not machine:
            raise ValueError(f"Machine '{machine_id}' not found.")

        # 1. Fetch latest reading
        latest_reading = db.query(SensorReading)\
            .filter(SensorReading.machine_id == machine_id_upper)\
            .order_by(SensorReading.timestamp.desc())\
            .first()

        # 2. Fetch recent anomalies (within last 10 readings) to evaluate active condition
        recent_anomalies = db.query(Anomaly)\
            .filter(Anomaly.machine_id == machine_id_upper)\
            .order_by(Anomaly.timestamp.desc())\
            .limit(10)\
            .all()

        anomaly_info = {}
        if recent_anomalies:
            severity_order = {"HIGH": 3, "MEDIUM": 2, "LOW": 1, "NORMAL": 0}
            worst_anomaly = max(recent_anomalies, key=lambda a: severity_order.get(a.severity, 0))
            is_anomaly = worst_anomaly.severity != "NORMAL"
            anomaly_info = {
                "is_anomaly": is_anomaly,
                "severity": worst_anomaly.severity,
                "anomaly_score": worst_anomaly.anomaly_score
            }

        # 3. Fetch active behavioral changes
        active_changes = db.query(BehaviorChange)\
            .filter(BehaviorChange.machine_id == machine_id_upper)\
            .filter(BehaviorChange.status == "ACTIVE")\
            .all()

        behavior_changes_list = [
            {
                "parameter": c.parameter,
                "magnitude_pct": c.percentage_change,
                "z_score": c.change_score,
                "direction": c.change_type
            }
            for c in active_changes
        ]

        # 4. Fetch active energy events
        active_energy = db.query(EnergyEvent)\
            .filter(EnergyEvent.machine_id == machine_id_upper)\
            .filter(EnergyEvent.status == "ACTIVE")\
            .first()

        energy_info = {}
        if active_energy:
            base_pwr = active_energy.expected_power if active_energy.expected_power > 0 else 1.0
            excess_pct = (active_energy.excess_power / base_pwr) * 100.0
            energy_info = {
                "energy_status": "INEFFICIENT" if excess_pct >= 20.0 else "ELEVATED",
                "difference_percentage": excess_pct,
                "excess_power": active_energy.excess_power
            }
        else:
            # Check if current reading has elevated power
            stats = BaselineManager.calculate_baseline_statistics(db, machine_id_upper, machine.machine_type)
            if stats and "power" in stats and latest_reading and latest_reading.operating_state == "RUNNING":
                base_pwr = stats["power"]["mean"]
                if base_pwr > 0 and latest_reading.power >= base_pwr * 1.10:
                    diff_pct = ((latest_reading.power - base_pwr) / base_pwr) * 100.0
                    energy_info = {
                        "energy_status": "INEFFICIENT" if diff_pct >= 20.0 else "ELEVATED",
                        "difference_percentage": diff_pct,
                        "excess_power": latest_reading.power - base_pwr
                    }

        # 5. Fetch active diagnosis event
        active_diagnosis = db.query(DiagnosisEvent)\
            .filter(DiagnosisEvent.machine_id == machine_id_upper)\
            .filter(DiagnosisEvent.status == "ACTIVE")\
            .first()

        diagnosis_info = {}
        if active_diagnosis:
            diagnosis_info = {
                "status": "DIAGNOSIS_AVAILABLE",
                "primary_cause": active_diagnosis.primary_possible_cause,
                "evidence_score": active_diagnosis.evidence_score
            }

        # 6. Calculate parameter deviations vs baseline
        param_deviations: Dict[str, float] = {}
        stats = BaselineManager.calculate_baseline_statistics(db, machine_id_upper, machine.machine_type)
        if stats and latest_reading:
            for param in ["vibration", "power", "temperature", "current"]:
                if param in stats:
                    base_val = stats[param]["mean"]
                    curr_val = getattr(latest_reading, param)
                    if base_val > 0:
                        param_deviations[param] = ((curr_val - base_val) / base_val) * 100.0

        # 7. Update and evaluate persistence
        has_abnormal_signal = bool(
            (anomaly_info and anomaly_info.get("is_anomaly")) or
            (len(behavior_changes_list) > 0) or
            (energy_info and energy_info.get("energy_status") in ["ELEVATED", "INEFFICIENT"]) or
            (diagnosis_info and diagnosis_info.get("status") == "DIAGNOSIS_AVAILABLE")
        )

        current_persistence = HEALTH_PERSISTENCE.get(machine_id_upper, 0)
        if has_abnormal_signal:
            current_persistence += 1
        else:
            current_persistence = max(0, current_persistence - 1)
        HEALTH_PERSISTENCE[machine_id_upper] = current_persistence

        # 8. Compute Priority and Health Status
        priority_score, health_status, primary_reason, contributing_factors, active_issues, signals = PriorityEngine.evaluate(
            anomaly_info=anomaly_info,
            behavior_changes=behavior_changes_list,
            energy_info=energy_info,
            diagnosis_info=diagnosis_info,
            persistence_count=current_persistence,
            param_deviations=param_deviations
        )

        # 9. Manage Database Health Events & Operator Status
        active_event = db.query(MachineHealthEvent)\
            .filter(MachineHealthEvent.machine_id == machine_id_upper)\
            .filter(MachineHealthEvent.status == "ACTIVE")\
            .first()

        operator_status = "INVESTIGATE"
        event_id = None

        if health_status == "HEALTHY":
            if active_event:
                active_event.status = "RESOLVED"
                db.commit()
        else:
            factors_json = json.dumps(contributing_factors)
            signals_json = json.dumps({k: v.dict() for k, v in signals.items()})

            if active_event:
                active_event.health_status = health_status
                active_event.priority_score = priority_score
                active_event.primary_reason = primary_reason
                active_event.contributing_factors_json = factors_json
                active_event.signal_scores_json = signals_json
                active_event.timestamp = datetime.utcnow()
                db.commit()
                operator_status = active_event.operator_status
                event_id = active_event.id
            else:
                new_event = MachineHealthEvent(
                    machine_id=machine_id_upper,
                    timestamp=datetime.utcnow(),
                    health_status=health_status,
                    priority_score=priority_score,
                    primary_reason=primary_reason,
                    contributing_factors_json=factors_json,
                    signal_scores_json=signals_json,
                    operator_status="INVESTIGATE",
                    status="ACTIVE"
                )
                db.add(new_event)
                db.commit()
                db.refresh(new_event)
                operator_status = new_event.operator_status
                event_id = new_event.id

        return MachineHealthResponse(
            machine_id=machine_id_upper,
            machine_type=machine.machine_type,
            health_status=health_status,
            priority_score=priority_score,
            primary_reason=primary_reason,
            contributing_factors=contributing_factors,
            signals=signals,
            active_issues=active_issues,
            operator_status=operator_status,
            event_id=event_id,
            timestamp=datetime.utcnow()
        )

    @classmethod
    def get_factory_overview(cls, db: Session) -> HealthOverviewResponse:
        """
        Evaluates all registered machines, aggregates factory counts, and
        ranks machines by priority score in descending order.
        """
        machines = db.query(Machine).all()
        items: List[HealthOverviewItem] = []

        healthy_count = 0
        watch_count = 0
        attention_count = 0
        critical_count = 0

        for machine in machines:
            try:
                res = cls.evaluate_machine(db, machine.machine_id)
                status = res.health_status
                if status == "HEALTHY":
                    healthy_count += 1
                elif status == "WATCH":
                    watch_count += 1
                elif status == "ATTENTION":
                    attention_count += 1
                elif status == "CRITICAL":
                    critical_count += 1

                items.append(HealthOverviewItem(
                    machine_id=machine.machine_id,
                    machine_name=machine.machine_name,
                    machine_type=machine.machine_type,
                    location=machine.location,
                    health_status=res.health_status,
                    priority_score=res.priority_score,
                    primary_reason=res.primary_reason,
                    operator_status=res.operator_status,
                    active_issues_count=len(res.active_issues)
                ))
            except Exception as e:
                print(f"[Health Overview Error] Failed evaluating machine {machine.machine_id}: {e}")

        # Sort ranked list descending by priority score
        items.sort(key=lambda x: x.priority_score, reverse=True)

        top_priority = items[0].machine_id if items and items[0].priority_score > 0 else None

        return HealthOverviewResponse(
            total_machines=len(machines),
            healthy_count=healthy_count,
            watch_count=watch_count,
            attention_count=attention_count,
            critical_count=critical_count,
            top_priority_machine=top_priority,
            machines=items,
            ranked_machines=items
        )
