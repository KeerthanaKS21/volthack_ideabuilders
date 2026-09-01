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
