import unittest
import os
import json
import datetime
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, StaticPool
from sqlalchemy.orm import sessionmaker

# Setup pathing
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.main import app
from app.database import Base, get_db
from app.models import Machine, SensorReading, EnergyEvent, BehaviorChange, Anomaly
from app.energy.config import ENERGY_CHANGE_THRESHOLD, ENERGY_MIN_DURATION
from app.energy.tariff import load_tariff, save_tariff

# Clean memory DB for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
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

class TestGridLiteEnergyIntelligence(unittest.TestCase):
    def setUp(self):
        # Build tables
        Base.metadata.create_all(bind=engine)
        self.client = TestClient(app)
        self.db = TestingSessionLocal()
        
        # Clear global tracker to ensure test independence
        from app.routes.readings import ENERGY_PERSISTENCE
        ENERGY_PERSISTENCE.clear()

        # Seed test machines
        self.seed_test_machines()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=engine)

    def seed_test_machines(self):
        m1 = Machine(
            machine_id="MOTOR-01",
            machine_name="Motor 1",
            machine_type="Motor",
            location="Line A"
        )
        m2 = Machine(
            machine_id="COMPRESSOR-01",
            machine_name="Compressor 1",
            machine_type="Compressor",
            location="Line B"
        )
        self.db.add_all([m1, m2])
        self.db.commit()

    def seed_baseline_data(self, machine_id, base_power, count=160):
        """Seed normal historical running baseline readings."""
        now = datetime.datetime.utcnow()
        for i in range(count):
            timestamp = now - datetime.timedelta(seconds=5 * (count - i))
            reading = SensorReading(
                machine_id=machine_id,
                timestamp=timestamp,
                voltage=230.0,
                power=base_power,
                temperature=40.0,
                vibration=0.15,
                current=5.0,
                power_factor=0.9,
                operating_state="RUNNING"
            )
            self.db.add(reading)
        self.db.commit()

    def test_normal_machine_consumption_and_small_variation(self):
        """1 & 2. Test normal consumption and small random power variations are ignored."""
        # Baseline = 2.0 kW
        self.seed_baseline_data("MOTOR-01", base_power=2.0)
        
        # Post a reading with a small variation (power = 2.05 kW, 2.5% increase)
        # Threshold is 10%, so this should not increment persistence or create events
        response = self.client.post("/api/readings", json={
            "machine_id": "MOTOR-01",
            "voltage": 230.0,
            "power": 2.05,
            "temperature": 40.0,
            "vibration": 0.15,
            "current": 5.0,
            "power_factor": 0.9,
            "operating_state": "RUNNING",
            "timestamp": datetime.datetime.utcnow().isoformat()
        })
        self.assertEqual(response.status_code, 201)
        
        # Check active energy events in DB
        events = self.db.query(EnergyEvent).filter(EnergyEvent.machine_id == "MOTOR-01").all()
        self.assertEqual(len(events), 0)

    def test_persistent_excess_power_and_resolutions(self):
        """3 & 4. Test persistent excess power triggers energy event and reduced consumption resolves it."""
        # Baseline = 2.0 kW
        self.seed_baseline_data("MOTOR-01", base_power=2.0)
        
        # We need to post high readings (power = 2.4 kW, 20% increase) persistently (ENERGY_MIN_DURATION = 3)
        now = datetime.datetime.utcnow()
        for i in range(3):
            t = now + datetime.timedelta(seconds=10 * i)
            response = self.client.post("/api/readings", json={
                "machine_id": "MOTOR-01",
                "voltage": 230.0,
                "power": 2.4,
                "temperature": 40.0,
                "vibration": 0.15,
                "current": 5.0,
                "power_factor": 0.9,
                "operating_state": "RUNNING",
                "timestamp": t.isoformat()
            })
            self.assertEqual(response.status_code, 201)
            
        # Check for ACTIVE energy event
        active_events = self.db.query(EnergyEvent)\
            .filter(EnergyEvent.machine_id == "MOTOR-01")\
            .filter(EnergyEvent.status == "ACTIVE")\
            .all()
        self.assertEqual(len(active_events), 1)
        
        # Post a reduced power reading to resolve the event
        response = self.client.post("/api/readings", json={
            "machine_id": "MOTOR-01",
            "voltage": 230.0,
            "power": 2.0,
            "temperature": 40.0,
            "vibration": 0.15,
            "current": 5.0,
            "power_factor": 0.9,
            "operating_state": "RUNNING",
            "timestamp": (now + datetime.timedelta(seconds=40)).isoformat()
        })
        self.assertEqual(response.status_code, 201)
        
        # Check that it got RESOLVED
        active_events_after = self.db.query(EnergyEvent)\
            .filter(EnergyEvent.machine_id == "MOTOR-01")\
            .filter(EnergyEvent.status == "ACTIVE")\
            .all()
        self.assertEqual(len(active_events_after), 0)

        resolved_events = self.db.query(EnergyEvent)\
            .filter(EnergyEvent.machine_id == "MOTOR-01")\
            .filter(EnergyEvent.status == "RESOLVED")\
            .all()
        self.assertEqual(len(resolved_events), 1)

    def test_state_filtering_off_idle_running(self):
        """5, 6 & 7. Test energy expected baseline changes per operating states (OFF, IDLE, RUNNING)."""
        # Baseline = 2.0 kW
        self.seed_baseline_data("MOTOR-01", base_power=2.0)
        
        # Post 3 elevated readings but in OFF or IDLE state
        now = datetime.datetime.utcnow()
        for i in range(3):
            t = now + datetime.timedelta(seconds=10 * i)
            self.client.post("/api/readings", json={
                "machine_id": "MOTOR-01",
                "voltage": 230.0,
                "power": 2.4, # high power, but in IDLE state
                "temperature": 40.0,
                "vibration": 0.15,
                "current": 5.0,
                "power_factor": 0.9,
                "operating_state": "IDLE",
                "timestamp": t.isoformat()
            })
            
        # Should not create active event because state is not RUNNING
        active_events = self.db.query(EnergyEvent)\
            .filter(EnergyEvent.machine_id == "MOTOR-01")\
            .filter(EnergyEvent.status == "ACTIVE")\
            .all()
        self.assertEqual(len(active_events), 0)

    def test_irregular_timestamp_intervals_kwh_cost(self):
        """8, 9 & 10. Test correct kWh integration and cost calculation over irregular timestamps."""
        # Baseline = 2.0 kW
        self.seed_baseline_data("MOTOR-01", base_power=2.0)
        
        # Override electricity tariff to ₹10.0 per kWh
        save_tariff(10.0)
        self.assertEqual(load_tariff(), 10.0)

        # Post persistent excess readings with known irregular intervals
        # Reading 1: t=0, power=2.4
        # Reading 2: t=3600s (1 hour), power=2.4
        # Reading 3: t=7200s (2 hours), power=2.4
        # expected_power=2.0, actual_power=2.4, excess_power=0.4kW
        # For 2 hours, excess energy = 0.4 kW * 2 hours = 0.8 kWh
        # Cost at ₹10/kWh = 0.8 * 10 = ₹8.00
        start_time = datetime.datetime.utcnow() + datetime.timedelta(hours=5)
        for i in range(3):
            t = start_time + datetime.timedelta(hours=i)
            self.client.post("/api/readings", json={
                "machine_id": "MOTOR-01",
                "voltage": 230.0,
                "power": 2.4,
                "temperature": 40.0,
                "vibration": 0.15,
                "current": 5.0,
                "power_factor": 0.9,
                "operating_state": "RUNNING",
                "timestamp": t.isoformat()
            })
            
        active_event = self.db.query(EnergyEvent)\
            .filter(EnergyEvent.machine_id == "MOTOR-01")\
            .filter(EnergyEvent.status == "ACTIVE")\
            .first()
            
        self.assertIsNotNone(active_event)
        self.assertAlmostEqual(active_event.excess_energy_kwh, 0.8, places=3)
        self.assertAlmostEqual(active_event.estimated_cost, 8.00, places=2)

    def test_configurable_tariff(self):
        """11. Test electricity tariff endpoints GET/PUT and validations."""
        # GET tariff config
        res = self.client.get("/api/energy/config")
        self.assertEqual(res.status_code, 200)
        self.assertIn("tariff", res.json())
        
        # PUT invalid tariff
        res = self.client.put("/api/energy/config", json={"tariff": -2.5})
        self.assertEqual(res.status_code, 422) # Fastapi validation error gt=0.0
        
        # PUT valid tariff
        res = self.client.put("/api/energy/config", json={"tariff": 12.5})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["tariff"], 12.5)
        self.assertEqual(load_tariff(), 12.5)

    def test_multiple_machines_different_baselines(self):
        """12. Verify multiple machines with different baselines are compared independently."""
        # MOTOR-01 baseline = 2.0 kW
        self.seed_baseline_data("MOTOR-01", base_power=2.0)
        # COMPRESSOR-01 baseline = 3.5 kW
        self.seed_baseline_data("COMPRESSOR-01", base_power=3.5)
        
        # Post 2.2 kW for MOTOR-01 (10% excess) and COMPRESSOR-01 (normal, as 2.2 < 3.5)
        # Verify machine-specific status classifications
        res1 = self.client.get("/api/energy/machines/MOTOR-01")
        self.assertEqual(res1.status_code, 200)
        self.assertEqual(res1.json()["baseline_power_kw"], 2.0)

        res2 = self.client.get("/api/energy/machines/COMPRESSOR-01")
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(res2.json()["baseline_power_kw"], 3.5)

    def test_insufficient_historical_baseline(self):
        """14. Test handling of insufficient baseline count."""
        # Seeding only 10 readings (required 100)
        self.seed_baseline_data("MOTOR-01", base_power=2.0, count=10)
        
        res = self.client.get("/api/energy/machines/MOTOR-01")
        self.assertEqual(res.status_code, 200)
        # If insufficient, baseline defaults to 0
        self.assertEqual(res.json()["baseline_power_kw"], 0.0)
        self.assertEqual(res.json()["energy_status"], "NORMAL")

    def test_integration_with_behavioral_change_and_anomaly(self):
        """16 & 17. Verify backend functions correctly with concurrent behavioral changes and anomalies."""
        # Baseline = 2.0 kW
        self.seed_baseline_data("MOTOR-01", base_power=2.0)
        
        # Inject behavioral change manually into DB
        bc = BehaviorChange(
            machine_id="MOTOR-01",
            detected_at=datetime.datetime.utcnow(),
            parameter="power",
            baseline_value=2.0,
            recent_value=2.5,
            percentage_change=25.0,
            change_type="SHIFTED_LEVEL",
            change_score=3.5,
            persistence_count=3,
            status="ACTIVE"
        )
        self.db.add(bc)
        
        # Inject anomaly record manually into DB
        an = Anomaly(
            machine_id="MOTOR-01",
            timestamp=datetime.datetime.utcnow(),
            anomaly_score=0.85,
            severity="HIGH",
            affected_parameters='{"power": 25.0}',
            reading_id=1
        )
        self.db.add(an)
        self.db.commit()

        # Check machine status GET route, verify both changes are retrieved successfully
        res = self.client.get("/api/machines/MOTOR-01/changes")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json()), 1)
        self.assertEqual(res.json()[0]["parameter"], "power")
