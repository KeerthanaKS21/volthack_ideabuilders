import json
import os
from app.energy.config import TARIFF_CONFIG_PATH, DEFAULT_ELECTRICITY_TARIFF

def load_tariff() -> float:
    """Load electricity tariff from persistent JSON configuration file."""
    if os.path.exists(TARIFF_CONFIG_PATH):
        try:
            with open(TARIFF_CONFIG_PATH, "r") as f:
                data = json.load(f)
                val = float(data.get("tariff", DEFAULT_ELECTRICITY_TARIFF))
                return val if val > 0.0 else DEFAULT_ELECTRICITY_TARIFF
        except Exception:
            return DEFAULT_ELECTRICITY_TARIFF
    return DEFAULT_ELECTRICITY_TARIFF

def save_tariff(value: float):
    """Save positive electricity tariff value to persistent JSON configuration file."""
    os.makedirs(os.path.dirname(TARIFF_CONFIG_PATH), exist_ok=True)
    with open(TARIFF_CONFIG_PATH, "w") as f:
        json.dump({"tariff": float(value)}, f)
