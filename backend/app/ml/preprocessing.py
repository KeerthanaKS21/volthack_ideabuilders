import numpy as np

# List of telemetry features used in machine learning models
FEATURE_NAMES = ["voltage", "current", "power", "temperature", "vibration", "power_factor"]

def extract_features(readings):
    """
    Extract a 2D list/array of float features from raw DB query objects or dict records.
    Features: voltage, current, power, temperature, vibration, power_factor
    """
    X = []
    for r in readings:
        is_dict = isinstance(r, dict)
        X.append([
            float(r["voltage"] if is_dict else r.voltage),
            float(r["current"] if is_dict else r.current),
            float(r["power"] if is_dict else r.power),
            float(r["temperature"] if is_dict else r.temperature),
            float(r["vibration"] if is_dict else r.vibration),
            float(r["power_factor"] if is_dict else r.power_factor),
        ])
    return np.array(X, dtype=float)
