import os

# Configuration for GridLite ML Anomaly Detection Engine

# Minimum normal running samples required to train a machine-specific model
MIN_TRAINING_SAMPLES = 100

# Anomaly score thresholds for severity mapping
ANOMALY_THRESHOLD_LOW = 0.50
ANOMALY_THRESHOLD_MEDIUM = 0.62
ANOMALY_THRESHOLD_HIGH = 0.72

# Directory path where model pickle weights will be stored
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) # GridLite/backend/
MODEL_DIR = os.path.join(BASE_DIR, "models")

# Phase 5: Behavioral Change Detection Configuration
RECENT_WINDOW_SIZE = 50
PERSISTENCE_THRESHOLD = 3
CHANGE_DETECTION_INTERVAL = 10

# Machine normal baseline profiles
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
