from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session

from app.models import (
    Machine,
    SensorReading,
    Anomaly,
    BehaviorChange,
    EnergyEvent,
    DiagnosisEvent,
    MachineHealthEvent
)
from app.ml.baseline_manager import BaselineManager
from app.energy.energy_analyzer import EnergyAnalyzer
from app.energy.tariff import load_tariff
from app.diagnosis.diagnosis_engine import DiagnosisEngine
from app.health.health_engine import HealthEngine

class QueryEngine:
    @classmethod
    def get_machine(cls, db: Session, machine_id: str) -> Optional[Machine]:
        return db.query(Machine).filter(Machine.machine_id == machine_id.upper()).first()

    @classmethod
    def get_all_machines(cls, db: Session) -> List[Machine]:
        return db.query(Machine).all()

    @classmethod
    def get_latest_reading(cls, db: Session, machine_id: str) -> Optional[SensorReading]:
        return db.query(SensorReading)\
            .filter(SensorReading.machine_id == machine_id.upper())\
            .order_by(SensorReading.timestamp.desc())\
            .first()

    @classmethod
    def get_latest_anomaly(cls, db: Session, machine_id: str) -> Optional[Anomaly]:
        return db.query(Anomaly)\
            .filter(Anomaly.machine_id == machine_id.upper())\
            .order_by(Anomaly.timestamp.desc())\
            .first()

    @classmethod
    def get_all_recent_anomalies(cls, db: Session) -> List[Anomaly]:
        machines = cls.get_all_machines(db)
        anomalies = []
        for m in machines:
            latest = cls.get_latest_anomaly(db, m.machine_id)
            if latest and latest.severity != "NORMAL":
                anomalies.append(latest)
        return anomalies

    @classmethod
    def get_active_behavior_changes(cls, db: Session, machine_id: str) -> List[BehaviorChange]:
        return db.query(BehaviorChange)\
            .filter(BehaviorChange.machine_id == machine_id.upper())\
            .filter(BehaviorChange.status == "ACTIVE")\
            .all()

    @classmethod
    def get_all_active_behavior_changes(cls, db: Session) -> List[BehaviorChange]:
        return db.query(BehaviorChange)\
            .filter(BehaviorChange.status == "ACTIVE")\
            .all()

    @classmethod
    def get_active_energy_event(cls, db: Session, machine_id: str) -> Optional[EnergyEvent]:
        return db.query(EnergyEvent)\
            .filter(EnergyEvent.machine_id == machine_id.upper())\
            .filter(EnergyEvent.status == "ACTIVE")\
            .first()

    @classmethod
    def get_factory_energy_overview(cls, db: Session, hours: int = 24) -> Any:
        try:
            machines = db.query(Machine).all()
            total_actual = 0.0
            total_expected = 0.0
            total_excess = 0.0
            tariff = load_tariff()
            cutoff = datetime.utcnow() - timedelta(hours=hours)

            class MachineEnergyItem:
                def __init__(self, machine_id, actual_power, excess_energy_kwh, estimated_cost):
                    self.machine_id = machine_id
                    self.actual_power = actual_power
                    self.excess_energy_kwh = excess_energy_kwh
                    self.estimated_cost = estimated_cost

            items = []
            for m in machines:
                stats = BaselineManager.calculate_baseline_statistics(db, m.machine_id, m.machine_type)
                baseline_power = stats["power"]["mean"] if (stats and "power" in stats) else 0.0

                readings = db.query(SensorReading)\
                    .filter(SensorReading.machine_id == m.machine_id)\
                    .filter(SensorReading.timestamp >= cutoff)\
                    .all()

                metrics = EnergyAnalyzer.calculate_window_energy(readings, baseline_power)
                total_actual += metrics["actual_kwh"]
                total_expected += metrics["expected_kwh"]
                total_excess += metrics["excess_kwh"]

                latest_r = cls.get_latest_reading(db, m.machine_id)
                curr_pwr = latest_r.power if latest_r else (stats["power"]["mean"] if stats and "power" in stats else 0.0)
                m_cost = metrics["excess_kwh"] * tariff

                items.append(MachineEnergyItem(m.machine_id, curr_pwr, metrics["excess_kwh"], m_cost))

            class FactoryEnergyOverview:
                def __init__(self, actual, expected, excess, cost, machines_list):
                    self.total_energy_kwh = actual
                    self.expected_energy_kwh = expected
                    self.excess_energy_kwh = excess
                    self.estimated_excess_cost = cost
                    self.machines = machines_list

            return FactoryEnergyOverview(total_actual, total_expected, total_excess, total_excess * tariff, items)
        except Exception as e:
            print(f"[QueryEngine] Energy overview retrieval failed: {e}")
            return None

    @classmethod
    def get_machine_energy_summary(cls, db: Session, machine_id: str, hours: int = 24) -> Any:
        try:
            m = cls.get_machine(db, machine_id)
            if not m:
                return None
            stats = BaselineManager.calculate_baseline_statistics(db, m.machine_id, m.machine_type)
            baseline_power = stats["power"]["mean"] if (stats and "power" in stats) else 0.0
            cutoff = datetime.utcnow() - timedelta(hours=hours)

            readings = db.query(SensorReading)\
                .filter(SensorReading.machine_id == m.machine_id)\
                .filter(SensorReading.timestamp >= cutoff)\
                .all()

            metrics = EnergyAnalyzer.calculate_window_energy(readings, baseline_power)
            tariff = load_tariff()

            class MachineEnergySummary:
                def __init__(self, base_pwr, actual_kwh, excess_kwh, cost):
                    self.energy_status = "INEFFICIENT" if excess_kwh > 0 else "NORMAL"
                    self.baseline_power_kw = base_pwr
                    self.recent_avg_power_kw = (actual_kwh / hours) if hours > 0 else base_pwr
                    self.total_excess_energy_kwh = excess_kwh
                    self.total_excess_cost = cost

            return MachineEnergySummary(baseline_power, metrics["actual_kwh"], metrics["excess_kwh"], metrics["excess_kwh"] * tariff)
        except Exception as e:
            print(f"[QueryEngine] Machine energy summary retrieval failed: {e}")
            return None

    @classmethod
    def get_active_diagnosis(cls, db: Session, machine_id: str) -> Optional[DiagnosisEvent]:
        return db.query(DiagnosisEvent)\
            .filter(DiagnosisEvent.machine_id == machine_id.upper())\
            .filter(DiagnosisEvent.status == "ACTIVE")\
            .first()

    @classmethod
    def get_machine_health(cls, db: Session, machine_id: str) -> Any:
        try:
            return HealthEngine.evaluate_machine(db, machine_id.upper())
        except Exception as e:
            print(f"[QueryEngine] Machine health retrieval failed: {e}")
            return None

    @classmethod
    def get_factory_health_overview(cls, db: Session) -> Any:
        try:
            return HealthEngine.get_factory_overview(db)
        except Exception as e:
            print(f"[QueryEngine] Factory health overview retrieval failed: {e}")
            return None

    @classmethod
    def get_baseline_statistics(cls, db: Session, machine_id: str, machine_type: str) -> Optional[Dict[str, Any]]:
        try:
            return BaselineManager.calculate_baseline_statistics(db, machine_id.upper(), machine_type)
        except Exception as e:
            print(f"[QueryEngine] Baseline calculation failed: {e}")
            return None
