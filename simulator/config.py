# Simulation Configuration

# Default update interval in seconds
SIMULATION_INTERVAL = 1.0

import os

# Backend integration configuration (Phase 3)
SEND_TO_BACKEND = True
BACKEND_URL = os.getenv("GRIDLITE_BACKEND_URL", "http://127.0.0.1:8000/api/readings")


# Ambient temperature in degrees Celsius
AMBIENT_TEMP = 23.0

# Base noise standard deviation factor for sensor readings
NOISE_FACTOR = 0.02

# List of simulated machines
MACHINES = [
    {
        "machine_id": "MOTOR-01",
        "machine_name": "Motor 01",
        "machine_type": "Motor",
        "location": "Production Line A",
    },
    {
        "machine_id": "MOTOR-02",
        "machine_name": "Motor 02",
        "machine_type": "Motor",
        "location": "Production Line A",
    },
    {
        "machine_id": "PUMP-01",
        "machine_name": "Pump 01",
        "machine_type": "Pump",
        "location": "Production Line B",
    },
    {
        "machine_id": "PUMP-02",
        "machine_name": "Pump 02",
        "machine_type": "Pump",
        "location": "Production Line B",
    },
    {
        "machine_id": "COMPRESSOR-01",
        "machine_name": "Compressor 01",
        "machine_type": "Compressor",
        "location": "Utility Area",
    },
    {
        "machine_id": "CONVEYOR-01",
        "machine_name": "Conveyor 01",
        "machine_type": "Conveyor",
        "location": "Production Line A",
    }
]

# Normal operating profiles for each machine type
PROFILES = {
    "Motor": {
        "voltage": {"min": 220.0, "max": 240.0, "nominal": 230.0},
        "power": {"min": 1.5, "max": 2.5, "nominal": 2.0},
        "temperature": {"min": 35.0, "max": 50.0, "nominal": 42.5},
        "vibration": {"min": 0.08, "max": 0.20, "nominal": 0.14},
        "power_factor": {"min": 0.85, "max": 0.97, "nominal": 0.91},
    },
    "Pump": {
        "voltage": {"min": 220.0, "max": 240.0, "nominal": 230.0},
        "power": {"min": 1.0, "max": 2.0, "nominal": 1.5},
        "temperature": {"min": 35.0, "max": 48.0, "nominal": 41.5},
        "vibration": {"min": 0.08, "max": 0.22, "nominal": 0.15},
        "power_factor": {"min": 0.82, "max": 0.95, "nominal": 0.885},
    },
    "Compressor": {
        "voltage": {"min": 220.0, "max": 240.0, "nominal": 230.0},
        "power": {"min": 2.0, "max": 4.0, "nominal": 3.0},
        "temperature": {"min": 40.0, "max": 60.0, "nominal": 50.0},
        "vibration": {"min": 0.10, "max": 0.25, "nominal": 0.175},
        "power_factor": {"min": 0.80, "max": 0.94, "nominal": 0.87},
    },
    "Conveyor": {
        "voltage": {"min": 220.0, "max": 240.0, "nominal": 230.0},
        "power": {"min": 0.8, "max": 1.8, "nominal": 1.3},
        "temperature": {"min": 30.0, "max": 45.0, "nominal": 37.5},
        "vibration": {"min": 0.05, "max": 0.18, "nominal": 0.115},
        "power_factor": {"min": 0.85, "max": 0.96, "nominal": 0.905},
    }
}

# State specific configurations relative to nominal values
STATE_FACTORS = {
    "OFF": {
        "voltage_mult": 0.0,
        "power_mult": 0.0,
        "pf_mult": 0.0,
        "temp_target": AMBIENT_TEMP,
        "vib_mult": 0.0
    },
    "STARTING": {
        "voltage_mult": 0.97, # slight voltage dip
        "power_mult": 2.2,    # high power spike
        "pf_mult": 0.7,      # degraded power factor at startup
        "temp_target_offset": 2.0, # starting to warm up
        "vib_mult": 2.5       # vibration spike during transient
    },
    "IDLE": {
        "voltage_mult": 1.0,
        "power_mult": 0.15,   # low power draw when idling
        "pf_mult": 0.6,      # lower power factor at low loads
        "temp_target_offset": -5.0, # runs cooler than running state
        "vib_mult": 0.25      # low vibration when idling
    },
    "RUNNING": {
        "voltage_mult": 1.0,
        "power_mult": 1.0,
        "pf_mult": 1.0,
        "temp_target_offset": 0.0,
        "vib_mult": 1.0
    }
}
