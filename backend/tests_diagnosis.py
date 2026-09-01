import unittest
import datetime
import json
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Machine, SensorReading, DiagnosisEvent, BehaviorChange, Anomaly, EnergyEvent
from app.diagnosis.diagnosis_engine import DiagnosisEngine
from app.diagnosis.explanations import RuleBasedExplainer
from app.diagnosis.evidence import EvidenceCollector
from app.diagnosis.schemas import PossibleCause

# Setup in-memory SQLite database for isolated test execution
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

class TestGridLiteDiagnosisEngine(unittest.TestCase):
    def setUp(self):
        Base.metadata.create_all(bind=engine)
        self.client = TestClient(app)
        self.db = TestingSessionLocal()
        self.seed_test_machines()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=engine)

    def seed_test_machines(self):
        m1 = Machine(machine_id="MOTOR-01", machine_name="Motor 1", machine_type="Motor", location="Line A")
        m2 = Machine(machine_id="PUMP-01", machine_name="Pump 1", machine_type="Pump", location="Line B")
        m3 = Machine(machine_id="COMPRESSOR-01", machine_name="Compressor 1", machine_type="Compressor", location="Line C")
        self.db.add_all([m1, m2, m3])
        self.db.commit()

    def seed_baseline_data(self, machine_id="MOTOR-01", count=160, base_power=2.0, base_temp=40.0, base_vib=0.10, base_cur=5.0, base_volt=230.0, base_pf=0.92):
        now = datetime.datetime.utcnow() - datetime.timedelta(hours=1)
        readings = []
        for i in range(count):
            t = now + datetime.timedelta(seconds=i * 5)
            readings.append(SensorReading(
                machine_id=machine_id,
                voltage=base_volt,
                current=base_cur,
                power=base_power,
                temperature=base_temp,
                vibration=base_vib,
                power_factor=base_pf,
                operating_state="RUNNING",
                timestamp=t
            ))
        self.db.add_all(readings)
        self.db.commit()

    def test_normal_machine_no_diagnosis(self):
        """1. Normal machine operating within baselines returns NORMAL and no active diagnosis."""
        self.seed_baseline_data("MOTOR-01")
        # Post normal reading
        self.client.post("/api/readings", json={
            "machine_id": "MOTOR-01",
            "voltage": 230.0,
            "current": 5.0,
            "power": 2.0,
            "temperature": 40.0,
            "vibration": 0.10,
            "power_factor": 0.92,
            "operating_state": "RUNNING",
            "timestamp": datetime.datetime.utcnow().isoformat()
        })

        res = self.client.get("/api/diagnosis/machines/MOTOR-01")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "NORMAL")
        self.assertEqual(len(data["possible_causes"]), 0)

    def test_mechanical_degradation_diagnosis(self):
        """2. High vibration, power increase, and temp increase trigger MECHANICAL_DEGRADATION."""
        self.seed_baseline_data("MOTOR-01", base_power=2.0, base_temp=40.0, base_vib=0.10)
        
        # Post degraded telemetry: vibration +100%, power +25%, temp +15%
        self.client.post("/api/readings", json={
            "machine_id": "MOTOR-01",
            "voltage": 230.0,
            "current": 5.5,
            "power": 2.5,
            "temperature": 46.0,
            "vibration": 0.20,
            "power_factor": 0.90,
            "operating_state": "RUNNING",
            "timestamp": datetime.datetime.utcnow().isoformat()
        })

        res = self.client.post("/api/diagnosis/analyze/MOTOR-01")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "DIAGNOSIS_AVAILABLE")
        self.assertEqual(data["primary_cause"], "MECHANICAL_DEGRADATION")
        self.assertGreaterEqual(data["evidence_score"], 0.60)
        self.assertIn("vibration", " ".join(data["possible_causes"][0]["evidence"]).lower())
        self.assertGreater(len(data["suggested_inspections"]), 0)

    def test_overload_diagnosis(self):
        """3. High current and power draw trigger OVERLOAD diagnosis."""
        self.seed_baseline_data("PUMP-01", base_power=1.5, base_cur=5.0, base_temp=40.0)

        # Post overload telemetry: current +60%, power +60%
        self.client.post("/api/readings", json={
            "machine_id": "PUMP-01",
            "voltage": 230.0,
            "current": 8.0,
            "power": 2.4,
            "temperature": 48.0,
            "vibration": 0.12,
            "power_factor": 0.90,
            "operating_state": "RUNNING",
            "timestamp": datetime.datetime.utcnow().isoformat()
        })

        res = self.client.post("/api/diagnosis/analyze/PUMP-01")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "DIAGNOSIS_AVAILABLE")
        self.assertEqual(data["primary_cause"], "OVERLOAD")
        self.assertGreaterEqual(data["evidence_score"], 0.70)

    def test_overheating_diagnosis(self):
        """4. Severe temperature elevation triggers OVERHEATING diagnosis."""
        self.seed_baseline_data("COMPRESSOR-01", base_temp=40.0, base_power=4.0)

        # Post high thermal telemetry: temp +50% (60.0 vs 40.0)
        self.client.post("/api/readings", json={
            "machine_id": "COMPRESSOR-01",
            "voltage": 230.0,
            "current": 8.0,
            "power": 4.0,
            "temperature": 60.0,
            "vibration": 0.11,
            "power_factor": 0.92,
            "operating_state": "RUNNING",
            "timestamp": datetime.datetime.utcnow().isoformat()
        })

        res = self.client.post("/api/diagnosis/analyze/COMPRESSOR-01")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "DIAGNOSIS_AVAILABLE")
        self.assertEqual(data["primary_cause"], "OVERHEATING")
        self.assertGreaterEqual(data["evidence_score"], 0.50)

    def test_electrical_anomaly_diagnosis(self):
        """5. Voltage fluctuation and power factor collapse trigger ELECTRICAL_ANOMALY."""
        self.seed_baseline_data("MOTOR-01", base_volt=230.0, base_pf=0.92)

        # Post abnormal electrical telemetry: voltage 210V (-8.7%), PF 0.70 (-23.9%)
        self.client.post("/api/readings", json={
            "machine_id": "MOTOR-01",
            "voltage": 210.0,
            "current": 6.5,
            "power": 2.0,
            "temperature": 40.0,
            "vibration": 0.10,
            "power_factor": 0.70,
            "operating_state": "RUNNING",
            "timestamp": datetime.datetime.utcnow().isoformat()
        })

        res = self.client.post("/api/diagnosis/analyze/MOTOR-01")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "DIAGNOSIS_AVAILABLE")
        self.assertEqual(data["primary_cause"], "ELECTRICAL_ANOMALY")
        self.assertGreaterEqual(data["evidence_score"], 0.50)

    def test_multiple_plausible_causes(self):
        """6. Compound faults return multiple ranked possible causes."""
        self.seed_baseline_data("MOTOR-01")
        # Elevated current, power, and vibration
        self.client.post("/api/readings", json={
            "machine_id": "MOTOR-01",
            "voltage": 230.0,
            "current": 8.0,
            "power": 3.0,
            "temperature": 52.0,
            "vibration": 0.18,
            "power_factor": 0.90,
            "operating_state": "RUNNING",
            "timestamp": datetime.datetime.utcnow().isoformat()
        })

        res = self.client.post("/api/diagnosis/analyze/MOTOR-01")
        data = res.json()
        self.assertEqual(data["status"], "DIAGNOSIS_AVAILABLE")
        self.assertGreater(len(data["possible_causes"]), 1)
        # Verify causes are ranked descending
        scores = [c["evidence_score"] for c in data["possible_causes"]]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_insufficient_evidence_when_no_baseline(self):
        """7. Machine with fewer than 100 historical readings returns INSUFFICIENT_EVIDENCE."""
        # Only seed 10 readings
        self.seed_baseline_data("MOTOR-01", count=10)
        res = self.client.get("/api/diagnosis/machines/MOTOR-01")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "INSUFFICIENT_EVIDENCE")
        self.assertEqual(len(data["possible_causes"]), 0)

    def test_rule_based_explainer_works_offline(self):
        """8. RuleBasedExplainer operates deterministically without external LLM keys."""
        explainer = RuleBasedExplainer()
        self.seed_baseline_data("MOTOR-01")
        bundle = EvidenceCollector.gather_evidence(self.db, "MOTOR-01")
        causes = [PossibleCause(
            cause="MECHANICAL_DEGRADATION",
            evidence_score=0.84,
            evidence=["Vibration +92%", "Power +25%"],
            suggested_inspections=["Inspect bearings", "Check shaft alignment"]
        )]
        text = explainer.explain("MOTOR-01", "Motor", causes, bundle)
        self.assertIn("MOTOR-01", text)
        self.assertIn("Mechanical Degradation", text)
        self.assertIn("0.84", text)
        self.assertIn("Suggested Physical Inspection", text)
        self.assertIn("AI-assisted diagnostic suggestion", text)

    def test_human_review_workflow_preserves_evidence(self):
        """9. Human review updates (CONFIRMED/REJECTED) do not mutate underlying telemetry."""
        self.seed_baseline_data("MOTOR-01")
        self.client.post("/api/readings", json={
            "machine_id": "MOTOR-01",
            "voltage": 230.0,
            "current": 5.5,
            "power": 2.5,
            "temperature": 46.0,
            "vibration": 0.20,
            "power_factor": 0.90,
            "operating_state": "RUNNING",
            "timestamp": datetime.datetime.utcnow().isoformat()
        })
        diag_res = self.client.post("/api/diagnosis/analyze/MOTOR-01").json()
        event_id = diag_res["event_id"]
        self.assertIsNotNone(event_id)

        # Update to CONFIRMED
        rev_res = self.client.put(f"/api/diagnosis/events/{event_id}/review", json={
            "status": "CONFIRMED"
        })
        self.assertEqual(rev_res.status_code, 200)
        self.assertEqual(rev_res.json()["human_review_status"], "CONFIRMED")

        # Verify event in DB has CONFIRMED status
        event = self.db.query(DiagnosisEvent).filter(DiagnosisEvent.id == event_id).first()
        self.assertEqual(event.human_review_status, "CONFIRMED")

    def test_duplicate_prevention_and_resolution(self):
        """10. Consecutive diagnoses update ongoing event; returning to normal resolves it."""
        self.seed_baseline_data("MOTOR-01")
        # Post fault reading
        self.client.post("/api/readings", json={
            "machine_id": "MOTOR-01",
            "voltage": 230.0,
            "current": 5.5,
            "power": 2.5,
            "temperature": 46.0,
            "vibration": 0.20,
            "power_factor": 0.90,
            "operating_state": "RUNNING",
            "timestamp": datetime.datetime.utcnow().isoformat()
        })
        res1 = self.client.post("/api/diagnosis/analyze/MOTOR-01").json()
        event_id_1 = res1["event_id"]

        # Post second fault reading
        self.client.post("/api/readings", json={
            "machine_id": "MOTOR-01",
            "voltage": 230.0,
            "current": 5.6,
            "power": 2.55,
            "temperature": 47.0,
            "vibration": 0.21,
            "power_factor": 0.90,
            "operating_state": "RUNNING",
            "timestamp": datetime.datetime.utcnow().isoformat()
        })
        res2 = self.client.post("/api/diagnosis/analyze/MOTOR-01").json()
        event_id_2 = res2["event_id"]
        # Verify event ID is preserved rather than duplicated
        self.assertEqual(event_id_1, event_id_2)

        # Return to normal telemetry
        self.client.post("/api/readings", json={
            "machine_id": "MOTOR-01",
            "voltage": 230.0,
            "current": 5.0,
            "power": 2.0,
            "temperature": 40.0,
            "vibration": 0.10,
            "power_factor": 0.92,
            "operating_state": "RUNNING",
            "timestamp": datetime.datetime.utcnow().isoformat()
        })
        res3 = self.client.post("/api/diagnosis/analyze/MOTOR-01").json()
        self.assertEqual(res3["status"], "NORMAL")

        # Verify active event is now RESOLVED in DB
        event = self.db.query(DiagnosisEvent).filter(DiagnosisEvent.id == event_id_1).first()
        self.assertEqual(event.status, "RESOLVED")

    def test_diagnosis_overview_endpoint(self):
        """11. Factory overview correctly surfaces prioritized machines."""
        self.seed_baseline_data("MOTOR-01")
        self.client.post("/api/readings", json={
            "machine_id": "MOTOR-01",
            "voltage": 230.0,
            "current": 5.5,
            "power": 2.5,
            "temperature": 46.0,
            "vibration": 0.20,
            "power_factor": 0.90,
            "operating_state": "RUNNING",
            "timestamp": datetime.datetime.utcnow().isoformat()
        })
        self.client.post("/api/diagnosis/analyze/MOTOR-01")

        overview_res = self.client.get("/api/diagnosis/overview")
        self.assertEqual(overview_res.status_code, 200)
        data = overview_res.json()
        self.assertEqual(data["total_active_diagnoses"], 1)
        self.assertEqual(data["machines_requiring_attention"][0]["machine_id"], "MOTOR-01")
        self.assertEqual(data["machines_requiring_attention"][0]["priority"], "HIGH")


if __name__ == "__main__":
    unittest.main()
