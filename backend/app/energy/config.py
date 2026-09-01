import os

# Configuration parameters for Phase 6 Energy Intelligence Module

ENERGY_CHANGE_THRESHOLD = 0.10  # 10% threshold above baseline
ENERGY_MIN_DURATION = 3         # Persistence readings count
ENERGY_ANALYSIS_WINDOW = 50     # Size of rolling data evaluation window

DEFAULT_ELECTRICITY_TARIFF = 8.0  # default tariff in ₹ per kWh

# Persistent JSON config file path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TARIFF_CONFIG_PATH = os.path.join(BASE_DIR, "models", "tariff_config.json")
