import unittest
import requests
import datetime
import time

BACKEND_URL = "http://localhost:8000"

class TestGridLiteBackend(unittest.TestCase):
    def test_01_health(self):
        """Verify the health endpoint is active."""
        response = requests.get(f"{BACKEND_URL}/api/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["service"], "GridLite Backend")

    def test_02_machines_seeded(self):
        """Verify that the 6 default virtual machines are seeded and returned."""
        response = requests.get(f"{BACKEND_URL}/api/machines")
        self.assertEqual(response.status_code, 200)
        machines = response.json()
        
        # Check that we have exactly 6 machines
        self.assertEqual(len(machines), 6)
        
        # Verify machine details exist
        machine_ids = [m["machine_id"] for m in machines]
        expected_ids = ["MOTOR-01", "MOTOR-02", "PUMP-01", "PUMP-02", "COMPRESSOR-01", "CONVEYOR-01"]
        for eid in expected_ids:
            self.assertIn(eid, machine_ids)

    def test_03_single_machine_lookup(self):
        """Verify retrieving details of a single machine by ID."""
        response = requests.get(f"{BACKEND_URL}/api/machines/MOTOR-01")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["machine_id"], "MOTOR-01")
        self.assertEqual(data["machine_type"], "Motor")
        
        # Querying an invalid machine ID should yield HTTP 404
        response_invalid = requests.get(f"{BACKEND_URL}/api/machines/UNKNOWN-99")
        self.assertEqual(response_invalid.status_code, 404)

    def test_04_post_sensor_reading(self):
        """Verify posting a new sensor reading and schema validation."""
        timestamp = datetime.datetime.now().isoformat()
        payload = {
            "timestamp": timestamp,
            "machine_id": "MOTOR-01",
            "voltage": 230.5,
            "current": 8.5,
            "power": 1.95,
            "temperature": 42.0,
            "vibration": 0.12,
            "power_factor": 0.92,
            "operating_state": "RUNNING"
        }
        
        response = requests.post(f"{BACKEND_URL}/api/readings", json=payload)
        self.assertEqual(response.status_code, 201)
        data = response.json()
        reading = data.get("reading", data)
        self.assertEqual(reading["machine_id"], "MOTOR-01")
        self.assertEqual(reading["voltage"], 230.5)
        self.assertEqual(reading["operating_state"], "RUNNING")
        self.assertIn("id", reading)

        # Querying with invalid validation schema (negative power factor) should yield HTTP 422
        bad_payload = payload.copy()
        bad_payload["power_factor"] = -0.5
        response_bad = requests.post(f"{BACKEND_URL}/api/readings", json=bad_payload)
        self.assertEqual(response_bad.status_code, 422)

        # Querying with unknown machine ID should yield HTTP 404
        unknown_payload = payload.copy()
        unknown_payload["machine_id"] = "UNKNOWN-99"
        response_unknown = requests.post(f"{BACKEND_URL}/api/readings", json=unknown_payload)
        self.assertEqual(response_unknown.status_code, 404)

    def test_05_get_latest_readings(self):
        """Verify retrieving the latest readings for all machines."""
        response = requests.get(f"{BACKEND_URL}/api/readings/latest")
        self.assertEqual(response.status_code, 200)
        readings = response.json()
        
        # Check that we have received readings (at least the one we posted)
        self.assertGreater(len(readings), 0)
        motor_reading = next((r for r in readings if r["machine_id"] == "MOTOR-01"), None)
        self.assertIsNotNone(motor_reading)
        self.assertEqual(motor_reading["operating_state"], "RUNNING")

    def test_06_get_machine_history(self):
        """Verify retrieving historical readings for a specific machine."""
        response = requests.get(f"{BACKEND_URL}/api/machines/MOTOR-01/readings?limit=10")
        self.assertEqual(response.status_code, 200)
        readings = response.json()
        self.assertGreater(len(readings), 0)
        self.assertEqual(readings[0]["machine_id"], "MOTOR-01")

if __name__ == "__main__":
    print("Executing GridLite API Integration Test Suite...")
    unittest.main()
