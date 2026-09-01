import unittest
import os
import shutil
import datetime
import json
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, StaticPool
from sqlalchemy.orm import sessionmaker

# Set sys.path to resolve backend app correctly
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Define and override test models directory BEFORE importing ModelManager
TEST_MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_models")
os.makedirs(TEST_MODEL_DIR, exist_ok=True)

import app.ml.config
app.ml.config.MODEL_DIR = TEST_MODEL_DIR

from app.main import app
from app.database import Base, get_db
from app.models import Machine, SensorReading, Anomaly
from app.ml.model_manager import ModelManager

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

class TestGridLiteMLPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_model_dir = TEST_MODEL_DIR
        os.makedirs(cls.temp_model_dir, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.temp_model_dir):
            shutil.rmtree(cls.temp_model_dir)

    def setUp(self):
        # Recreate tables in memory SQLite
        engine = TestingSessionLocal().bind
        Base.metadata.create_all(bind=engine)
        
        self.client = TestClient(app)
        self.db = TestingSessionLocal()
        
        # Clean model directory
        for f in os.listdir(self.temp_model_dir):
            os.remove(os.path.join(self.temp_model_dir, f))
            
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

    def seed_readings(self, machine_id, count, is_abnormal=False):
        """Seed time-series telemetry data for testing."""
        base_time = datetime.datetime.utcnow() - datetime.timedelta(hours=5)
        for i in range(count):
            # Introduce anomalies if flagged, otherwise stay within standard normal limits
            if is_abnormal:
                voltage = 190.0 if i % 2 == 0 else 260.0
                current = 15.0
                power = 3.5
                temperature = 65.0
                vibration = 0.35
                pf = 0.50
            else:
                voltage = 230.0 + (i % 5) - 2 # 228V - 232V
                current = 8.0 + (i % 3) * 0.1 # 8.0A - 8.2A
                power = 1.8 + (i % 2) * 0.1 # 1.8kW - 1.9kW
                temperature = 40.0 + (i % 4) # 40C - 43C
                vibration = 0.12 + (i % 3) * 0.01 # 0.12 - 0.14
                pf = 0.90 + (i % 2) * 0.02 # 0.90 - 0.92

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

    def test_training_sufficient_data(self):
        """1. Train with sufficient normal readings."""
        self.seed_readings("TEST-MOTOR", 110, is_abnormal=False)
        response = self.client.post("/api/anomaly/train/TEST-MOTOR")
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertEqual(data["machine_id"], "TEST-MOTOR")
        self.assertEqual(data["status"], "trained")
        self.assertEqual(data["training_samples"], 110)
        self.assertTrue(os.path.exists(os.path.join(self.temp_model_dir, "TEST-MOTOR.pkl")))

    def test_training_insufficient_data(self):
        """2. Assert training fails if readings count < MIN_TRAINING_SAMPLES."""
        self.seed_readings("TEST-MOTOR", 45, is_abnormal=False)
        response = self.client.post("/api/anomaly/train/TEST-MOTOR")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Insufficient normal training data", response.json()["detail"])

    def test_prediction_with_normal_reading(self):
        """3. Prediction checks for normal values return NORMAL severity."""
        self.seed_readings("TEST-MOTOR", 110, is_abnormal=False)
        self.client.post("/api/anomaly/train/TEST-MOTOR")
        
        payload = {
            "machine_id": "TEST-MOTOR",
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "voltage": 230.0,
            "current": 8.0,
            "power": 1.85,
            "temperature": 41.5,
            "vibration": 0.125,
            "power_factor": 0.91,
            "operating_state": "RUNNING"
        }
        
        response = self.client.post("/api/readings", json=payload)
        self.assertEqual(response.status_code, 201)
        
        data = response.json()
        self.assertIn("anomaly", data)
        self.assertFalse(data["anomaly"]["is_anomaly"])
        self.assertEqual(data["anomaly"]["severity"], "NORMAL")

    def test_prediction_with_abnormal_reading(self):
        """4. Prediction checks for out-of-bounds metrics flag anomaly and returns deviations."""
        self.seed_readings("TEST-MOTOR", 110, is_abnormal=False)
        self.client.post("/api/anomaly/train/TEST-MOTOR")
        
        # Post a reading with double normal vibration and power spikes
        payload = {
            "machine_id": "TEST-MOTOR",
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "voltage": 230.0,
            "current": 16.0,
            "power": 3.70,
            "temperature": 55.0,
            "vibration": 0.380,
            "power_factor": 0.90,
            "operating_state": "RUNNING"
        }
        
        response = self.client.post("/api/readings", json=payload)
        self.assertEqual(response.status_code, 201)
        
        data = response.json()
        self.assertIn("anomaly", data)
        self.assertTrue(data["anomaly"]["is_anomaly"])
        self.assertNotEqual(data["anomaly"]["severity"], "NORMAL")
        self.assertIn("vibration", data["anomaly"]["parameter_deviations"])
        
        # Check deviations parsing
        vibration_dev = data["anomaly"]["parameter_deviations"]["vibration"]
        self.assertTrue(vibration_dev.startswith("+"))

    def test_missing_model_handling(self):
        """5. Unconfigured machine models return 'not_available' without failing request."""
        payload = {
            "machine_id": "TEST-MOTOR",
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "voltage": 230.0,
            "current": 8.0,
            "power": 1.85,
            "temperature": 41.5,
            "vibration": 0.125,
            "power_factor": 0.91,
            "operating_state": "RUNNING"
        }
        
        response = self.client.post("/api/readings", json=payload)
        self.assertEqual(response.status_code, 201)
        
        data = response.json()
        self.assertEqual(data["anomaly"]["status"], "not_available")

    def test_invalid_sensor_values(self):
        """6. Assert schema validation flags negative voltages or invalid power factors."""
        payload = {
            "machine_id": "TEST-MOTOR",
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "voltage": -230.0, # INVALID
            "current": 8.0,
            "power": 1.85,
            "temperature": 41.5,
            "vibration": 0.125,
            "power_factor": 1.15, # INVALID
            "operating_state": "RUNNING"
        }
        response = self.client.post("/api/readings", json=payload)
        self.assertEqual(response.status_code, 422)

    def test_multiple_machines_separate_models(self):
        """7. Verify models exist separately on disk for different machines."""
        self.seed_readings("TEST-MOTOR", 110)
        self.seed_readings("TEST-PUMP", 110)
        
        res1 = self.client.post("/api/anomaly/train/TEST-MOTOR")
        res2 = self.client.post("/api/anomaly/train/TEST-PUMP")
        
        self.assertEqual(res1.status_code, 200)
        self.assertEqual(res2.status_code, 200)
        self.assertTrue(ModelManager.model_exists("TEST-MOTOR"))
        self.assertTrue(ModelManager.model_exists("TEST-PUMP"))

    def test_model_loading_metadata(self):
        """8. Verify serialized model returns correct training sample counts and timestamp."""
        self.seed_readings("TEST-MOTOR", 105)
        self.client.post("/api/anomaly/train/TEST-MOTOR")
        
        info = ModelManager.get_model_info("TEST-MOTOR")
        self.assertIsNotNone(info)
        self.assertEqual(info["training_samples"], 105)
        self.assertEqual(info["machine_id"], "TEST-MOTOR")
        self.assertIn("trained_at", info)

    def test_duplicate_anomaly_prevention(self):
        """9. Ensure anomalies table database constraint prevents duplicate records for a single reading."""
        # 1. Train model
        self.seed_readings("TEST-MOTOR", 110)
        self.client.post("/api/anomaly/train/TEST-MOTOR")
        
        # 2. Add an anomaly linked to a reading ID manually
        r = SensorReading(
            machine_id="TEST-MOTOR",
            timestamp=datetime.datetime.utcnow(),
            voltage=230.0, current=8.0, power=1.85, temperature=41.5, vibration=0.125, power_factor=0.91,
            operating_state="RUNNING"
        )
        self.db.add(r)
        self.db.commit()
        
        anom1 = Anomaly(
            machine_id="TEST-MOTOR",
            anomaly_score=0.85,
            severity="HIGH",
            affected_parameters="{}",
            reading_id=r.id
        )
        self.db.add(anom1)
        self.db.commit()
        
        # Try inserting same reading_id
        anom2 = Anomaly(
            machine_id="TEST-MOTOR",
            anomaly_score=0.92,
            severity="HIGH",
            affected_parameters="{}",
            reading_id=r.id
        )
        self.db.add(anom2)
        
        from sqlalchemy.exc import IntegrityError
        with self.assertRaises(IntegrityError):
            self.db.commit()

    def test_backend_continues_if_ml_fails(self):
        """10. Telemetry data continues saving successfully even if ML model loader crashes."""
        self.seed_readings("TEST-MOTOR", 110)
        self.client.post("/api/anomaly/train/TEST-MOTOR")
        
        payload = {
            "machine_id": "TEST-MOTOR",
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "voltage": 230.0,
            "current": 8.0,
            "power": 1.85,
            "temperature": 41.5,
            "vibration": 0.125,
            "power_factor": 0.91,
            "operating_state": "RUNNING"
        }
        
        # Mock load_model to raise RuntimeError
        with patch("app.ml.model_manager.ModelManager.load_model", side_effect=RuntimeError("Corrupted pickle file")):
            response = self.client.post("/api/readings", json=payload)
            self.assertEqual(response.status_code, 201)
            
            data = response.json()
            self.assertEqual(data["anomaly"]["status"], "error")
            self.assertIn("Anomaly detection failed", data["anomaly"]["reason"])
            
            # Verify reading was successfully saved in DB
            db_reading = self.db.query(SensorReading).filter(SensorReading.machine_id == "TEST-MOTOR").order_by(SensorReading.id.desc()).first()
            self.assertIsNotNone(db_reading)
            self.assertEqual(db_reading.voltage, 230.0)

if __name__ == "__main__":
    unittest.main()
