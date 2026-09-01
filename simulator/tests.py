import unittest
import json
import datetime
import sys
import os

# Add the parent directory of this script to the Python module search path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from simulator.config import MACHINES, PROFILES
from simulator.machines import Machine
from simulator.sensor_generator import generate_sensor_data
from simulator.fault_simulator import register_machines, inject_fault, clear_fault, get_active_fault

class TestGridLiteSimulator(unittest.TestCase):
    def setUp(self):
        # Create test machine instances
        self.machines = {}
        for m_cfg in MACHINES:
            m_id = m_cfg["machine_id"]
            self.machines[m_id] = Machine(
                machine_id=m_id,
                machine_name=m_cfg["machine_name"],
                machine_type=m_cfg["machine_type"],
                location=m_cfg["location"]
            )
        register_machines(self.machines)

    def test_machine_initialization(self):
        """Verify machines initialize in OFF state with correct attributes."""
        for m_id, machine in self.machines.items():
            self.assertEqual(machine.machine_id, m_id)
            self.assertEqual(machine.operating_state, "OFF")
            self.assertIsNone(machine.active_fault)
            self.assertEqual(machine.time_in_state, 0)

    def test_state_changes(self):
        """Verify operating states are correctly applied and validated."""
        machine = self.machines["MOTOR-01"]
        
        # Valid state changes
        machine.set_state("STARTING")
        self.assertEqual(machine.operating_state, "STARTING")
        self.assertEqual(machine.time_in_state, 0)
        
        machine.set_state("RUNNING")
        self.assertEqual(machine.operating_state, "RUNNING")
        
        machine.set_state("IDLE")
        self.assertEqual(machine.operating_state, "IDLE")
        
        machine.set_state("OFF")
        self.assertEqual(machine.operating_state, "OFF")
        
        # Invalid state change
        with self.assertRaises(ValueError):
            machine.set_state("BLOCKED")

    def test_sensor_data_schema(self):
        """Verify all required sensor schema fields exist and serialize to JSON."""
        machine = self.machines["MOTOR-01"]
        machine.set_state("RUNNING")
        
        data = generate_sensor_data(machine)
        
        # Check required fields
        required_fields = [
            "timestamp", "machine_id", "machine_type", "location",
            "voltage", "current", "power", "temperature", 
            "vibration", "power_factor", "operating_state"
        ]
        for field in required_fields:
            self.assertIn(field, data)
            
        # Check type correctness
        self.assertEqual(data["machine_id"], "MOTOR-01")
        self.assertEqual(data["machine_type"], "Motor")
        self.assertEqual(data["location"], "Production Line A")
        self.assertEqual(data["operating_state"], "RUNNING")
        self.assertIsInstance(data["voltage"], float)
        self.assertIsInstance(data["current"], float)
        self.assertIsInstance(data["power"], float)
        self.assertIsInstance(data["temperature"], float)
        self.assertIsInstance(data["vibration"], float)
        self.assertIsInstance(data["power_factor"], float)
        
        # Verify JSON serialization works
        json_str = json.dumps(data)
        decoded = json.loads(json_str)
        self.assertEqual(decoded["machine_id"], "MOTOR-01")
        
        # Verify ISO timestamp parsing
        parsed_time = datetime.datetime.fromisoformat(data["timestamp"])
        self.assertIsInstance(parsed_time, datetime.datetime)

    def test_physical_calculations_correlation(self):
        """Verify electric correlation formula: Power = Voltage * Current * PF / 1000."""
        machine = self.machines["COMPRESSOR-01"]
        machine.set_state("RUNNING")
        
        data = generate_sensor_data(machine)
        
        # Extract variables
        v = data["voltage"]
        i = data["current"]
        p = data["power"]
        pf = data["power_factor"]
        
        # Assert correlation
        expected_power = (v * i * pf) / 1000.0
        # Check accuracy within small margin of noise (e.g. 0.08 A noise)
        self.assertAlmostEqual(p, expected_power, delta=0.05)

    def test_off_state_values(self):
        """Verify sensor values when the machine is OFF."""
        machine = self.machines["PUMP-01"]
        machine.set_state("OFF")
        
        data = generate_sensor_data(machine)
        
        self.assertEqual(data["voltage"], 0.0)
        self.assertEqual(data["current"], 0.0)
        self.assertEqual(data["power"], 0.0)
        self.assertEqual(data["power_factor"], 0.0)
        # Vibration should decay to zero
        self.assertAlmostEqual(data["vibration"], 0.0, delta=0.01)

    def test_fault_injection_propagation_and_recovery(self):
        """Verify fault injection alters targets gradually and clear_fault recovers them."""
        machine = self.machines["MOTOR-01"]
        machine.set_state("RUNNING")
        
        # Let the machine warm up to stable running values
        for _ in range(15):
            machine.step()
            generate_sensor_data(machine)
            
        # 1. Baseline reading (normal operation)
        baseline = generate_sensor_data(machine)
        base_vib = baseline["vibration"]
        base_power = baseline["power"]
        
        # 2. Inject mechanical degradation fault
        inject_fault("MOTOR-01", "MECHANICAL_DEGRADATION")
        self.assertEqual(get_active_fault("MOTOR-01"), "MECHANICAL_DEGRADATION")
        
        # Run 5 steps to allow fault parameters to start rising
        for _ in range(5):
            machine.step()
            generate_sensor_data(machine)
        mid_fault_data = generate_sensor_data(machine)
        
        # Run 20 steps to fully saturate fault parameters (severity = 1.0)
        for _ in range(20):
            machine.step()
            generate_sensor_data(machine)
        max_fault_data = generate_sensor_data(machine)
        
        # Verify gradual rise: baseline < mid_fault < max_fault
        self.assertGreater(mid_fault_data["vibration"], base_vib)
        self.assertGreater(max_fault_data["vibration"], mid_fault_data["vibration"])
        self.assertGreater(max_fault_data["power"], base_power)
        
        # 3. Clear fault
        clear_fault("MOTOR-01")
        self.assertIsNone(get_active_fault("MOTOR-01"))
        
        # Run another 20 steps to allow thermal and vibration physics to decay to normal
        for _ in range(20):
            machine.step()
            generate_sensor_data(machine)
        recovered_data = generate_sensor_data(machine)
        
        # Verify parameters returned toward normal profiles
        self.assertLess(recovered_data["vibration"], max_fault_data["vibration"])
        self.assertAlmostEqual(recovered_data["vibration"], base_vib, delta=0.05)

if __name__ == "__main__":
    unittest.main()
