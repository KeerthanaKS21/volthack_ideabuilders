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
from app.assistant.assistant_service import CONVERSATION_CACHE
from app.assistant.question_classifier import QuestionClassifier
from app.assistant.answer_generator import RuleBasedAnswerGenerator, LLMAnswerGenerator

# In-memory SQLite with StaticPool for isolated and shared thread execution
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

class TestGridLiteAIAssistant(unittest.TestCase):
    def setUp(self):
        Base.metadata.create_all(bind=engine)
        self.db = TestingSessionLocal()
        self.client = TestClient(app)
        CONVERSATION_CACHE.clear()

        # Seed standard virtual machines
        self.db.add(Machine(machine_id="MOTOR-01", machine_name="Motor 01", machine_type="Motor", location="Line A"))
        self.db.add(Machine(machine_id="MOTOR-02", machine_name="Motor 02", machine_type="Motor", location="Line A"))
        self.db.add(Machine(machine_id="PUMP-01", machine_name="Pump 01", machine_type="Pump", location="Line B"))
        self.db.add(Machine(machine_id="COMPRESSOR-01", machine_name="Compressor 01", machine_type="Compressor", location="Line C"))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=engine)
        CONVERSATION_CACHE.clear()

    def seed_baseline_telemetry(self, machine_id="MOTOR-01", count=110, base_power=2.0, base_temp=42.0, base_vib=0.14, base_curr=10.0, base_volt=230.0, base_pf=0.91):
        """Seed normal baseline running telemetry."""
        now = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)
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

    def test_current_machine_status(self):
        """1. Querying current status returns state and live telemetry."""
        self.seed_baseline_telemetry("MOTOR-01")

        res = self.client.post("/api/assistant/query", json={
            "question": "What is the current status of MOTOR-01?"
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["intent"], "MACHINE_STATUS")
        self.assertEqual(data["machine_id"], "MOTOR-01")
        self.assertIn("RUNNING", data["answer"])
        self.assertIn("Power", data["answer"])

    def test_current_sensor_value(self):
        """2. Querying specific sensor value returns exact verified value."""
        self.seed_baseline_telemetry("MOTOR-01", base_power=2.45)

        res = self.client.post("/api/assistant/query", json={
            "question": "What is MOTOR-01's current power?"
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["intent"], "SENSOR_VALUE")
        self.assertEqual(data["machine_id"], "MOTOR-01")
        self.assertIn("2.45 kW", data["answer"])

    def test_anomaly_question_machine_specific(self):
        """3. Querying why machine flagged as anomaly returns severity and score."""
        self.seed_baseline_telemetry("MOTOR-01")
        latest_reading = self.db.query(SensorReading).filter(SensorReading.machine_id == "MOTOR-01").first()
        self.db.add(Anomaly(
            machine_id="MOTOR-01",
            reading_id=latest_reading.id,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
            anomaly_score=0.88,
            severity="HIGH",
            affected_parameters="[]"
        ))
        self.db.commit()

        res = self.client.post("/api/assistant/query", json={
            "question": "Why was MOTOR-01 flagged as an anomaly?"
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["intent"], "ANOMALY")
        self.assertIn("HIGH", data["answer"])
        self.assertIn("0.88", data["answer"])

    def test_anomaly_question_factory_wide(self):
        """4. Querying which machines have anomalies returns anomalous list."""
        self.seed_baseline_telemetry("MOTOR-01")
        self.seed_baseline_telemetry("PUMP-01")

        m1_reading = self.db.query(SensorReading).filter(SensorReading.machine_id == "MOTOR-01").first()
        self.db.add(Anomaly(
            machine_id="MOTOR-01",
            reading_id=m1_reading.id,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
            anomaly_score=0.92,
            severity="HIGH",
            affected_parameters="[]"
        ))
        self.db.commit()

        res = self.client.post("/api/assistant/query", json={
            "question": "Which machines have anomalies?"
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["intent"], "ANOMALY")
        self.assertIn("MOTOR-01", data["answer"])
        self.assertIn("HIGH", data["answer"])

    def test_behavioral_change_question(self):
        """5. Querying behavioral changes returns active persistent shifts."""
        self.seed_baseline_telemetry("MOTOR-01")
        self.db.add(BehaviorChange(
            machine_id="MOTOR-01",
            parameter="power",
            detected_at=datetime.datetime.now(datetime.timezone.utc),
            baseline_value=2.0,
            recent_value=2.6,
            percentage_change=30.0,
            change_type="INCREASING",
            change_score=3.5,
            persistence_count=4,
            status="ACTIVE"
        ))
        self.db.commit()

        res = self.client.post("/api/assistant/query", json={
            "question": "What changed in MOTOR-01?"
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["intent"], "BEHAVIOR_CHANGE")
        self.assertIn("power", data["answer"].lower())
        self.assertIn("+30.0%", data["answer"])

    def test_energy_waste_question(self):
        """6. Querying energy waste returns excess kWh and cost."""
        self.seed_baseline_telemetry("MOTOR-01")
        self.db.add(EnergyEvent(
            machine_id="MOTOR-01",
            detected_at=datetime.datetime.now(datetime.timezone.utc),
            expected_power=2.0,
            actual_power=2.8,
            excess_power=0.8,
            excess_energy_kwh=3.2,
            estimated_cost=25.6,
            status="ACTIVE"
        ))
        self.db.commit()

        res = self.client.post("/api/assistant/query", json={
            "question": "How much excess energy is MOTOR-01 consuming?"
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["intent"], "ENERGY")
        self.assertIn("3.20 kWh", data["answer"])
        self.assertIn("25.60", data["answer"])

    def test_diagnosis_question(self):
        """7. Querying diagnosis presents diagnostic hypothesis without claiming false certainty."""
        self.seed_baseline_telemetry("MOTOR-01")
        self.db.add(DiagnosisEvent(
            machine_id="MOTOR-01",
            timestamp=datetime.datetime.now(datetime.timezone.utc),
            primary_possible_cause="MECHANICAL_DEGRADATION",
            evidence_score=0.84,
            evidence_json="[]",
            possible_causes_json="[]",
            explanation="Elevated vibration and thermal rise match mechanical degradation signature",
            suggested_inspections_json="[]",
            status="ACTIVE"
        ))
        self.db.commit()

        res = self.client.post("/api/assistant/query", json={
            "question": "What could be wrong with MOTOR-01?"
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["intent"], "DIAGNOSIS")
        self.assertIn("possible mechanical degradation", data["answer"].lower())
        self.assertIn("84%", data["answer"])
        # Must include cautionary note
        self.assertIn("diagnostic hypothesis", data["answer"].lower())

    def test_health_priority_triage(self):
        """8. Querying investigation priority answers which machine to investigate first."""
        self.seed_baseline_telemetry("MOTOR-01")
        self.seed_baseline_telemetry("PUMP-01")

        # Give MOTOR-01 high priority
        m1_reading = self.db.query(SensorReading).filter(SensorReading.machine_id == "MOTOR-01").first()
        self.db.add(Anomaly(
            machine_id="MOTOR-01",
            reading_id=m1_reading.id,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
            anomaly_score=0.91,
            severity="HIGH",
            affected_parameters="[]"
        ))
        self.db.commit()

        res = self.client.post("/api/assistant/query", json={
            "question": "Which machine should I investigate first?"
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["intent"], "HEALTH")
        self.assertIn("MOTOR-01", data["answer"])
        self.assertIn("investigate", data["answer"].lower())

    def test_factory_summary(self):
        """9. Querying factory summary returns accurate counts across all statuses."""
        self.seed_baseline_telemetry("MOTOR-01")
        self.seed_baseline_telemetry("MOTOR-02")
        self.seed_baseline_telemetry("PUMP-01")
        self.seed_baseline_telemetry("COMPRESSOR-01")

        res = self.client.post("/api/assistant/query", json={
            "question": "Give me a summary of the factory."
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["intent"], "FACTORY_SUMMARY")
        self.assertIn("4 machines", data["answer"])
        self.assertIn("Healthy", data["answer"])

    def test_unknown_machine(self):
        """10. Querying unregistered machine returns polite refusal without hallucinating."""
        res = self.client.post("/api/assistant/query", json={
            "question": "What is the status of TURBINE-99?"
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("not found", data["answer"].lower())

    def test_general_concept_explanation(self):
        """11. General engineering question is answered and tagged as general knowledge."""
        res = self.client.post("/api/assistant/query", json={
            "question": "What is power factor?"
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["intent"], "GENERAL_CONCEPT")
        self.assertTrue(data["is_general_knowledge"])
        self.assertIn("ratio of real working power", data["answer"].lower())

    def test_unknown_out_of_domain_question(self):
        """12. Future speculation or out-of-domain query is safely rejected."""
        res = self.client.post("/api/assistant/query", json={
            "question": "What will MOTOR-01 look like next year?"
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("don't have enough verified gridlite data", data["answer"].lower())

    def test_missing_database_telemetry_refusal(self):
        """13. Machine without readings does not fabricate data."""
        # PUMP-01 has no readings
        res = self.client.post("/api/assistant/query", json={
            "question": "What is the status of PUMP-01?"
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("don't have verified telemetry readings", data["answer"].lower())

    def test_hallucination_prevention_missing_voltage(self):
        """14. If a parameter reading is missing or null, assistant refuses rather than fabricating 230V."""
        # Insert a reading with voltage=None (if possible) or query parameter that has no readings
        # Machine COMPRESSOR-01 has no readings
        res = self.client.post("/api/assistant/query", json={
            "question": "What is COMPRESSOR-01's voltage?"
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertNotIn("230", data["answer"])
        self.assertIn("don't have", data["answer"].lower())

    def test_follow_up_pronoun_resolution(self):
        """15. Follow-up pronoun 'its' correctly resolves to previous machine in conversation."""
        self.seed_baseline_telemetry("MOTOR-01", base_power=2.8)
        conv_id = "test-session-123"

        # Query 1
        res1 = self.client.post("/api/assistant/query", json={
            "question": "What is MOTOR-01's current power?",
            "conversation_id": conv_id
        })
        self.assertEqual(res1.status_code, 200)
        self.assertEqual(res1.json()["machine_id"], "MOTOR-01")

        # Query 2 with pronoun
        res2 = self.client.post("/api/assistant/query", json={
            "question": "What is its temperature?",
            "conversation_id": conv_id
        })
        self.assertEqual(res2.status_code, 200)
        data2 = res2.json()
        self.assertEqual(data2["machine_id"], "MOTOR-01")
        self.assertIn("42.0", data2["answer"])

    def test_evidence_generation(self):
        """16. Verified evidence items are included in response payload."""
        self.seed_baseline_telemetry("MOTOR-01", base_power=2.8)

        res = self.client.post("/api/assistant/query", json={
            "question": "What is MOTOR-01's current power?"
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIsInstance(data["evidence"], list)

    def test_highest_power_consumer(self):
        """17. Asking for highest power consumer compares machines accurately."""
        self.seed_baseline_telemetry("MOTOR-01", base_power=2.0)
        self.seed_baseline_telemetry("MOTOR-02", base_power=4.5)

        res = self.client.post("/api/assistant/query", json={
            "question": "Which machine is consuming the most power?"
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("MOTOR-02", data["answer"])
        self.assertIn("4.50 kW", data["answer"])

    def test_quick_questions_endpoint(self):
        """18. Quick questions endpoint returns structured button options."""
        res = self.client.get("/api/assistant/quick-questions")
        self.assertEqual(res.status_code, 200)
        items = res.json()
        self.assertGreaterEqual(len(items), 5)
        self.assertTrue(any(item["label"] == "Factory Summary" for item in items))

    def test_clear_conversation(self):
        """19. Conversation deletion endpoint clears context cache."""
        conv_id = "test-conv-delete"
        CONVERSATION_CACHE[conv_id] = {"last_machine_id": "MOTOR-01"}

        res = self.client.delete(f"/api/assistant/conversations/{conv_id}")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["cleared"])
        self.assertNotIn(conv_id, CONVERSATION_CACHE)

    def test_llm_fallback_to_rule_based(self):
        """20. When no LLM key is present, rule based answer generator executes cleanly."""
        self.seed_baseline_telemetry("MOTOR-01")
        # Ensure no key in test environment
        res = self.client.post("/api/assistant/query", json={
            "question": "Why is MOTOR-01 critical?"
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIsNotNone(data["answer"])
        self.assertTrue(len(data["answer"]) > 10)

if __name__ == "__main__":
    unittest.main()
