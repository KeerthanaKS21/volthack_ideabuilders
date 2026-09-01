import unittest
import json
import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.models import Machine, SensorReading, Anomaly, BehaviorChange, EnergyEvent, DiagnosisEvent, MachineHealthEvent
from app.main import app
from app.health.health_engine import HealthEngine, HEALTH_PERSISTENCE
from app.health.priority_engine import PriorityEngine

# In-memory SQLite with StaticPool so all connections and threads share the same test DB
engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

class TestMachineHealthEngine(unittest.TestCase):
    def setUp(self):
        Base.metadata.create_all(bind=engine)
        self.db = TestingSessionLocal()
        self.client = TestClient(app)
        HEALTH_PERSISTENCE.clear()

        # Seed sample test machines
        self.db.add(Machine(machine_id="MOTOR-01", machine_name="Motor 01", machine_type="Motor", location="Line A"))
        self.db.add(Machine(machine_id="PUMP-01", machine_name="Pump 01", machine_type="Pump", location="Line B"))
        self.db.add(Machine(machine_id="COMPRESSOR-01", machine_name="Compressor 01", machine_type="Compressor", location="Line C"))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=engine)
        HEALTH_PERSISTENCE.clear()

    def seed_baseline_data(self, machine_id="MOTOR-01", count=110, base_power=2.0, base_temp=42.5, base_vib=0.14, base_curr=10.0, base_volt=230.0, base_pf=0.91):
        """Seed normal baseline running telemetry."""
        now = datetime.datetime.utcnow() - datetime.timedelta(hours=1)
        for i in range(count):
            ts = now + datetime.timedelta(seconds=i)
            reading = SensorReading(
                machine_id=machine_id,
                timestamp=ts,
                voltage=base_volt,
                current=base_curr,
                power=base_power,
                temperature=base_temp,
                vibration=base_vib,
                power_factor=base_pf,
                operating_state="RUNNING"
            )
            self.db.add(reading)
        self.db.commit()

    def test_all_machines_healthy(self):
        """1. Healthy machine with baseline telemetry returns HEALTHY and priority <= 25."""
        self.seed_baseline_data("MOTOR-01")
        
        # Add a normal reading
        reading = SensorReading(
            machine_id="MOTOR-01",
            voltage=230.0,
            current=10.0,
            power=2.0,
            temperature=42.5,
            vibration=0.14,
            power_factor=0.91,
            operating_state="RUNNING",
            timestamp=datetime.datetime.utcnow()
        )
        self.db.add(reading)
        self.db.commit()

        res = self.client.get("/api/health/machines/MOTOR-01")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["health_status"], "HEALTHY")
        self.assertLessEqual(data["priority_score"], 25)
        self.assertIn("normal", data["primary_reason"].lower())

    def test_low_severity_anomaly_only(self):
        """2. Isolated low-severity anomaly produces WATCH health status."""
        self.seed_baseline_data("MOTOR-01")

        # Record a LOW severity anomaly in DB
        latest_reading = self.db.query(SensorReading).filter(SensorReading.machine_id == "MOTOR-01").first()
        anomaly = Anomaly(
            machine_id="MOTOR-01",
            reading_id=latest_reading.id,
            timestamp=datetime.datetime.utcnow(),
            anomaly_score=0.55,
            severity="LOW",
            affected_parameters="[]"
        )
        self.db.add(anomaly)
        self.db.commit()

        res = self.client.get("/api/health/machines/MOTOR-01")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["health_status"], "WATCH")
        self.assertTrue(26 <= data["priority_score"] <= 50)
        self.assertEqual(data["signals"]["anomaly"]["rating"], "LOW")

    def test_persistent_anomaly_increases_priority(self):
        """3. Persistent anomaly over multiple readings increases priority score."""
        self.seed_baseline_data("MOTOR-01")

        # Simulate 6 persistent anomaly checks
        HEALTH_PERSISTENCE["MOTOR-01"] = 6

        latest_reading = self.db.query(SensorReading).filter(SensorReading.machine_id == "MOTOR-01").first()
        anomaly = Anomaly(
            machine_id="MOTOR-01",
            reading_id=latest_reading.id,
            timestamp=datetime.datetime.utcnow(),
            anomaly_score=0.68,
            severity="MEDIUM",
            affected_parameters="[]"
        )
        self.db.add(anomaly)
        self.db.commit()

        res = self.client.get("/api/health/machines/MOTOR-01")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn(data["health_status"], ["ATTENTION", "CRITICAL"])
        self.assertGreaterEqual(data["priority_score"], 50)
        self.assertGreater(data["signals"]["persistence"]["normalized_score"], 0.5)

    def test_behavioral_change_only(self):
        """4. Active behavioral change yields WATCH or ATTENTION."""
        self.seed_baseline_data("MOTOR-01")

        # Record active behavioral change
        change = BehaviorChange(
            machine_id="MOTOR-01",
            parameter="power",
            detected_at=datetime.datetime.utcnow(),
            baseline_value=2.0,
            recent_value=2.6,
            percentage_change=30.0,
            change_type="INCREASING",
            change_score=3.5,
            persistence_count=3,
            status="ACTIVE"
        )
        self.db.add(change)
        self.db.commit()

        res = self.client.get("/api/health/machines/MOTOR-01")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn(data["health_status"], ["WATCH", "ATTENTION"])
        self.assertGreater(data["priority_score"], 25)
        self.assertEqual(data["signals"]["behavior"]["rating"], "MEDIUM")

    def test_energy_inefficiency_only(self):
        """5. Active energy inefficiency yields WATCH or ATTENTION."""
        self.seed_baseline_data("MOTOR-01")

        # Record active energy event
        energy = EnergyEvent(
            machine_id="MOTOR-01",
            detected_at=datetime.datetime.utcnow(),
            expected_power=2.0,
            actual_power=2.7,
            excess_power=0.7,
            excess_energy_kwh=1.4,
            estimated_cost=11.2,
            status="ACTIVE"
        )
        self.db.add(energy)
        self.db.commit()

        res = self.client.get("/api/health/machines/MOTOR-01")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn(data["health_status"], ["WATCH", "ATTENTION"])
        self.assertGreater(data["priority_score"], 25)
        self.assertEqual(data["signals"]["energy"]["rating"], "HIGH")

    def test_multiple_signals_correlation_bonus(self):
        """6. Compounding signals (anomaly + change + energy + diagnosis) trigger multi-signal bonus -> CRITICAL."""
        self.seed_baseline_data("MOTOR-01")
        HEALTH_PERSISTENCE["MOTOR-01"] = 10

        latest_reading = self.db.query(SensorReading).filter(SensorReading.machine_id == "MOTOR-01").first()

        # Anomaly
        self.db.add(Anomaly(
            machine_id="MOTOR-01",
            reading_id=latest_reading.id,
            timestamp=datetime.datetime.utcnow(),
            anomaly_score=0.82,
            severity="HIGH",
            affected_parameters="[]"
        ))
        # Behavior Change
        self.db.add(BehaviorChange(
            machine_id="MOTOR-01",
            parameter="vibration",
            detected_at=datetime.datetime.utcnow(),
            baseline_value=0.14,
            recent_value=0.28,
            percentage_change=100.0,
            change_type="INCREASING",
            change_score=5.0,
            persistence_count=5,
            status="ACTIVE"
        ))
        # Energy
        self.db.add(EnergyEvent(
            machine_id="MOTOR-01",
            detected_at=datetime.datetime.utcnow(),
            expected_power=2.0,
            actual_power=2.8,
            excess_power=0.8,
            excess_energy_kwh=2.0,
            estimated_cost=16.0,
            status="ACTIVE"
        ))
        # Diagnosis
        self.db.add(DiagnosisEvent(
            machine_id="MOTOR-01",
            timestamp=datetime.datetime.utcnow(),
            primary_possible_cause="MECHANICAL_DEGRADATION",
            evidence_score=0.84,
            evidence_json="[]",
            possible_causes_json="[]",
            explanation="Mechanical degradation detected",
            suggested_inspections_json="[]",
            status="ACTIVE"
        ))
        self.db.commit()

        res = self.client.get("/api/health/machines/MOTOR-01")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["health_status"], "CRITICAL")
        self.assertGreaterEqual(data["priority_score"], 80)
        # Verify multi-signal contributing factor explanation
        self.assertTrue(any("multi-signal" in f.lower() for f in data["contributing_factors"]))

    def test_priority_ranking_order(self):
        """7. Multi-signal compound issue machine ranks higher than isolated anomaly machine."""
        self.seed_baseline_data("MOTOR-01")
        self.seed_baseline_data("PUMP-01", base_power=1.5, base_vib=0.15)

        motor_reading = self.db.query(SensorReading).filter(SensorReading.machine_id == "MOTOR-01").first()

        # MOTOR-01: isolated point anomaly
        self.db.add(Anomaly(
            machine_id="MOTOR-01",
            reading_id=motor_reading.id,
            timestamp=datetime.datetime.utcnow(),
            anomaly_score=0.55,
            severity="LOW",
            affected_parameters="[]"
        ))

        # PUMP-01: compound issue (Change + Energy + Diagnosis)
        self.db.add(BehaviorChange(
            machine_id="PUMP-01",
            parameter="power",
            detected_at=datetime.datetime.utcnow(),
            baseline_value=1.5,
            recent_value=2.1,
            percentage_change=40.0,
            change_type="INCREASING",
            change_score=4.0,
            persistence_count=4,
            status="ACTIVE"
        ))
        self.db.add(EnergyEvent(
            machine_id="PUMP-01",
            detected_at=datetime.datetime.utcnow(),
            expected_power=1.5,
            actual_power=2.2,
            excess_power=0.7,
            excess_energy_kwh=1.5,
            estimated_cost=12.0,
            status="ACTIVE"
        ))
        self.db.add(DiagnosisEvent(
            machine_id="PUMP-01",
            timestamp=datetime.datetime.utcnow(),
            primary_possible_cause="OVERLOAD",
            evidence_score=0.75,
            evidence_json="[]",
            possible_causes_json="[]",
            explanation="Overload condition",
            suggested_inspections_json="[]",
            status="ACTIVE"
        ))
        self.db.commit()

        res = self.client.get("/api/health/overview")
        self.assertEqual(res.status_code, 200)
        data = res.json()

        # PUMP-01 must rank above MOTOR-01
        machines = data["machines"]
        pump_idx = next(i for i, m in enumerate(machines) if m["machine_id"] == "PUMP-01")
        motor_idx = next(i for i, m in enumerate(machines) if m["machine_id"] == "MOTOR-01")
        self.assertLess(pump_idx, motor_idx)
        self.assertEqual(data["top_priority_machine"], "PUMP-01")

    def test_operator_status_workflow(self):
        """8. Operator status can be updated to UNDER_REVIEW and RESOLVED."""
        self.seed_baseline_data("MOTOR-01")

        latest_reading = self.db.query(SensorReading).filter(SensorReading.machine_id == "MOTOR-01").first()

        # Create active issue
        self.db.add(Anomaly(
            machine_id="MOTOR-01",
            reading_id=latest_reading.id,
            timestamp=datetime.datetime.utcnow(),
            anomaly_score=0.85,
            severity="HIGH",
            affected_parameters="[]"
        ))
        self.db.commit()

        res = self.client.get("/api/health/machines/MOTOR-01")
        data = res.json()
        event_id = data["event_id"]
        self.assertIsNotNone(event_id)

        # Update to UNDER_REVIEW
        put_res = self.client.put(f"/api/health/events/{event_id}/operator-status", json={
            "status": "UNDER_REVIEW"
        })
        self.assertEqual(put_res.status_code, 200)
        self.assertEqual(put_res.json()["operator_status"], "UNDER_REVIEW")

        # Update to RESOLVED
        res_resolved = self.client.put(f"/api/health/events/{event_id}/operator-status", json={
            "status": "RESOLVED"
        })
        self.assertEqual(res_resolved.status_code, 200)
        self.assertEqual(res_resolved.json()["operator_status"], "RESOLVED")

    def test_no_duplicate_active_health_events(self):
        """9. Multiple evaluations update the existing active health event in place."""
        self.seed_baseline_data("MOTOR-01")

        latest_reading = self.db.query(SensorReading).filter(SensorReading.machine_id == "MOTOR-01").first()

        # Add anomaly
        self.db.add(Anomaly(
            machine_id="MOTOR-01",
            reading_id=latest_reading.id,
            timestamp=datetime.datetime.utcnow(),
            anomaly_score=0.75,
            severity="MEDIUM",
            affected_parameters="[]"
        ))
        self.db.commit()

        # Evaluate 3 times
        self.client.post("/api/health/analyze/MOTOR-01")
        self.client.post("/api/health/analyze/MOTOR-01")
        self.client.post("/api/health/analyze/MOTOR-01")

        active_events = self.db.query(MachineHealthEvent)\
            .filter(MachineHealthEvent.machine_id == "MOTOR-01")\
            .filter(MachineHealthEvent.status == "ACTIVE")\
            .all()

        self.assertEqual(len(active_events), 1)

    def test_factory_health_overview_endpoint(self):
        """10. Factory overview returns aggregated health counts and ranked list."""
        self.seed_baseline_data("MOTOR-01")
        self.seed_baseline_data("PUMP-01", base_power=1.5)
        self.seed_baseline_data("COMPRESSOR-01", base_power=3.0)

        motor_reading = self.db.query(SensorReading).filter(SensorReading.machine_id == "MOTOR-01").first()

        # MOTOR-01: High anomaly -> CRITICAL
        self.db.add(Anomaly(
            machine_id="MOTOR-01",
            reading_id=motor_reading.id,
            timestamp=datetime.datetime.utcnow(),
            anomaly_score=0.88,
            severity="HIGH",
            affected_parameters="[]"
        ))
        # PUMP-01: Behavioral change -> WATCH
        self.db.add(BehaviorChange(
            machine_id="PUMP-01",
            parameter="power",
            detected_at=datetime.datetime.utcnow(),
            baseline_value=1.5,
            recent_value=1.8,
            percentage_change=20.0,
            change_type="INCREASING",
            change_score=2.5,
            persistence_count=2,
            status="ACTIVE"
        ))
        # COMPRESSOR-01: normal -> HEALTHY
        self.db.commit()

        res = self.client.get("/api/health/overview")
        self.assertEqual(res.status_code, 200)
        data = res.json()

        self.assertEqual(data["total_machines"], 3)
        self.assertEqual(data["top_priority_machine"], "MOTOR-01")
        self.assertEqual(len(data["machines"]), 3)
        # Ranked descending
        scores = [m["priority_score"] for m in data["machines"]]
        self.assertEqual(scores, sorted(scores, reverse=True))

if __name__ == "__main__":
    unittest.main()
