import random
from simulator.config import AMBIENT_TEMP, STATE_FACTORS, PROFILES

class Machine:
    def __init__(self, machine_id, machine_name, machine_type, location):
        self.machine_id = machine_id
        self.machine_name = machine_name
        self.machine_type = machine_type
        self.location = location
        
        # Initial operating state
        self.operating_state = "OFF"
        self.time_in_state = 0
        
        # Determine randomized durations for autonomous state cycles
        self.state_durations = {
            "OFF": random.randint(15, 45),
            "STARTING": 3, # Startup transient takes 3 steps
            "IDLE": random.randint(10, 30),
            "RUNNING": random.randint(30, 90)
        }
        
        # Sensor history to allow gradual temperature and vibration shifts
        self.last_temperature = AMBIENT_TEMP
        self.last_vibration = 0.0
        
        # Fault registry
        self.active_fault = None
        self.fault_duration = 0
        
        # Flag to indicate manual state override (stops auto cycle until cleared/restarted)
        self.is_manual_state = False

    def set_state(self, new_state, manual=True):
        """Transition the machine to a new state and reset timers."""
        valid_states = ["OFF", "STARTING", "IDLE", "RUNNING"]
        if new_state not in valid_states:
            raise ValueError(f"Invalid state: {new_state}. Must be one of {valid_states}")
            
        self.operating_state = new_state
        self.time_in_state = 0
        self.is_manual_state = manual
        
        # Randomize durations for the next phases
        if new_state == "RUNNING":
            self.state_durations["RUNNING"] = random.randint(30, 90)
        elif new_state == "IDLE":
            self.state_durations["IDLE"] = random.randint(10, 30)
        elif new_state == "OFF":
            self.state_durations["OFF"] = random.randint(15, 45)

    def inject_fault(self, fault_type):
        """Inject a fault to begin gradual propagation."""
        self.active_fault = fault_type
        self.fault_duration = 0

    def clear_fault(self):
        """Clear active fault."""
        self.active_fault = None
        self.fault_duration = 0

    def step(self):
        """Advance time by one step (1 second) and execute state machine transitions."""
        self.time_in_state += 1
        
        if self.active_fault:
            self.fault_duration += 1
            
            # Prevent autonomous transitions to OFF/IDLE and keep/force RUNNING state
            if self.operating_state not in ["RUNNING", "STARTING"]:
                self.set_state("STARTING", manual=False)
            elif self.operating_state == "STARTING" and self.time_in_state >= self.state_durations["STARTING"]:
                self.set_state("RUNNING", manual=False)
            return # Skip the autonomous state transition check
            
        # Autonomous state transitions (only if not manually overridden)
        if not self.is_manual_state:
            limit = self.state_durations.get(self.operating_state, 10)
            if self.time_in_state >= limit:
                self._transition_next()

    def _transition_next(self):
        """Define the state transition flow: OFF -> STARTING -> RUNNING -> IDLE/OFF."""
        if self.operating_state == "OFF":
            # Off state ends, start up the machine
            self.set_state("STARTING", manual=False)
        elif self.operating_state == "STARTING":
            # Startup phase complete, go to running
            self.set_state("RUNNING", manual=False)
        elif self.operating_state == "RUNNING":
            # Running ends, decide whether to idle or turn off
            next_state = "IDLE" if random.random() < 0.7 else "OFF"
            self.set_state(next_state, manual=False)
        elif self.operating_state == "IDLE":
            # Idle ends, decide whether to run again or turn off
            next_state = "RUNNING" if random.random() < 0.8 else "OFF"
            self.set_state(next_state, manual=False)

    def to_dict(self):
        """Serialize current machine attributes."""
        return {
            "machine_id": self.machine_id,
            "machine_name": self.machine_name,
            "machine_type": self.machine_type,
            "location": self.location,
            "operating_state": self.operating_state,
            "active_fault": self.active_fault
        }
