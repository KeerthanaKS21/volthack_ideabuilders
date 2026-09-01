"""
Autonomous Cloud Telemetry Background Simulator (GridLite 24/7 Self-Sustaining Service)
Enables cloud deployments on Render / Railway / Fly.io / EC2 to continuously
simulate physical telemetry, anomalies, behavioral changes, energy drift,
and diagnostic events in the background without needing a local CLI terminal running.
"""

import os
import time
import math
import random
import asyncio
import datetime
import logging
from typing import Dict, Any, Optional

from app.database import SessionLocal
from app.schemas import SensorReadingCreate
from app.pipeline.pipeline_service import PipelineService

logger = logging.getLogger("gridlite.auto_simulator")

# Ambient conditions
AMBIENT_TEMP = 23.0
NOISE_FACTOR = 0.02

# Last external post timestamp tracker
last_external_ingest_time: float = 0.0

def record_external_ingest():
    """Called whenever an external client POSTs to /api/readings."""
    global last_external_ingest_time
    last_external_ingest_time = time.time()

# Machine Profiles
PROFILES = {
    "Motor": {
        "voltage": {"nominal": 400.0, "noise": 3.0},
        "power": {"nominal": 2.0, "noise": 0.05},
        "power_factor": {"nominal": 0.90, "noise": 0.02},
        "temperature": {"nominal": 42.0, "noise": 0.5},
        "vibration": {"nominal": 0.15, "noise": 0.02},
    },
    "Pump": {
        "voltage": {"nominal": 400.0, "noise": 3.0},
        "power": {"nominal": 1.5, "noise": 0.04},
        "power_factor": {"nominal": 0.88, "noise": 0.02},
        "temperature": {"nominal": 40.0, "noise": 0.5},
        "vibration": {"nominal": 0.15, "noise": 0.02},
    },
    "Compressor": {
        "voltage": {"nominal": 400.0, "noise": 4.0},
        "power": {"nominal": 3.0, "noise": 0.08},
        "power_factor": {"nominal": 0.86, "noise": 0.03},
        "temperature": {"nominal": 50.0, "noise": 0.8},
        "vibration": {"nominal": 0.18, "noise": 0.02},
    },
    "Conveyor": {
        "voltage": {"nominal": 400.0, "noise": 3.0},
        "power": {"nominal": 1.3, "noise": 0.03},
        "power_factor": {"nominal": 0.90, "noise": 0.02},
        "temperature": {"nominal": 36.0, "noise": 0.4},
        "vibration": {"nominal": 0.12, "noise": 0.015},
    }
}

STATE_FACTORS = {
    "OFF": {
        "voltage_mult": 0.0,
        "power_mult": 0.0,
        "pf_mult": 0.0,
        "temp_target": AMBIENT_TEMP,
        "vib_mult": 0.0
    },
    "STARTING": {
        "voltage_mult": 0.96,
        "power_mult": 2.2,
        "pf_mult": 0.65,
        "temp_target_offset": 3.0,
        "vib_mult": 1.8
    },
    "IDLE": {
        "voltage_mult": 1.0,
        "power_mult": 0.35,
        "pf_mult": 0.70,
        "temp_target_offset": -5.0,
        "vib_mult": 0.5
    },
    "RUNNING": {
        "voltage_mult": 1.0,
        "power_mult": 1.0,
        "pf_mult": 1.0,
        "temp_target_offset": 0.0,
        "vib_mult": 1.0
    }
}

class AutoMachine:
    def __init__(self, machine_id: str, machine_name: str, machine_type: str, location: str):
        self.machine_id = machine_id
        self.machine_name = machine_name
        self.machine_type = machine_type
        self.location = location
        self.operating_state = "RUNNING"
        self.time_in_state = 0
        self.state_durations = {
            "RUNNING": random.randint(40, 100),
            "IDLE": random.randint(10, 20),
            "STARTING": 3,
            "OFF": random.randint(5, 15)
        }
        self.last_temperature = AMBIENT_TEMP + 10.0
        self.last_vibration = 0.12
        self.active_fault = None
        self.fault_duration = 0

    def step(self):
        self.time_in_state += 1
        if self.active_fault:
            self.fault_duration += 1
        
        # State machine transition
        current_max = self.state_durations.get(self.operating_state, 60)
        if self.time_in_state >= current_max:
            if self.operating_state == "RUNNING":
                self.operating_state = "IDLE" if random.random() < 0.7 else "RUNNING"
                self.state_durations["IDLE"] = random.randint(10, 25)
            elif self.operating_state == "IDLE":
                self.operating_state = "RUNNING"
                self.state_durations["RUNNING"] = random.randint(40, 100)
            elif self.operating_state == "OFF":
                self.operating_state = "STARTING"
            elif self.operating_state == "STARTING":
                self.operating_state = "RUNNING"
            self.time_in_state = 0

    def generate_reading(self) -> dict:
        profile = PROFILES.get(self.machine_type, PROFILES["Motor"])
        state = self.operating_state
        factors = STATE_FACTORS[state]
        
        v_nom = profile["voltage"]["nominal"]
        p_nom = profile["power"]["nominal"]
        pf_nom = profile["power_factor"]["nominal"]
        t_nom = profile["temperature"]["nominal"]
        vib_nom = profile["vibration"]["nominal"]
        
        target_voltage = v_nom * factors["voltage_mult"]
        target_power = p_nom * factors["power_mult"]
        target_pf = pf_nom * factors["pf_mult"]
        
        if "temp_target" in factors:
            target_temp = factors["temp_target"]
        else:
            target_temp = t_nom + factors["temp_target_offset"]
            
        target_vib = vib_nom * factors["vib_mult"]
        
        # Fault effects
        if self.active_fault and state != "OFF":
            severity = min(self.fault_duration / 15.0, 1.0)
            if self.active_fault == "OVERLOAD":
                target_power *= (1.0 + severity * 0.55)
                target_temp += (severity * 20.0)
                target_vib *= (1.0 + severity * 0.25)
            elif self.active_fault == "OVERHEATING":
                target_temp += (severity * 35.0)
                target_power *= (1.0 + severity * 0.05)
            elif self.active_fault == "MECHANICAL_DEGRADATION":
                target_vib *= (1.0 + severity * 2.8)
                target_power *= (1.0 + severity * 0.20)
                target_temp += (severity * 12.0)
            elif self.active_fault == "VOLTAGE_UNBALANCE":
                target_voltage *= (1.0 + (1 if self.fault_duration % 2 == 0 else -1) * severity * 0.15)
                target_power *= (1.0 + severity * 0.15)
                target_temp += (severity * 10.0)
            elif self.active_fault == "POWER_FACTOR_DROP":
                target_pf = max(0.50, target_pf * (1.0 - severity * 0.35))
                target_power *= (1.0 + severity * 0.25)
                target_temp += (severity * 8.0)

        # Smooth gradual physical inertia
        if state == "OFF":
            self.last_temperature += (AMBIENT_TEMP - self.last_temperature) * 0.08
            self.last_vibration += (0.0 - self.last_vibration) * 0.3
        else:
            self.last_temperature += (target_temp - self.last_temperature) * 0.12
            self.last_vibration += (target_vib - self.last_vibration) * 0.25
            
        noise_v = random.gauss(0, profile["voltage"]["noise"])
        noise_p = random.gauss(0, profile["power"]["noise"])
        noise_pf = random.gauss(0, profile["power_factor"]["noise"])
        noise_t = random.gauss(0, profile["temperature"]["noise"])
        noise_vib = random.gauss(0, profile["vibration"]["noise"])
        
        voltage = max(0.0, target_voltage + noise_v) if state != "OFF" else 0.0
        power = max(0.0, target_power + noise_p) if state != "OFF" else 0.0
        power_factor = min(1.0, max(0.0, target_pf + noise_pf)) if state != "OFF" else 0.0
        temperature = max(AMBIENT_TEMP, self.last_temperature + noise_t)
        vibration = max(0.0, self.last_vibration + noise_vib)
        
        # Calculate current: I = P / (V * PF * sqrt(3))
        if voltage > 0 and power_factor > 0:
            current = (power * 1000.0) / (voltage * power_factor * math.sqrt(3))
        else:
            current = 0.0
            
        return {
            "machine_id": self.machine_id,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "voltage": round(voltage, 2),
            "current": round(current, 2),
            "power": round(power, 3),
            "temperature": round(temperature, 2),
            "vibration": round(vibration, 4),
            "power_factor": round(power_factor, 3),
            "operating_state": self.operating_state
        }

AUTO_MACHINES = [
    AutoMachine("MOTOR-01", "Motor 01", "Motor", "Production Line A"),
    AutoMachine("MOTOR-02", "Motor 02", "Motor", "Production Line A"),
    AutoMachine("PUMP-01", "Pump 01", "Pump", "Production Line B"),
    AutoMachine("PUMP-02", "Pump 02", "Pump", "Production Line B"),
    AutoMachine("COMPRESSOR-01", "Compressor 01", "Compressor", "Utility Room"),
    AutoMachine("CONVEYOR-01", "Conveyor 01", "Conveyor", "Assembly Line")
]

# Initialize with persistent demonstration faults active continuously
AUTO_MACHINES[1].active_fault = "MECHANICAL_DEGRADATION" # MOTOR-02 (Critical - High Vibration)
AUTO_MACHINES[1].fault_duration = 15
AUTO_MACHINES[4].active_fault = "OVERHEATING"             # COMPRESSOR-01 (Attention - High Temp)
AUTO_MACHINES[4].fault_duration = 12
AUTO_MACHINES[2].active_fault = "POWER_FACTOR_DROP"      # PUMP-01 (Watch - Low Power Factor)
AUTO_MACHINES[2].fault_duration = 10

def inject_simulator_fault(machine_id: str, fault_type: str):
    """Manually inject a fault into a simulated machine."""
    target = next((m for m in AUTO_MACHINES if m.machine_id.upper() == machine_id.upper()), None)
    if target:
        target.active_fault = fault_type.upper()
        target.fault_duration = 10
        return True
    return False

def clear_all_simulator_faults():
    """Clear all active simulator faults."""
    for m in AUTO_MACHINES:
        m.active_fault = None
        m.fault_duration = 0

def run_telemetry_simulation():
    """
    Continuous background thread that automatically ingests simulated telemetry 24/7 with persistent faults.
    """
    import sys
    if "unittest" in sys.modules:
        logger.info("Unit tests active; skipping autonomous telemetry loop.")
        return

    logger.info("Starting GridLite 24/7 Autonomous Cloud Telemetry Simulator Thread...")
    time.sleep(1.0)
    
    while True:
        try:
            # Maintain demonstration faults unless cleared
            if AUTO_MACHINES[1].active_fault is None:
                AUTO_MACHINES[1].active_fault = "MECHANICAL_DEGRADATION"
                AUTO_MACHINES[1].fault_duration = 15
            if AUTO_MACHINES[4].active_fault is None:
                AUTO_MACHINES[4].active_fault = "OVERHEATING"
                AUTO_MACHINES[4].fault_duration = 12
            if AUTO_MACHINES[2].active_fault is None:
                AUTO_MACHINES[2].active_fault = "POWER_FACTOR_DROP"
                AUTO_MACHINES[2].fault_duration = 10
            
            # Step and ingest for all 6 machines
            db = SessionLocal()
            try:
                for machine in AUTO_MACHINES:
                    machine.step()
                    raw_data = machine.generate_reading()
                    reading_create = SensorReadingCreate(**raw_data)
                    PipelineService.ingest_and_process(db, reading_create)
            except Exception as ex:
                logger.error(f"Error ingesting simulated step: {ex}")
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error in autonomous telemetry background task: {e}")
            
        time.sleep(2.0)

_simulator_started = False

def start_simulator_daemon():
    """Starts background telemetry simulator thread that runs 24/7."""
    global _simulator_started
    import sys
    if "unittest" in sys.modules or _simulator_started:
        return
    _simulator_started = True
    
    import threading
    t = threading.Thread(target=run_telemetry_simulation, daemon=True, name="GridLite-Cloud-Simulator")
    t.start()
    logger.info("GridLite 24/7 Simulator Daemon Thread started.")


