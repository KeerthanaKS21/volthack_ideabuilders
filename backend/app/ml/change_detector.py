import numpy as np
from typing import List, Dict, Any

class ChangeDetector:
    @staticmethod
    def analyze_parameter_change(
        param_name: str, 
        recent_values: List[float], 
        baseline_stats: Dict[str, float]
    ) -> Dict[str, Any]:
        """
        Compare a rolling window of recent values with historical baseline stats.
        Returns a dict describing the behavior pattern shift if detected, or None.
        """
        if not baseline_stats or len(recent_values) < 5:
            return None

        baseline_mean = baseline_stats["mean"]
        baseline_std = baseline_stats["std"]
        
        recent_arr = np.array(recent_values, dtype=float)
        recent_mean = float(np.mean(recent_arr))
        recent_std = float(np.std(recent_arr))

        if baseline_mean == 0.0:
            return None

        # 1. Calculate statistical parameters
        percentage_change = ((recent_mean - baseline_mean) / baseline_mean) * 100.0
        z_score = (recent_mean - baseline_mean) / baseline_std
        variance_ratio = recent_std / baseline_std if baseline_std > 0.0 else 1.0

        # 2. Compute linear trend slope to check for gradual increases/decreases
        x = np.arange(len(recent_values))
        # Fit linear regression: y = slope * x + intercept
        slope, _ = np.polyfit(x, recent_arr, 1)
        
        # Standardized slope measures cumulative drift in standard deviation units
        std_slope = (slope * len(recent_values)) / baseline_std if baseline_std > 0.0 else 0.0

        # 3. Categorize Change Pattern Type
        change_type = None
        
        floors = {
            "power": 0.1,
            "temperature": 1.0,
            "vibration": 0.02,
            "current": 0.5,
            "power_factor": 0.02
        }
        floor = floors.get(param_name, 0.05)
        # Only evaluate DECREASED_VARIABILITY if baseline has actual variable noise above floor
        is_baseline_variable = baseline_std > (floor * 1.01)

        if std_slope >= 1.5:
            change_type = "INCREASING"
        elif std_slope <= -1.5:
            change_type = "DECREASING"
        elif abs(z_score) >= 2.0:
            change_type = "SHIFTED_LEVEL"
        elif variance_ratio >= 1.5:
            change_type = "INCREASED_VARIABILITY"
        elif variance_ratio <= 0.5 and is_baseline_variable:
            change_type = "DECREASED_VARIABILITY"

        # 4. If a change type pattern is identified, compile score and return info
        if change_type:
            # Map Z-scores and variance changes to a normalized change score (0.5 to 1.0)
            metric_factor = max(abs(z_score), abs(variance_ratio - 1.0) * 2.0, abs(std_slope))
            change_score = min(1.0, 0.5 + (metric_factor * 0.08))
            
            return {
                "parameter": param_name,
                "baseline": round(baseline_mean, 3),
                "recent": round(recent_mean, 3),
                "percentage_change": round(percentage_change, 1),
                "change_type": change_type,
                "change_score": round(change_score, 2)
            }
            
        return None
