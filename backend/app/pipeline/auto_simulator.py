"""
Autonomous Cloud Telemetry Background Simulator (GridLite Automated Demo Engine)
Enables cloud deployments on Render and local environments to continuously
simulate realistic multi-parameter physical telemetry, progressive anomaly development,
behavioral drift, energy waste tracking, diagnostic hypotheses, and health prioritization
without requiring any manual terminal commands.
"""

import os
import time
import math
import random
import datetime
import logging
from typing import Dict, Any, Optional

from app.database import SessionLocal
from app.models import SensorReading, Anomaly, BehaviorChange, DiagnosisEvent, UnifiedEvent, MachineHealthEvent
from app.schemas import SensorReadingCreate
from app.pipeline.pipeline_service import PipelineService

logger = logging.getLogger("gridlite.demo_simulator")

# Ambient conditions and physical parameters
AMBIENT_TEMP = 23.0
NOISE_FACTOR = 0.02

# Demo mode configuration (reads from environment, defaults to True on Render/Cloud)
DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() in ("true", "1", "yes")

# Machine Profiles (nominal baseline and sensor noise specifications)
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
            "RUNNING": random.randint(60, 150),
            "IDLE": random.randint(15, 30),
            "STARTING": 3,
            "OFF": random.randint(10, 20)
        }
        self.last_temperature = AMBIENT_TEMP + 10.0
        self.last_vibration = 0.12
        self.active_fault = None
        self.fault_duration = 0

    def step(self):
        self.time_in_state += 1
        if self.active_fault:
            self.fault_duration += 1
            # Maintain active operating state during fault
            if self.operating_state not in ["RUNNING", "STARTING"]:
                self.operating_state = "STARTING"
                self.time_in_state = 0
            elif self.operating_state == "STARTING" and self.time_in_state >= 3:
                self.operating_state = "RUNNING"
                self.time_in_state = 0
            return
        
        # Natural state machine transition when normal
        current_max = self.state_durations.get(self.operating_state, 60)
        if self.time_in_state >= current_max:
            if self.operating_state == "RUNNING":
                self.operating_state = "IDLE" if random.random() < 0.25 else "RUNNING"
                self.state_durations["IDLE"] = random.randint(15, 30)
            elif self.operating_state == "IDLE":
                self.operating_state = "RUNNING"
                self.state_durations["RUNNING"] = random.randint(60, 150)
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
        
        # Progressive physical fault dynamics
        if self.active_fault and state != "OFF":
            severity = min(self.fault_duration / 20.0, 1.0)
            if self.active_fault == "OVERLOAD":
                target_power *= (1.0 + severity * 0.55)
                target_temp += (severity * 20.0)
                target_vib *= (1.0 + severity * 0.25)
            elif self.active_fault == "OVERHEATING":
                target_temp += (severity * 35.0)
                target_power *= (1.0 + severity * 0.08)
            elif self.active_fault == "MECHANICAL_DEGRADATION":
                target_vib *= (1.0 + severity * 2.8) # Vibration rises to ~0.50 mm/s
                target_power *= (1.0 + severity * 0.18) # Friction power draw
                target_temp += (severity * 14.0)       # Bearing friction heat
            elif self.active_fault == "VOLTAGE_UNBALANCE":
                target_voltage *= (1.0 + (1 if self.fault_duration % 2 == 0 else -1) * severity * 0.15)
                target_power *= (1.0 + severity * 0.15)
                target_temp += (severity * 10.0)
            elif self.active_fault == "POWER_FACTOR_DROP":
                target_pf = max(0.52, target_pf * (1.0 - severity * 0.35))
                target_power *= (1.0 + severity * 0.22)
                target_temp += (severity * 8.0)

        # Smooth gradual physical inertia (differential thermal and mechanical response)
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

# Registered virtual machines (identical to standard fleet)
AUTO_MACHINES = [
    AutoMachine("MOTOR-01", "Motor 01", "Motor", "Production Line A"),
    AutoMachine("MOTOR-02", "Motor 02", "Motor", "Production Line A"),
    AutoMachine("PUMP-01", "Pump 01", "Pump", "Production Line B"),
    AutoMachine("PUMP-02", "Pump 02", "Pump", "Production Line B"),
    AutoMachine("COMPRESSOR-01", "Compressor 01", "Compressor", "Utility Room"),
    AutoMachine("CONVEYOR-01", "Conveyor 01", "Conveyor", "Assembly Line")
]

# Scenario state tracking
_scenario_step: int = 0
_total_scenario_steps: int = 110 # Total loop ~220 seconds (~3.6 minutes)
_is_simulation_active: bool = False
_last_prune_step: int = 0

def get_demo_status() -> dict:
    """Return safe operational info about the current automated demo scenario."""
    global _scenario_step, _is_simulation_active, DEMO_MODE
    
    # Calculate current phase based on step
    if _scenario_step <= 30:
        phase = "PHASE_1_NORMAL"
        desc = "All machines operating normally within nominal baseline parameters"
        target = None
        fault = None
    elif _scenario_step <= 65:
        phase = "PHASE_2_DEVELOPING_ABNORMALITY"
        desc = "MOTOR-01 developing progressive mechanical degradation (bearing wear & vibration surge)"
        target = "MOTOR-01"
        fault = "MECHANICAL_DEGRADATION"
    elif _scenario_step <= 85:
        phase = "PHASE_3_PEAK_ABNORMALITY"
        desc = "MOTOR-01 critical anomaly with diagnostic root-cause hypothesis and priority ranking"
        target = "MOTOR-01"
        fault = "MECHANICAL_DEGRADATION"
    else:
        phase = "PHASE_4_RECOVERY"
        desc = "MOTOR-01 recovering toward normal baseline operating state"
        target = "MOTOR-01"
        fault = "RECOVERING"
        
    return {
        "demo_mode": DEMO_MODE,
        "simulation_running": _is_simulation_active,
        "current_phase": phase,
        "phase_description": desc,
        "cycle_step": _scenario_step,
        "total_cycle_steps": _total_scenario_steps,
        "target_machine": target,
        "active_fault": fault
    }

def reset_demo_scenario():
    """Reset the automated demo scenario back to Phase 1 (Step 0) cleanly."""
    global _scenario_step
    _scenario_step = 0
    for m in AUTO_MACHINES:
        m.active_fault = None
        m.fault_duration = 0
        m.operating_state = "RUNNING"
        m.time_in_state = 0
    logger.info("[DEMO] Scenario reset to Phase 1 (Normal Operation)")

def prune_old_telemetry(db, keep_count: int = 3000):
    """Keep SQLite database lightweight by retaining only recent sensor readings."""
    try:
        total = db.query(SensorReading).count()
        if total > keep_count + 500:
            oldest_to_keep = db.query(SensorReading.id)\
                .order_by(SensorReading.timestamp.desc())\
                .offset(keep_count)\
                .first()
            if oldest_to_keep:
                db.query(SensorReading)\
                    .filter(SensorReading.id <= oldest_to_keep[0])\
                    .delete(synchronize_session=False)
                db.commit()
                logger.info(f"[RETENTION] Pruned database: kept latest {keep_count} sensor readings.")
    except Exception as e:
        db.rollback()
        logger.warning(f"[RETENTION] Telemetry prune warning: {e}")

def run_telemetry_simulation():
    """
    Continuous background thread executing the 4-phase repeatable demo scenario.
    Ingests all telemetry through PipelineService so existing ML, Behavior, Energy,
    Diagnosis, Health, and Event engines process every step naturally.
    """
    global _scenario_step, _is_simulation_active, _last_prune_step
    import sys
    if "unittest" in sys.modules:
        logger.info("[DEMO] Unit tests active; skipping autonomous telemetry loop.")
        return

    _is_simulation_active = True
    logger.info("[DEMO] GridLite Automated Cloud Demo Simulator Thread Started (DEMO_MODE=True)")
    time.sleep(1.0)
    
    while True:
        try:
            _scenario_step += 1
            if _scenario_step > _total_scenario_steps:
                _scenario_step = 1
                logger.info("[DEMO] Restarting repeatable scenario loop at Phase 1...")

            motor_01 = next((m for m in AUTO_MACHINES if m.machine_id == "MOTOR-01"), None)
            comp_01 = next((m for m in AUTO_MACHINES if m.machine_id == "COMPRESSOR-01"), None)
            pump_01 = next((m for m in AUTO_MACHINES if m.machine_id == "PUMP-01"), None)

            # Scenario Phase Management
            if _scenario_step <= 30:
                # PHASE 1: Normal Operation (All Healthy)
                if motor_01:
                    motor_01.active_fault = None
                if comp_01:
                    comp_01.active_fault = None
                if pump_01:
                    pump_01.active_fault = None
                    
            elif 31 <= _scenario_step <= 85:
                # PHASE 2 & 3: Developing & Peak Abnormality on MOTOR-01
                if motor_01 and motor_01.active_fault != "MECHANICAL_DEGRADATION":
                    motor_01.active_fault = "MECHANICAL_DEGRADATION"
                    motor_01.fault_duration = 1
                    logger.info("[DEMO] MOTOR-01 mechanical degradation fault initiated (Phase 2)")
                    
                # Introduce secondary minor overheating on COMPRESSOR-01 in Phase 3
                if 60 <= _scenario_step <= 85 and comp_01 and comp_01.active_fault is None:
                    comp_01.active_fault = "OVERHEATING"
                    comp_01.fault_duration = 1
                    
            elif _scenario_step > 85:
                # PHASE 4: Recovery
                if motor_01 and motor_01.active_fault is not None:
                    motor_01.active_fault = None
                    motor_01.fault_duration = 0
                    logger.info("[DEMO] MOTOR-01 fault resolved, entering recovery phase (Phase 4)")
                if comp_01 and comp_01.active_fault is not None:
                    comp_01.active_fault = None
                    comp_01.fault_duration = 0

            # Step and ingest for all 6 machines
            db = SessionLocal()
            try:
                for machine in AUTO_MACHINES:
                    machine.step()
                    raw_data = machine.generate_reading()
                    reading_create = SensorReadingCreate(**raw_data)
                    PipelineService.ingest_and_process(db, reading_create)

                # Periodic retention check every 50 steps
                if _scenario_step - _last_prune_step >= 50:
                    prune_old_telemetry(db, keep_count=3000)
                    _last_prune_step = _scenario_step

            except Exception as ex:
                logger.error(f"[DEMO] Pipeline ingestion error on step {_scenario_step}: {ex}")
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"[DEMO] Unexpected error in background simulation thread: {e}")
            
        time.sleep(2.0)

_simulator_started = False

def start_simulator_daemon():
    """Starts the background telemetry demo simulator thread if DEMO_MODE is enabled."""
    global _simulator_started, DEMO_MODE
    import sys
    if "unittest" in sys.modules or _simulator_started:
        return
        
    if not DEMO_MODE:
        logger.info("[DEMO] DEMO_MODE=False - Skipping autonomous background telemetry daemon.")
        return
        
    _simulator_started = True
    import threading
    t = threading.Thread(target=run_telemetry_simulation, daemon=True, name="GridLite-Cloud-Demo-Simulator")
    t.start()
    logger.info("[DEMO] GridLite 24/7 Demo Simulator Daemon Thread started.")
