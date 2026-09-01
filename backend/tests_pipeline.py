import unittest
import json
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Machine, SensorReading, UnifiedEvent, Anomaly, BehaviorChange, EnergyEvent, DiagnosisEvent, MachineHealthEvent
from app.pipeline.telemetry_processor import TelemetryProcessor
from app.pipeline.event_manager import EventManager
from app.pipeline.pipeline_service import PipelineService
from app.schemas import SensorReadingCreate

# Setup in-memory SQLite database for isolated pipeline testing
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
client = TestClient(app)

class TestPipelineAndEvents(unittest.TestCase):
    def setUp(self):
        Base.metadata.create_all(bind=engine)
        self.db = TestingSessionLocal()
        
        # Seed test machines
        m1 = Machine(machine_id="MOTOR-01", machine_name="Main Induction Motor", machine_type="MOTOR", location="Bay A")
        m2 = Machine(machine_id="PUMP-01", machine_name="Cooling Water Pump", machine_type="PUMP", location="Bay B")
        self.db.add_all([m1, m2])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=engine)

    def test_01_valid_telemetry_ingestion(self):
        """Test valid telemetry ingestion and initial state transition event."""
        payload = {
            "machine_id": "MOTOR-01",
            "timestamp": datetime.utcnow().isoformat(),
            "voltage": 230.0,
            "current": 8.5,
            "power": 2.1,
            "temperature": 45.0,
            "vibration": 0.12,
            "power_factor": 0.92,
            "operating_state": "RUNNING"
        }
        response = client.post("/api/readings", json=payload)
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["reading"]["machine_id"], "MOTOR-01")

        # Verify state change event was generated
        state_events = self.db.query(UnifiedEvent).filter(
            UnifiedEvent.machine_id == "MOTOR-01", 
            UnifiedEvent.event_type == "MACHINE_STATE_CHANGED"
        ).all()
        self.assertEqual(len(state_events), 1)
        self.assertEqual(state_events[0].severity, "INFO")

    def test_02_corrupted_telemetry_rejected_negative_power(self):
        """Test that negative power telemetry is rejected with HTTP 422."""
        payload = {
            "machine_id": "MOTOR-01",
            "timestamp": datetime.utcnow().isoformat(),
            "voltage": 230.0,
            "current": 8.5,
            "power": -5.0,
            "temperature": 45.0,
            "vibration": 0.12,
            "power_factor": 0.92,
            "operating_state": "RUNNING"
        }
        response = client.post("/api/readings", json=payload)
        self.assertEqual(response.status_code, 422)

    def test_03_corrupted_telemetry_rejected_extreme_temperature(self):
        """Test that impossible temperature is rejected with HTTP 422."""
        payload = {
            "machine_id": "MOTOR-01",
            "timestamp": datetime.utcnow().isoformat(),
            "voltage": 230.0,
            "current": 8.5,
            "power": 2.1,
            "temperature": 850.0,
            "vibration": 0.12,
            "power_factor": 0.92,
            "operating_state": "RUNNING"
        }
        response = client.post("/api/readings", json=payload)
        self.assertEqual(response.status_code, 422)
        self.assertIn("Acceptable range is -40°C to 250°C", response.json()["detail"])

    def test_04_unregistered_machine_rejected(self):
        """Test that telemetry for an unknown machine returns HTTP 404."""
        payload = {
            "machine_id": "ROBOT-99",
            "timestamp": datetime.utcnow().isoformat(),
            "voltage": 230.0,
            "current": 8.5,
            "power": 2.1,
            "temperature": 45.0,
            "vibration": 0.12,
            "power_factor": 0.92,
            "operating_state": "RUNNING"
        }
        response = client.post("/api/readings", json=payload)
        self.assertEqual(response.status_code, 404)

    def test_05_state_transition_and_deduplication(self):
        """Test that state transition produces an event, but consecutive identical states do not."""
        # 1st reading: RUNNING
        payload = {
            "machine_id": "MOTOR-01",
            "timestamp": datetime.utcnow().isoformat(),
            "voltage": 230.0,
            "current": 8.5,
            "power": 2.1,
            "temperature": 45.0,
            "vibration": 0.12,
            "power_factor": 0.92,
            "operating_state": "RUNNING"
        }
        client.post("/api/readings", json=payload)
        self.assertEqual(self.db.query(UnifiedEvent).filter(UnifiedEvent.event_type == "MACHINE_STATE_CHANGED").count(), 1)

        # 2nd reading: still RUNNING
        client.post("/api/readings", json=payload)
        self.assertEqual(self.db.query(UnifiedEvent).filter(UnifiedEvent.event_type == "MACHINE_STATE_CHANGED").count(), 1)

        # 3rd reading: STOPPED (transition)
        payload["operating_state"] = "STOPPED"
        client.post("/api/readings", json=payload)
        self.assertEqual(self.db.query(UnifiedEvent).filter(UnifiedEvent.event_type == "MACHINE_STATE_CHANGED").count(), 2)

    def test_06_event_deduplication_active_event_maintained(self):
        """Test that consecutive abnormal conditions update the single active event rather than duplicating."""
        e1 = EventManager.create_or_update_event(
            db=self.db,
            machine_id="MOTOR-01",
            event_type="ANOMALY_DETECTED",
            severity="MEDIUM",
            title="MOTOR-01 Anomaly Detected",
            description="Initial anomaly flag",
            evidence={"score": 0.65}
        )
        self.assertEqual(e1.status, "ACTIVE")
        self.assertEqual(self.db.query(UnifiedEvent).count(), 1)

        # Repeat event creation for same machine & type
        e2 = EventManager.create_or_update_event(
            db=self.db,
            machine_id="MOTOR-01",
            event_type="ANOMALY_DETECTED",
            severity="HIGH",
            title="MOTOR-01 Anomaly Detected (HIGH)",
            description="Escalated anomaly flag",
            evidence={"score": 0.88}
        )
        self.assertEqual(e1.id, e2.id)
        self.assertEqual(e2.severity, "HIGH")
        self.assertEqual(self.db.query(UnifiedEvent).count(), 1)

    def test_07_event_auto_resolution(self):
        """Test that event resolves when condition disappears."""
        EventManager.create_or_update_event(
            db=self.db,
            machine_id="MOTOR-01",
            event_type="ENERGY_INEFFICIENCY",
            severity="MEDIUM",
            title="MOTOR-01 Energy Inefficiency",
            description="Elevated consumption",
            evidence={"excess_kwh": 3.4}
        )
        active = self.db.query(UnifiedEvent).filter(UnifiedEvent.status == "ACTIVE").first()
        self.assertIsNotNone(active)

        # Resolve
        resolved = EventManager.resolve_active_event(self.db, "MOTOR-01", "ENERGY_INEFFICIENCY")
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.status, "RESOLVED")
        self.assertIsNotNone(resolved.resolved_at)

    def test_08_event_acknowledgement_lifecycle(self):
        """Test operator acknowledgement endpoint."""
        e = EventManager.create_or_update_event(
            db=self.db,
            machine_id="MOTOR-01",
            event_type="HEALTH_CHANGED",
            severity="CRITICAL",
            title="MOTOR-01 Health Critical",
            description="Critical multi-engine alerts",
            evidence={"priority": 89}
        )
        response = client.post(f"/api/events/{e.id}/acknowledge")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ACKNOWLEDGED")
        self.assertIsNotNone(data["acknowledged_at"])

    def test_09_event_manual_resolution_lifecycle(self):
        """Test operator manual resolve endpoint."""
        e = EventManager.create_or_update_event(
            db=self.db,
            machine_id="PUMP-01",
            event_type="DIAGNOSIS_AVAILABLE",
            severity="HIGH",
            title="PUMP-01 Possible Overload",
            description="Current elevated",
            evidence={"cause": "OVERLOAD"}
        )
        response = client.post(f"/api/events/{e.id}/resolve")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "RESOLVED")
        self.assertIsNotNone(data["resolved_at"])

    def test_10_list_events_with_filters(self):
        """Test GET /api/events with filters."""
        EventManager.create_or_update_event(self.db, "MOTOR-01", "ANOMALY_DETECTED", "HIGH", "A1", "D1")
        EventManager.create_or_update_event(self.db, "PUMP-01", "BEHAVIOR_CHANGE", "MEDIUM", "A2", "D2")

        res1 = client.get("/api/events?machine_id=MOTOR-01")
        self.assertEqual(res1.status_code, 200)
        self.assertEqual(len(res1.json()), 1)
        self.assertEqual(res1.json()[0]["machine_id"], "MOTOR-01")

        res2 = client.get("/api/events?severity=MEDIUM")
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(len(res2.json()), 1)
        self.assertEqual(res2.json()[0]["machine_id"], "PUMP-01")

    def test_11_get_recent_events_prioritization(self):
        """Test GET /api/events/recent prioritizes CRITICAL and HIGH severity above INFO."""
        EventManager.create_or_update_event(self.db, "MOTOR-01", "MACHINE_STATE_CHANGED", "INFO", "State Changed", "Desc")
        EventManager.create_or_update_event(self.db, "PUMP-01", "HEALTH_CHANGED", "CRITICAL", "Health Critical", "Desc")
        EventManager.create_or_update_event(self.db, "MOTOR-01", "ANOMALY_DETECTED", "HIGH", "Anomaly High", "Desc")

        res = client.get("/api/events/recent")
        self.assertEqual(res.status_code, 200)
        events = res.json()
        self.assertEqual(len(events), 3)
        # CRITICAL should be first
        self.assertEqual(events[0]["severity"], "CRITICAL")
        self.assertEqual(events[1]["severity"], "HIGH")
        self.assertEqual(events[2]["severity"], "INFO")

    def test_12_machine_event_timeline(self):
        """Test GET /api/events/machines/{machine_id}/timeline returns machine-specific chronological stream."""
        EventManager.create_or_update_event(self.db, "MOTOR-01", "MACHINE_STATE_CHANGED", "INFO", "Started", "Desc")
        EventManager.create_or_update_event(self.db, "PUMP-01", "ANOMALY_DETECTED", "HIGH", "Pump Anomaly", "Desc")

        res = client.get("/api/events/machines/MOTOR-01/timeline")
        self.assertEqual(res.status_code, 200)
        events = res.json()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["machine_id"], "MOTOR-01")

    def test_13_demo_reset_endpoint(self):
        """Test POST /api/demo/reset clears all active intelligence events."""
        EventManager.create_or_update_event(self.db, "MOTOR-01", "ANOMALY_DETECTED", "HIGH", "A1", "D1")
        EventManager.create_or_update_event(self.db, "PUMP-01", "HEALTH_CHANGED", "CRITICAL", "A2", "D2")
        self.assertEqual(self.db.query(UnifiedEvent).count(), 2)

        res = client.post("/api/demo/reset")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["cleared_events_count"], 2)
        self.assertEqual(self.db.query(UnifiedEvent).count(), 0)

    def test_14_backend_health_check(self):
        """Test GET /api/health returns database and pipeline status."""
        res = client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["database"], "connected")
        self.assertEqual(data["pipeline"], "running")

    def test_15_re_trigger_event_after_resolution(self):
        """Test that an event resolved earlier correctly creates a new active event if fault recurs."""
        e1 = EventManager.create_or_update_event(self.db, "MOTOR-01", "ANOMALY_DETECTED", "HIGH", "A1", "D1")
        EventManager.resolve_active_event(self.db, "MOTOR-01", "ANOMALY_DETECTED")
        self.assertEqual(self.db.query(UnifiedEvent).filter(UnifiedEvent.status == "RESOLVED").count(), 1)

        # Re-trigger
        e2 = EventManager.create_or_update_event(self.db, "MOTOR-01", "ANOMALY_DETECTED", "HIGH", "A1 (New)", "D1 (New)")
        self.assertNotEqual(e1.id, e2.id)
        self.assertEqual(e2.status, "ACTIVE")
        self.assertEqual(self.db.query(UnifiedEvent).count(), 2)

    def test_16_single_event_details(self):
        """Test GET /api/events/{event_id} returns accurate event details and evidence."""
        e = EventManager.create_or_update_event(
            self.db, "MOTOR-01", "ENERGY_INEFFICIENCY", "MEDIUM", 
            "Excess Energy", "Consuming +22%", {"expected_power_kw": 2.0, "actual_power_kw": 2.44}
        )
        res = client.get(f"/api/events/{e.id}")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["id"], e.id)
        self.assertEqual(data["evidence"]["expected_power_kw"], 2.0)
        self.assertEqual(data["evidence"]["actual_power_kw"], 2.44)

    def test_17_single_event_404(self):
        """Test GET /api/events/99999 returns HTTP 404 for unknown event ID."""
        res = client.get("/api/events/99999")
        self.assertEqual(res.status_code, 404)

    def test_18_multi_machine_isolation(self):
        """Test that events for different machines remain isolated."""
        EventManager.create_or_update_event(self.db, "MOTOR-01", "ANOMALY_DETECTED", "HIGH", "M1 Anomaly", "D1")
        EventManager.create_or_update_event(self.db, "PUMP-01", "ANOMALY_DETECTED", "MEDIUM", "P1 Anomaly", "D2")

        # Resolving MOTOR-01 should not resolve PUMP-01
        EventManager.resolve_active_event(self.db, "MOTOR-01", "ANOMALY_DETECTED")
        m1_active = self.db.query(UnifiedEvent).filter(UnifiedEvent.machine_id == "MOTOR-01", UnifiedEvent.status == "ACTIVE").first()
        p1_active = self.db.query(UnifiedEvent).filter(UnifiedEvent.machine_id == "PUMP-01", UnifiedEvent.status == "ACTIVE").first()

        self.assertIsNone(m1_active)
        self.assertIsNotNone(p1_active)
        self.assertEqual(p1_active.severity, "MEDIUM")

    def test_19_state_transition_sequence(self):
        """Test sequential transitions: STARTING -> RUNNING -> COOLDOWN -> STOPPED."""
        states = ["STARTING", "RUNNING", "COOLDOWN", "STOPPED"]
        for s in states:
            payload = {
                "machine_id": "MOTOR-01",
                "timestamp": datetime.utcnow().isoformat(),
                "voltage": 230.0,
                "current": 5.0,
                "power": 1.2,
                "temperature": 40.0,
                "vibration": 0.08,
                "power_factor": 0.9,
                "operating_state": s
            }
            res = client.post("/api/readings", json=payload)
            self.assertEqual(res.status_code, 201)

        # 4 state change events emitted
        events = self.db.query(UnifiedEvent).filter(UnifiedEvent.event_type == "MACHINE_STATE_CHANGED").all()
        self.assertEqual(len(events), 4)

    def test_20_pipeline_ingestion_returns_reading_and_anomaly(self):
        """Test that POST /api/readings returns formatted reading and anomaly structure."""
        payload = {
            "machine_id": "PUMP-01",
            "timestamp": datetime.utcnow().isoformat(),
            "voltage": 230.0,
            "current": 4.2,
            "power": 0.95,
            "temperature": 38.5,
            "vibration": 0.05,
            "power_factor": 0.88,
            "operating_state": "RUNNING"
        }
        res = client.post("/api/readings", json=payload)
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertIn("reading", data)
        self.assertIn("anomaly", data)
        self.assertEqual(data["reading"]["machine_id"], "PUMP-01")

if __name__ == "__main__":
    unittest.main()
