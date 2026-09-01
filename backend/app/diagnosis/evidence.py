from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from app.models import Machine, SensorReading, Anomaly, BehaviorChange, EnergyEvent
from app.ml.baseline_manager import BaselineManager
from app.ml.config import PERSISTENCE_THRESHOLD, MIN_TRAINING_SAMPLES
from app.diagnosis.schemas import EvidenceItem

class EvidenceBundle:
    def __init__(self, machine_id: str, machine_type: str, operating_state: str, has_baseline: bool):
        self.machine_id = machine_id
        self.machine_type = machine_type
        self.operating_state = operating_state
        self.has_baseline = has_baseline
        self.items: List[EvidenceItem] = []
        self.param_deviations: Dict[str, float] = {}
        self.active_behavior_changes: List[str] = []
        self.is_anomaly: bool = False
        self.anomaly_severity: str = "NORMAL"
        self.anomaly_score: float = 0.0
        self.is_energy_inefficient: bool = False
        self.excess_power: float = 0.0

    def add_item(self, item: EvidenceItem):
        self.items.append(item)


class EvidenceCollector:
    @classmethod
    def gather_evidence(cls, db: Session, machine_id: str) -> Optional[EvidenceBundle]:
        """
        Gather all verified telemetry, baseline deviations, anomaly statuses,
        behavior changes, and energy metrics into a single traceable EvidenceBundle.
        """
        machine_id_upper = machine_id.upper()
        machine = db.query(Machine).filter(Machine.machine_id == machine_id_upper).first()
        if not machine:
            return None

        # 1. Fetch latest reading
        latest_reading = db.query(SensorReading)\
            .filter(SensorReading.machine_id == machine_id_upper)\
            .order_by(SensorReading.timestamp.desc())\
            .first()

        if not latest_reading:
            return None

        operating_state = latest_reading.operating_state

        # 2. Fetch baseline statistics
        stats = BaselineManager.calculate_baseline_statistics(db, machine_id_upper, machine.machine_type)
        has_baseline = bool(stats and "power" in stats and stats["power"]["count"] >= MIN_TRAINING_SAMPLES)

        bundle = EvidenceBundle(
            machine_id=machine_id_upper,
            machine_type=machine.machine_type,
            operating_state=operating_state,
            has_baseline=has_baseline
        )

        # 3. Parameter baseline comparisons (only if baseline exists)
        if stats and has_baseline:
            params = ["vibration", "power", "temperature", "current", "voltage", "power_factor"]
            for param in params:
                if param not in stats:
                    continue
                curr = float(getattr(latest_reading, param))
                base = float(stats[param]["mean"])
                
                pct = ((curr - base) / base * 100.0) if base > 0 else 0.0
                bundle.param_deviations[param] = pct

                severity = "NORMAL"
                if param == "vibration":
                    if pct >= 100.0: severity = "CRITICAL"
                    elif pct >= 50.0: severity = "HIGH"
                    elif pct >= 20.0: severity = "MODERATE"
                    elif pct >= 10.0: severity = "LOW"
                elif param == "temperature":
                    if pct >= 40.0: severity = "CRITICAL"
                    elif pct >= 20.0: severity = "HIGH"
                    elif pct >= 10.0: severity = "MODERATE"
                    elif pct >= 5.0: severity = "LOW"
                elif param in ["power", "current"]:
                    if pct >= 40.0: severity = "CRITICAL"
                    elif pct >= 20.0: severity = "HIGH"
                    elif pct >= 10.0: severity = "MODERATE"
                    elif pct >= 5.0: severity = "LOW"
                elif param == "voltage":
                    abs_pct = abs(pct)
                    if abs_pct >= 10.0: severity = "HIGH"
                    elif abs_pct >= 5.0: severity = "MODERATE"
                elif param == "power_factor":
                    if pct <= -20.0 or curr < 0.75: severity = "HIGH"
                    elif pct <= -10.0 or curr < 0.85: severity = "MODERATE"

                # Always add evidence item for non-normal or significant readings
                sign = "+" if pct >= 0 else ""
                bundle.add_item(EvidenceItem(
                    parameter=param,
                    baseline=round(base, 2),
                    current=round(curr, 2),
                    change_percent=round(pct, 1),
                    severity=severity,
                    source="sensor_reading",
                    description=f"{param.replace('_', ' ').capitalize()} is {sign}{pct:.1f}% relative to baseline ({curr:.2f} vs {base:.2f})"
                ))

        # 4. Check Anomaly Detection (Phase 4)
        latest_anomaly = db.query(Anomaly)\
            .filter(Anomaly.machine_id == machine_id_upper)\
            .order_by(Anomaly.timestamp.desc())\
            .first()

        if latest_anomaly and latest_anomaly.severity != "NORMAL":
            bundle.is_anomaly = True
            bundle.anomaly_severity = latest_anomaly.severity
            bundle.anomaly_score = latest_anomaly.anomaly_score
            bundle.add_item(EvidenceItem(
                parameter="anomaly_detection",
                current=round(latest_anomaly.anomaly_score, 2),
                severity=latest_anomaly.severity,
                source="anomaly_detection",
                description=f"Isolation Forest flagged an anomaly with score {latest_anomaly.anomaly_score:.2f} ({latest_anomaly.severity} severity)"
            ))

        # 5. Check Behavioral Changes (Phase 5)
        active_changes = db.query(BehaviorChange)\
            .filter(BehaviorChange.machine_id == machine_id_upper)\
            .filter(BehaviorChange.status == "ACTIVE")\
            .filter(BehaviorChange.persistence_count >= PERSISTENCE_THRESHOLD)\
            .all()

        for c in active_changes:
            bundle.active_behavior_changes.append(c.parameter)
            bundle.add_item(EvidenceItem(
                parameter=f"behavior_{c.parameter}",
                baseline=round(c.baseline_value, 2),
                current=round(c.recent_value, 2),
                change_percent=round(c.percentage_change, 1),
                severity="HIGH" if c.persistence_count >= 5 else "MODERATE",
                source="behavioral_change",
                description=f"Persistent {c.change_type.lower().replace('_', ' ')} in {c.parameter} ({c.percentage_change:+.1f}%, persisted {c.persistence_count} cycles)"
            ))

        # 6. Check Energy Inefficiency (Phase 6)
        active_energy_event = db.query(EnergyEvent)\
            .filter(EnergyEvent.machine_id == machine_id_upper)\
            .filter(EnergyEvent.status == "ACTIVE")\
            .first()

        if active_energy_event:
            bundle.is_energy_inefficient = True
            bundle.excess_power = active_energy_event.excess_power
            bundle.add_item(EvidenceItem(
                parameter="energy_inefficiency",
                current=round(active_energy_event.excess_power, 2),
                severity="HIGH" if active_energy_event.excess_energy_kwh > 5.0 else "MODERATE",
                source="energy_intelligence",
                description=f"Persistent excess power draw of {active_energy_event.excess_power:.2f} kW (accumulated {active_energy_event.excess_energy_kwh:.2f} kWh waste, cost: ₹{active_energy_event.estimated_cost:.2f})"
            ))

        return bundle
