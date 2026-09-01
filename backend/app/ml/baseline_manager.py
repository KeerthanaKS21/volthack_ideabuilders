import numpy as np
from sqlalchemy.orm import Session
from app.models import SensorReading
from app.ml.preprocessing import FEATURE_NAMES
from simulator.config import PROFILES

class BaselineManager:
    @staticmethod
    def get_normal_readings(db: Session, machine_id: str, machine_type: str):
        """
        Query and filter only normal RUNNING historical telemetry records for a machine.
        Normal bounds are defined per machine type in simulator profiles.
        """
        profile = PROFILES.get(machine_type)
        if not profile:
            return []

        from app.ml.config import RECENT_WINDOW_SIZE

        # Fetch historical running telemetry (offset by recent window size to exclude recent evaluation data)
        readings = db.query(SensorReading)\
            .filter(SensorReading.machine_id == machine_id.upper())\
            .filter(SensorReading.operating_state == "RUNNING")\
            .order_by(SensorReading.timestamp.desc())\
            .offset(RECENT_WINDOW_SIZE)\
            .all()

        normal_readings = []
        for r in readings:
            is_normal = (
                profile["voltage"]["min"] <= r.voltage <= profile["voltage"]["max"] and
                profile["power"]["min"] <= r.power <= profile["power"]["max"] and
                profile["temperature"]["min"] <= r.temperature <= profile["temperature"]["max"] and
                profile["vibration"]["min"] <= r.vibration <= profile["vibration"]["max"] and
                profile["power_factor"]["min"] <= r.power_factor <= profile["power_factor"]["max"]
            )
            if is_normal:
                normal_readings.append(r)
                
        return normal_readings

    @classmethod
    def calculate_baseline_statistics(cls, db: Session, machine_id: str, machine_type: str):
        """
        Calculate baseline stats (mean, std, min, max, count) for each parameter of a machine.
        Returns a dictionary of parameters mapping to statistics.
        """
        normal_readings = cls.get_normal_readings(db, machine_id, machine_type)
        if not normal_readings:
            return None

        # Build feature lists
        data = {param: [] for param in ["power", "temperature", "vibration", "current", "power_factor"]}
        
        for r in normal_readings:
            data["power"].append(float(r.power))
            data["temperature"].append(float(r.temperature))
            data["vibration"].append(float(r.vibration))
            data["current"].append(float(r.current))
            data["power_factor"].append(float(r.power_factor))

        # Noise floor limits to prevent division-by-zero or over-sensitive triggers on synthetic flat data
        NOISE_FLOOR = {
            "power": 0.1,
            "temperature": 1.0,
            "vibration": 0.02,
            "current": 0.5,
            "power_factor": 0.02
        }

        stats = {}
        for param, vals in data.items():
            if len(vals) == 0:
                continue
                
            arr = np.array(vals)
            mean_val = float(np.mean(arr))
            std_val = float(np.std(arr))
            
            # Clamp to noise floor to handle low-variance synthetic profiles safely
            floor = NOISE_FLOOR.get(param, 0.05)
            if std_val < floor:
                std_val = floor

            stats[param] = {
                "mean": mean_val,
                "std": std_val,
                "min": float(np.min(arr)),
                "max": float(np.max(arr)),
                "count": len(vals)
            }
            
        return stats
