import unittest
import os
import datetime
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, StaticPool
from sqlalchemy.orm import sessionmaker

# Set sys.path to resolve backend app correctly
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.main import app
from app.database import Base, get_db
from app.models import Machine, SensorReading, BehaviorChange
from app.ml.config import PERSISTENCE_THRESHOLD

# Setup clean testing SQLite memory database
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

# Override dependencies
app.dependency_overrides[get_db] = override_get_db

class TestGridLiteBehavioralChanges(unittest.TestCase):
    def setUp(self):
        # Recreate tables in memory SQLite
        engine = TestingSessionLocal().bind
        Base.metadata.create_all(bind=engine)
        
        self.client = TestClient(app)
        self.db = TestingSessionLocal()
        
        # Seed test machines
        self.seed_test_machines()

    def tearDown(self):
        self.db.close()
        engine = TestingSessionLocal().bind
        Base.metadata.drop_all(bind=engine)

    def seed_test_machines(self):
        m1 = Machine(
            machine_id="TEST-MOTOR",
            machine_name="Test Motor 1",
            machine_type="Motor",
            location="Test Area A"
        )
        m2 = Machine(
            machine_id="TEST-PUMP",
            machine_name="Test Pump 2",
            machine_type="Pump",
            location="Test Area B"
        )
        self.db.add(m1)
        self.db.add(m2)
        self.db.commit()

    def seed_historical_baseline(self, machine_id, count=110):
        """Seed normal running telemetry data to establish a stable baseline."""
        base_time = datetime.datetime.utcnow() - datetime.timedelta(hours=10)
        for i in range(count):
            reading = SensorReading(
                machine_id=machine_id,
                timestamp=base_time + datetime.timedelta(seconds=i * 5),
                voltage=230.0 + (i % 3) - 1, # 229V - 231V
                current=8.0,
                power=1.9, # baseline mean
                temperature=42.0, # baseline mean
                vibration=0.12, # baseline mean
                power_factor=0.90,
                operating_state="RUNNING"
            )
            self.db.add(reading)
        self.db.commit()

    def seed_recent_window(self, machine_id, count=50, shift_param=None, shift_val=None, trend_dir=None, variability=False):
        """Seed rolling recent readings window with various pattern changes."""
        base_time = datetime.datetime.utcnow() - datetime.timedelta(minutes=30)
        
        for i in range(count):
            # Default values (baseline normal) depending on machine type
            if "PUMP" in machine_id.upper():
                voltage = 230.0
                current = 6.0
                power = 1.4
                temperature = 41.0
                vibration = 0.15
                pf = 0.88
            else:
                voltage = 230.0
                current = 8.0
                power = 1.9
                temperature = 42.0
                vibration = 0.12
                pf = 0.90

            # Apply shifts or trends
            if shift_param:
                if shift_param == "power":
                    power = shift_val
                elif shift_param == "temperature":
                    temperature = shift_val
                elif shift_param == "vibration":
                    vibration = shift_val

            if trend_dir:
                # Gradual drift
                factor = (i / count) # scales from 0.0 to 1.0
                if trend_dir == "up":
                    power = 1.9 + (factor * 0.6) # drifts 1.9 -> 2.5
                elif trend_dir == "down":
                    power = 1.9 - (factor * 0.6) # drifts 1.9 -> 1.3

            if variability:
                # High fluctuation around baseline mean
                vibration = 0.12 + (i % 2 * 0.15 - 0.075) # large standard deviation shifts

            reading = SensorReading(
                machine_id=machine_id,
                timestamp=base_time + datetime.timedelta(seconds=i * 5),
                voltage=voltage,
                current=current,
                power=power,
                temperature=temperature,
                vibration=vibration,
                power_factor=pf,
                operating_state="RUNNING"
            )
            self.db.add(reading)
        self.db.commit()

    def run_multiple_analyses(self, machine_id, count=3):
        """Run analysis POST multiple times to simulate persistence checks."""
        for _ in range(count):
            response = self.client.post(f"/api/change-detection/analyze/{machine_id}")
        return response

    def test_no_behavioral_change(self):
        """1. Verify steady telemetry generates no change alerts."""
        self.seed_historical_baseline("TEST-MOTOR")
        self.seed_recent_window("TEST-MOTOR", count=50) # normal window
        
        response = self.run_multiple_analyses("TEST-MOTOR", count=3)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 0)

    def test_small_random_variation_no_change(self):
        """2. Assert minor fluctuations do not trigger behavioral events."""
        self.seed_historical_baseline("TEST-MOTOR")
        # Seed slightly higher values (+2% change) which is statistically meaningless
        self.seed_recent_window("TEST-MOTOR", count=50, shift_param="power", shift_val=1.93)
        
        response = self.run_multiple_analyses("TEST-MOTOR", count=3)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 0)

    def test_persistent_power_increase(self):
        """3. Persistent power shift triggers SHIFTED_LEVEL change."""
        self.seed_historical_baseline("TEST-MOTOR")
        self.seed_recent_window("TEST-MOTOR", count=50, shift_param="power", shift_val=2.4) # +26% shift
        
        response = self.run_multiple_analyses("TEST-MOTOR", count=3)
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["parameter"], "power")
        self.assertEqual(data[0]["change_type"], "SHIFTED_LEVEL")
        self.assertEqual(data[0]["status"], "ACTIVE")

    def test_persistent_temperature_increase(self):
        """4. Persistent temperature increase triggers alert."""
        self.seed_historical_baseline("TEST-MOTOR")
        self.seed_recent_window("TEST-MOTOR", count=50, shift_param="temperature", shift_val=48.0) # +14% shift
        
        response = self.run_multiple_analyses("TEST-MOTOR", count=3)
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["parameter"], "temperature")

    def test_persistent_vibration_increase(self):
        """5. Persistent vibration increase triggers alert."""
        self.seed_historical_baseline("TEST-MOTOR")
        self.seed_recent_window("TEST-MOTOR", count=50, shift_param="vibration", shift_val=0.22) # +83% shift
        
        response = self.run_multiple_analyses("TEST-MOTOR", count=3)
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["parameter"], "vibration")

    def test_multiple_parameters_changing(self):
        """6. Simultaneous param shifts are both identified."""
        self.seed_historical_baseline("TEST-MOTOR")
        # Add temperature shift
        self.seed_recent_window("TEST-MOTOR", count=50, shift_param="temperature", shift_val=50.0)
        
        # Modify database directly to add a power shift to the same readings
        readings = self.db.query(SensorReading).filter(SensorReading.machine_id == "TEST-MOTOR").order_by(SensorReading.id.desc()).limit(50).all()
        for r in readings:
            r.power = 2.45
        self.db.commit()

        response = self.run_multiple_analyses("TEST-MOTOR", count=3)
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertEqual(len(data), 2)
        params = [item["parameter"] for item in data]
        self.assertIn("power", params)
        self.assertIn("temperature", params)

    def test_temporary_spike_no_event(self):
        """7. Temporary spikes with count < PERSISTENCE_THRESHOLD do not return active alerts."""
        self.seed_historical_baseline("TEST-MOTOR")
        self.seed_recent_window("TEST-MOTOR", count=50, shift_param="power", shift_val=2.4)
        
        # Run only 1 analysis POST (persistence count = 1)
        response = self.client.post("/api/change-detection/analyze/TEST-MOTOR")
        self.assertEqual(response.status_code, 200)
        
        # Should return 0 active changes because persistence threshold is 3
        self.assertEqual(len(response.json()), 0)
        
        # Database should still store the tracked event in active state with count=1
        ev = self.db.query(BehaviorChange).filter(BehaviorChange.machine_id == "TEST-MOTOR", BehaviorChange.status == "ACTIVE").first()
        self.assertIsNotNone(ev)
        self.assertEqual(ev.persistence_count, 1)

    def test_gradual_increasing_drift(self):
        """8. Gradual upward telemetry drift triggers INCREASING trend pattern."""
        self.seed_historical_baseline("TEST-MOTOR")
        self.seed_recent_window("TEST-MOTOR", count=50, trend_dir="up")
        
        response = self.run_multiple_analyses("TEST-MOTOR", count=3)
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["parameter"], "power")
        self.assertEqual(data[0]["change_type"], "INCREASING")

    def test_decreasing_drift(self):
        """9. Gradual downward telemetry drift triggers DECREASING trend pattern."""
        self.seed_historical_baseline("TEST-MOTOR")
        self.seed_recent_window("TEST-MOTOR", count=50, trend_dir="down")
        
        response = self.run_multiple_analyses("TEST-MOTOR", count=3)
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["parameter"], "power")
        self.assertEqual(data[0]["change_type"], "DECREASING")

    def test_increased_variability(self):
        """10. Telemetry standard deviation expansion triggers INCREASED_VARIABILITY."""
        self.seed_historical_baseline("TEST-MOTOR")
        self.seed_recent_window("TEST-MOTOR", count=50, variability=True)
        
        response = self.run_multiple_analyses("TEST-MOTOR", count=3)
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["parameter"], "vibration")
        self.assertEqual(data[0]["change_type"], "INCREASED_VARIABILITY")

    def test_insufficient_historical_data(self):
        """11. Baseline statistics calculation fails if counts < 100."""
        self.seed_historical_baseline("TEST-MOTOR", count=40)
        self.seed_recent_window("TEST-MOTOR", count=50)
        
        response = self.client.post("/api/change-detection/analyze/TEST-MOTOR")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Insufficient historical data", response.json()["detail"])

    def test_multiple_machines_separate_baselines(self):
        """12. Separate machines maintain completely isolated baselines."""
        # Motor: normal power = 1.9kW
        self.seed_historical_baseline("TEST-MOTOR")
        
        # Pump: normal power = 1.4kW (seeded manually)
        base_time = datetime.datetime.utcnow() - datetime.timedelta(hours=10)
        for i in range(110):
            r = SensorReading(
                machine_id="TEST-PUMP", timestamp=base_time + datetime.timedelta(seconds=i*5),
                voltage=230.0, current=6.0, power=1.4, temperature=41.0, vibration=0.15, power_factor=0.88,
                operating_state="RUNNING"
            )
            self.db.add(r)
        self.db.commit()

        # Seed recent windows
        self.seed_recent_window("TEST-MOTOR", count=50) # normal for Motor (1.9kW)
        self.seed_recent_window("TEST-PUMP", count=50, shift_param="power", shift_val=2.2) # shifted for Pump (1.4 -> 2.2kW)

        # Run analysis
        self.run_multiple_analyses("TEST-MOTOR", count=3)
        res_pump = self.run_multiple_analyses("TEST-PUMP", count=3)

        self.assertEqual(len(res_pump.json()), 1)
        self.assertEqual(res_pump.json()[0]["parameter"], "power")
        
        # Motor changes list should be empty
        res_motor = self.client.get("/api/change-detection/machines/TEST-MOTOR/changes")
        self.assertEqual(len(res_motor.json()), 0)

    def test_duplicate_active_change_prevention(self):
        """13. Subsequent check runs increment counts rather than duplicate active events."""
        self.seed_historical_baseline("TEST-MOTOR")
        self.seed_recent_window("TEST-MOTOR", count=50, shift_param="power", shift_val=2.4)
        
        # Run analysis 5 times
        self.run_multiple_analyses("TEST-MOTOR", count=5)
        
        active_events = self.db.query(BehaviorChange).filter(BehaviorChange.machine_id == "TEST-MOTOR", BehaviorChange.status == "ACTIVE").all()
        self.assertEqual(len(active_events), 1)
        self.assertEqual(active_events[0].persistence_count, 5)

    def test_change_resolution(self):
        """14. Setting values back to baseline marks active alerts as RESOLVED."""
        self.seed_historical_baseline("TEST-MOTOR")
        self.seed_recent_window("TEST-MOTOR", count=50, shift_param="power", shift_val=2.4)
        
        # 1. Trigger active changes
        self.run_multiple_analyses("TEST-MOTOR", count=3)
        res1 = self.client.get("/api/change-detection/machines/TEST-MOTOR/changes")
        self.assertEqual(len(res1.json()), 1)
        
        # 2. Reset recent window back to normal baseline
        readings = self.db.query(SensorReading).filter(SensorReading.machine_id == "TEST-MOTOR").order_by(SensorReading.id.desc()).limit(50).all()
        for r in readings:
            r.power = 1.9
        self.db.commit()
        
        # 3. Analyze again to trigger resolution
        self.client.post("/api/change-detection/analyze/TEST-MOTOR")
        
        res2 = self.client.get("/api/change-detection/machines/TEST-MOTOR/changes")
        self.assertEqual(len(res2.json()), 0)
        
        # Verify status resolves to RESOLVED in database
        ev = self.db.query(BehaviorChange).filter(BehaviorChange.machine_id == "TEST-MOTOR", BehaviorChange.parameter == "power").first()
        self.assertEqual(ev.status, "RESOLVED")

if __name__ == "__main__":
    unittest.main()
