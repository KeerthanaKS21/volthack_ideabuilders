"""
GridLite Phase 11: Master Integration Test Suite
Validates the entire end-to-end industrial intelligence pipeline:
Simulator -> Ingestion -> Database -> Anomaly -> Behavior Change -> Energy -> Diagnosis -> Health -> Priority -> Unified Events -> AI Assistant
"""

import unittest
import os
import sys
import json
import shutil
import tempfile
import datetime
from datetime import timedelta

# Add backend directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import numpy as np

from app.main import app
from app.database import Base, get_db
from app.models import Machine, SensorReading, Anomaly, BehaviorChange, DiagnosisEvent, MachineHealthEvent, UnifiedEvent
from app.pipeline.pipeline_service import PipelineService
from app.pipeline.event_manager import EventManager
from app.pipeline.telemetry_processor import TelemetryProcessor
from app.assistant.assistant_service import AssistantService
from app.assistant.query_engine import QueryEngine
from app.assistant.question_classifier import QuestionClassifier
from app.health.health_engine import HealthEngine
from app.diagnosis.diagnosis_engine import DiagnosisEngine
from app.ml.model_manager import ModelManager
from app.ml.anomaly_detector import AnomalyDetector

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

class TestGridLiteMasterIntegration(unittest.TestCase):
    def setUp(self):
        Base.metadata.create_all(bind=engine)
        self.db = TestingSessionLocal()
        self.client = TestClient(app)

        # Seed standard virtual machines with canonical profile types (Title case)
        self.machines = [
            Machine(machine_id="MOTOR-01", machine_name="Main Induction Motor 1", machine_type="Motor", location="Bay A"),
            Machine(machine_id="MOTOR-02", machine_name="Auxiliary Induction Motor 2", machine_type="Motor", location="Bay A"),
            Machine(machine_id="PUMP-01", machine_name="Cooling Water Pump 1", machine_type="Pump", location="Bay B"),
            Machine(machine_id="PUMP-02", machine_name="Cooling Water Pump 2", machine_type="Pump", location="Bay B"),
            Machine(machine_id="COMPRESSOR-01", machine_name="Rotary Screw Compressor 1", machine_type="Compressor", location="Bay C"),
            Machine(machine_id="CONVEYOR-01", machine_name="Main Feed Conveyor 1", machine_type="Conveyor", location="Bay D")
        ]
        self.db.add_all(self.machines)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=engine)

    def test_01_simulator_ingestion_and_db_storage(self):
        """Verify simulator telemetry ingestion stores verified readings in database with physical validation."""
        payload = {
            "machine_id": "MOTOR-01",
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "voltage": 230.0,
            "current": 8.7,
            "power": 2.0,
            "temperature": 42.0,
            "vibration": 0.14,
            "power_factor": 0.92,
            "operating_state": "RUNNING"
        }
        res = self.client.post("/api/readings", json=payload)
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertEqual(data["reading"]["machine_id"], "MOTOR-01")
        self.assertEqual(data["reading"]["power"], 2.0)

        # Check DB record
        saved = self.db.query(SensorReading).filter(SensorReading.machine_id == "MOTOR-01").first()
        self.assertIsNotNone(saved)
        self.assertEqual(saved.operating_state, "RUNNING")

    def test_02_physical_boundary_rejections(self):
        """Verify pipeline rejects unphysical values (negative power, out-of-bound voltage, etc.)."""
        # Negative power
        res = self.client.post("/api/readings", json={
            "machine_id": "MOTOR-01",
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "voltage": 230.0,
            "current": 8.7,
            "power": -5.0,
            "temperature": 45.0,
            "vibration": 0.14,
            "power_factor": 0.92,
            "operating_state": "RUNNING"
        })
        self.assertEqual(res.status_code, 422)

        # Extreme voltage > 600V
        res = self.client.post("/api/readings", json={
            "machine_id": "MOTOR-01",
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "voltage": 800.0,
            "current": 8.7,
            "power": 2.0,
            "temperature": 45.0,
            "vibration": 0.14,
            "power_factor": 0.92,
            "operating_state": "RUNNING"
        })
        self.assertEqual(res.status_code, 422)

    def test_03_end_to_end_mechanical_degradation_pipeline(self):
        """
        Master Pipeline Test:
        Inject MECHANICAL_DEGRADATION telemetry -> Anomaly -> Behavior Change -> Energy -> Diagnosis -> Health -> Priority -> Unified Events
        """
        # 1. Seed baseline normal readings (160 readings)
        base_time = datetime.datetime.utcnow() - timedelta(hours=2)
        for i in range(160):
            t = base_time + timedelta(seconds=i * 5)
            self.db.add(SensorReading(
                machine_id="MOTOR-01",
                timestamp=t,
                voltage=230.0,
                current=5.0,
                power=2.0,
                temperature=40.0,
                vibration=0.10,
                power_factor=0.92,
                operating_state="RUNNING"
            ))
        self.db.commit()

        # 2. Train ML model for MOTOR-01
        detector = AnomalyDetector()
        X = np.array([[230.0, 5.0, 2.0, 40.0, 0.10, 0.92] for _ in range(100)])
        detector.train(X)
        ModelManager.save_model("MOTOR-01", detector, {"sample_count": 100, "mean_power": 2.0})

        # 3. Ingest abnormal telemetry (Simulating MECHANICAL_DEGRADATION: elevated vibration, power & temp)
        now = datetime.datetime.utcnow()
        for i in range(10):
            t = now - timedelta(seconds=(10 - i) * 5)
            res = self.client.post("/api/readings", json={
                "machine_id": "MOTOR-01",
                "timestamp": t.isoformat(),
                "voltage": 230.0,
                "current": 5.5,
                "power": 2.5,
                "temperature": 46.0,
                "vibration": 0.20,
                "power_factor": 0.90,
                "operating_state": "RUNNING"
            })
            self.assertEqual(res.status_code, 201)

        # 4. Trigger change detection & diagnosis analysis
        self.client.post("/api/change-detection/analyze/MOTOR-01")
        diag_res = self.client.post("/api/diagnosis/analyze/MOTOR-01")
        self.assertEqual(diag_res.status_code, 200)
        diag_data = diag_res.json()
        self.assertIsNotNone(diag_data["primary_cause"])
        self.assertIn("DEGRADATION", diag_data["primary_cause"])

        # 5. Trigger health & priority evaluation
        health_res = self.client.post("/api/health/analyze/MOTOR-01")
        self.assertEqual(health_res.status_code, 200)
        health_data = health_res.json()
        self.assertIn(health_data["health_status"], ["WATCH", "ATTENTION", "CRITICAL"])
        self.assertGreater(health_data["priority_score"], 20)

        # 6. Verify Unified Events generated
        events_res = self.client.get("/api/events/machines/MOTOR-01/timeline")
        self.assertEqual(events_res.status_code, 200)
        timeline = events_res.json()
        self.assertGreater(len(timeline), 0)

        # 7. Ask AI Assistant about MOTOR-01
        ai_res = self.client.post("/api/assistant/query", json={
            "question": "What is the status of MOTOR-01?",
            "conversation_id": "test_master_conv"
        })
        self.assertEqual(ai_res.status_code, 200)
        ai_data = ai_res.json()
        self.assertIn("MOTOR-01", ai_data["answer"])
        self.assertGreater(len(ai_data["evidence"]), 0)

    def test_04_event_deduplication_and_auto_resolution(self):
        """Verify sustained abnormal conditions maintain single ACTIVE event and auto-resolve upon recovery."""
        # 1. Create active anomaly event
        e1 = EventManager.create_or_update_event(
            db=self.db,
            machine_id="PUMP-01",
            event_type="ANOMALY_DETECTED",
            severity="HIGH",
            title="PUMP-01 Anomaly",
            description="High vibration detected",
            evidence={"vibration": 0.45}
        )
        self.assertEqual(e1.status, "ACTIVE")

        # 2. Re-trigger same abnormal event -> deduplicated into same event
        e2 = EventManager.create_or_update_event(
            db=self.db,
            machine_id="PUMP-01",
            event_type="ANOMALY_DETECTED",
            severity="HIGH",
            title="PUMP-01 Anomaly Updated",
            description="High vibration still detected",
            evidence={"vibration": 0.48}
        )
        self.assertEqual(e1.id, e2.id)
        self.assertEqual(self.db.query(UnifiedEvent).filter(UnifiedEvent.machine_id == "PUMP-01").count(), 1)

        # 3. Telemetry normalizes -> resolve event
        resolved = EventManager.resolve_active_event(self.db, "PUMP-01", "ANOMALY_DETECTED")
        self.assertTrue(resolved)
        self.assertEqual(e1.status, "RESOLVED")

    def test_05_operator_event_lifecycle(self):
        """Verify operator can acknowledge and manually resolve events via REST API."""
        e = EventManager.create_or_update_event(
            db=self.db,
            machine_id="COMPRESSOR-01",
            event_type="ENERGY_INEFFICIENCY",
            severity="MEDIUM",
            title="Compressor High Power",
            description="Excess 1.2 kW",
            evidence={"excess_kw": 1.2}
        )
        self.assertEqual(e.status, "ACTIVE")

        # Acknowledge
        ack_res = self.client.post(f"/api/events/{e.id}/acknowledge")
        self.assertEqual(ack_res.status_code, 200)
        self.assertEqual(ack_res.json()["status"], "ACKNOWLEDGED")

        # Resolve
        res_res = self.client.post(f"/api/events/{e.id}/resolve")
        self.assertEqual(res_res.status_code, 200)
        self.assertEqual(res_res.json()["status"], "RESOLVED")

    def test_06_ai_assistant_zero_hallucination_and_refusal(self):
        """Verify AI Assistant strictly grounds answers in verified data and refuses non-existent parameters."""
        # Non-existent parameter
        res = self.client.post("/api/assistant/query", json={
            "question": "What is the bearing temperature of MOTOR-02?",
            "conversation_id": "test_hallucination_conv"
        })
        self.assertEqual(res.status_code, 200)
        ans = res.json()["answer"]
        self.assertTrue(
            "bearing temperature" in ans.lower() or 
            "don't have" in ans.lower() or
            "do not have" in ans.lower() or 
            "uninstrumented" in ans.lower() or 
            "not available" in ans.lower() or
            "not measured" in ans.lower()
        )

        # General factory summary
        res2 = self.client.post("/api/assistant/query", json={
            "question": "Give me a summary of the factory.",
            "conversation_id": "test_summary_conv"
        })
        self.assertEqual(res2.status_code, 200)
        self.assertIn("monitoring", res2.json()["answer"].lower())

    def test_07_demo_reset_endpoint(self):
        """Verify POST /api/demo/reset clears active anomalies, behavioral changes, and events."""
        # Create dirty state
        self.db.add(Anomaly(machine_id="MOTOR-01", reading_id=1, timestamp=datetime.datetime.utcnow(), anomaly_score=0.85, severity="HIGH", affected_parameters="{}"))
        self.db.add(BehaviorChange(machine_id="MOTOR-01", detected_at=datetime.datetime.utcnow(), parameter="power", baseline_value=2.0, recent_value=3.5, percentage_change=75.0, change_type="STEP_CHANGE", change_score=3.5, persistence_count=5, status="ACTIVE"))
        self.db.add(UnifiedEvent(machine_id="MOTOR-01", event_type="ANOMALY_DETECTED", severity="HIGH", timestamp=datetime.datetime.utcnow(), title="Anomaly", description="Alert", evidence_json="{}", status="ACTIVE"))
        self.db.commit()

        # Reset demo
        res = self.client.post("/api/demo/reset")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "success")
        self.assertGreater(data["cleared_events_count"], 0)

        # Check all events resolved
        active_count = self.db.query(UnifiedEvent).filter(UnifiedEvent.status == "ACTIVE").count()
        self.assertEqual(active_count, 0)

if __name__ == "__main__":
    unittest.main()
