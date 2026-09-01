# GridLite Health & Investigation Priority Engine Configuration

# Signal Weights for Base Investigation Priority (Must sum to 1.0)
ANOMALY_WEIGHT = 0.25
CHANGE_WEIGHT = 0.25
ENERGY_WEIGHT = 0.20
DIAGNOSIS_WEIGHT = 0.20
PERSISTENCE_WEIGHT = 0.10

# Multi-Signal Correlation Amplification
# When multiple independent signals agree on abnormal behavior, boost the score
MULTI_SIGNAL_BONUS_3 = 10.0  # 3 independent signals active
MULTI_SIGNAL_BONUS_4 = 15.0  # 4 independent signals active

# Health Status Thresholds (Priority Score 0 - 100)
HEALTHY_THRESHOLD = 25     # 0 - 25: HEALTHY
WATCH_THRESHOLD = 50       # 26 - 50: WATCH
ATTENTION_THRESHOLD = 75   # 51 - 75: ATTENTION
# Above 75 (76 - 100): CRITICAL
