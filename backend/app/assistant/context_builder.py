from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session

from app.assistant.query_engine import QueryEngine
from app.assistant.schemas import AssistantEvidenceItem

class ContextBuilder:
    @classmethod
    def build_machine_context(cls, db: Session, machine_id: str) -> Dict[str, Any]:
        """
        Gathers strictly verified machine telemetry, baseline stats, active anomalies,
        behavioral shifts, energy waste, diagnostic hypotheses, and priority score.
        """
        machine_id_upper = machine_id.upper()
        machine = QueryEngine.get_machine(db, machine_id_upper)
        if not machine:
            return {"exists": False, "machine_id": machine_id_upper}

        reading = QueryEngine.get_latest_reading(db, machine_id_upper)
        anomaly = QueryEngine.get_latest_anomaly(db, machine_id_upper)
        changes = QueryEngine.get_active_behavior_changes(db, machine_id_upper)
        energy_event = QueryEngine.get_active_energy_event(db, machine_id_upper)
        energy_summary = QueryEngine.get_machine_energy_summary(db, machine_id_upper)
        diagnosis = QueryEngine.get_active_diagnosis(db, machine_id_upper)
        health = QueryEngine.get_machine_health(db, machine_id_upper)
        baseline = QueryEngine.get_baseline_statistics(db, machine_id_upper, machine.machine_type)

        context: Dict[str, Any] = {
            "exists": True,
            "machine": {
                "id": machine.machine_id,
                "name": machine.machine_name,
                "type": machine.machine_type,
                "location": machine.location
            },
            "reading": None,
            "baseline": baseline,
            "anomaly": None,
            "behavior_changes": [],
            "energy": None,
            "diagnosis": None,
            "health": None,
            "evidence_items": []
        }

        # Telemetry
        if reading:
            context["reading"] = {
                "timestamp": reading.timestamp.isoformat(),
                "state": reading.operating_state,
                "power": reading.power,
                "temperature": reading.temperature,
                "vibration": reading.vibration,
                "current": reading.current,
                "voltage": reading.voltage,
                "power_factor": reading.power_factor
            }

        # Anomaly
        if anomaly and anomaly.severity != "NORMAL":
            context["anomaly"] = {
                "severity": anomaly.severity,
                "score": anomaly.anomaly_score,
                "timestamp": anomaly.timestamp.isoformat()
            }
            context["evidence_items"].append(AssistantEvidenceItem(
                parameter="Anomaly Detection",
                current=anomaly.anomaly_score,
                variance=anomaly.severity,
                note=f"Point anomaly flagged with {anomaly.severity} severity (Score: {anomaly.anomaly_score:.2f})"
            ))

        # Behavior Changes
        if changes:
            context["behavior_changes"] = [
                {
                    "parameter": c.parameter,
                    "magnitude_pct": c.percentage_change,
                    "direction": c.change_type,
                    "persistence_count": c.persistence_count,
                    "detected_at": c.detected_at.isoformat()
                }
                for c in changes
            ]
            for c in changes:
                context["evidence_items"].append(AssistantEvidenceItem(
                    parameter=c.parameter.title(),
                    baseline=c.baseline_value,
                    current=c.recent_value,
                    variance=f"{c.percentage_change:+.1f}%",
                    note=f"Persistent {c.change_type.lower()} shift ({c.percentage_change:+.1f}% vs baseline)"
                ))

        # Energy
        if energy_event:
            context["energy"] = {
                "status": "INEFFICIENT",
                "expected_power": energy_event.expected_power,
                "actual_power": energy_event.actual_power,
                "excess_power": energy_event.excess_power,
                "excess_energy_kwh": energy_event.excess_energy_kwh,
                "estimated_cost": energy_event.estimated_cost
            }
            context["evidence_items"].append(AssistantEvidenceItem(
                parameter="Energy Consumption",
                baseline=energy_event.expected_power,
                current=energy_event.actual_power,
                variance=f"+{energy_event.excess_power:.2f} kW",
                note=f"Excess power draw of +{energy_event.excess_power:.2f} kW generating ₹{energy_event.estimated_cost:.2f} estimated waste"
            ))
        elif energy_summary:
            context["energy"] = {
                "status": energy_summary.energy_status,
                "baseline_power_kw": energy_summary.baseline_power_kw,
                "recent_avg_power_kw": energy_summary.recent_avg_power_kw,
                "excess_energy_kwh": energy_summary.total_excess_energy_kwh,
                "estimated_cost": energy_summary.total_excess_cost
            }

        # Diagnosis
        if diagnosis:
            cause_readable = diagnosis.primary_possible_cause.replace("_", " ").title()
            context["diagnosis"] = {
                "status": "DIAGNOSIS_AVAILABLE",
                "primary_cause": diagnosis.primary_possible_cause,
                "evidence_score": diagnosis.evidence_score,
                "explanation": diagnosis.explanation
            }
            context["evidence_items"].append(AssistantEvidenceItem(
                parameter="Fault Diagnosis",
                current=diagnosis.evidence_score,
                variance=f"{int(diagnosis.evidence_score * 100)}% Match",
                note=f"Telemetry matches possible {cause_readable} signature (Score: {int(diagnosis.evidence_score * 100)}%)"
            ))

        # Health
        if health:
            context["health"] = {
                "status": health.health_status,
                "priority_score": health.priority_score,
                "primary_reason": health.primary_reason,
                "operator_status": health.operator_status
            }

        # Parameter deviations vs baseline
        if baseline and reading:
            for param in ["power", "temperature", "vibration", "current"]:
                if param in baseline and hasattr(reading, param):
                    b_mean = baseline[param]["mean"]
                    val = getattr(reading, param)
                    if b_mean > 0:
                        pct = ((val - b_mean) / b_mean) * 100.0
                        if abs(pct) >= 15.0:
                            # Check if not already added in behavior changes
                            if not any(e.parameter.lower() == param for e in context["evidence_items"]):
                                context["evidence_items"].append(AssistantEvidenceItem(
                                    parameter=param.title(),
                                    baseline=round(b_mean, 3),
                                    current=round(val, 3),
                                    variance=f"{pct:+.1f}%",
                                    note=f"{param.title()} is {pct:+.1f}% compared to normal baseline mean ({b_mean:.2f})"
                                ))

        return context

    @classmethod
    def build_factory_context(cls, db: Session) -> Dict[str, Any]:
        """Gathers factory-wide overview context across all registered machines."""
        health_ov = QueryEngine.get_factory_health_overview(db)
        energy_ov = QueryEngine.get_factory_energy_overview(db)
        anomalies = QueryEngine.get_all_recent_anomalies(db)
        changes = QueryEngine.get_all_active_behavior_changes(db)

        return {
            "health_overview": health_ov,
            "energy_overview": energy_ov,
            "active_anomalies_count": len(anomalies),
            "active_changes_count": len(changes)
        }
