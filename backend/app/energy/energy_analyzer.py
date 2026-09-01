from datetime import datetime
from typing import List, Dict, Any
from sqlalchemy.orm import Session

from app.models import SensorReading, EnergyEvent
from app.ml.baseline_manager import BaselineManager
from app.energy.tariff import load_tariff

class EnergyAnalyzer:
    @staticmethod
    def calculate_window_energy(readings: List[SensorReading], baseline_mean: float) -> Dict[str, float]:
        """
        Calculate actual, expected, and excess kWh over a chronological list of readings.
        Formula: kWh = Power(kW) * Time(hours)
        """
        if len(readings) < 2:
            return {
                "actual_kwh": 0.0,
                "expected_kwh": 0.0,
                "excess_kwh": 0.0
            }

        # Sort chronologically by timestamp
        sorted_readings = sorted(readings, key=lambda r: r.timestamp)
        
        actual_total = 0.0
        expected_total = 0.0

        for i in range(len(sorted_readings) - 1):
            r_prev = sorted_readings[i]
            r_curr = sorted_readings[i+1]

            # Calculate time difference in seconds
            dt = (r_curr.timestamp - r_prev.timestamp).total_seconds()
            
            # Skip invalid time steps
            if dt <= 0.0:
                continue
                
            # Clamp extremely large intervals (e.g. simulator gaps) to 1 hour (3600s)
            if dt > 3600.0:
                dt = 3600.0

            hours = dt / 3600.0

            # Power values (kW)
            actual_power = float(r_prev.power)
            
            # Expected power is baseline mean only during RUNNING state;
            # otherwise expected power equals actual power (so 0 excess is calculated for OFF/IDLE/STARTING)
            if r_prev.operating_state == "RUNNING" and baseline_mean > 0.0:
                expected_power = baseline_mean
            else:
                expected_power = actual_power

            actual_total += actual_power * hours
            expected_total += expected_power * hours

        excess = actual_total - expected_total
        if excess < 0.0:
            excess = 0.0

        return {
            "actual_kwh": round(actual_total, 3),
            "expected_kwh": round(expected_total, 3),
            "excess_kwh": round(excess, 3)
        }

    @classmethod
    def analyze_machine_efficiency(
        cls, 
        db: Session, 
        machine_id: str, 
        machine_type: str, 
        readings: List[SensorReading]
    ) -> Dict[str, Any]:
        """
        Compute real-time energy intelligence for a machine over its recent readings window.
        Returns a dictionary of energy metrics and status classifications.
        """
        machine_id_upper = machine_id.upper()
        
        # 1. Fetch baseline statistics
        stats = BaselineManager.calculate_baseline_statistics(db, machine_id_upper, machine_type)
        baseline_power = stats["power"]["mean"] if (stats and "power" in stats) else 0.0

        # Get latest current power
        current_power = 0.0
        state = "OFF"
        if readings:
            latest_reading = max(readings, key=lambda r: r.timestamp)
            current_power = float(latest_reading.power)
            state = latest_reading.operating_state

        # 2. Compute actual, expected, and excess kWh
        energy_metrics = cls.calculate_window_energy(readings, baseline_power)
        
        actual_kwh = energy_metrics["actual_kwh"]
        expected_kwh = energy_metrics["expected_kwh"]
        excess_kwh = energy_metrics["excess_kwh"]

        # Calculate difference percentage
        if expected_kwh > 0.0:
            diff_pct = ((actual_kwh - expected_kwh) / expected_kwh) * 100.0
        else:
            diff_pct = 0.0

        # 3. Load electricity tariff and calculate cost estimates
        tariff = load_tariff()
        estimated_excess_cost = excess_kwh * tariff

        # 4. Check for active database energy event (Phase 6 persistence)
        active_event = db.query(EnergyEvent)\
            .filter(EnergyEvent.machine_id == machine_id_upper)\
            .filter(EnergyEvent.status == "ACTIVE")\
            .first()

        # Classify energy status
        if active_event:
            # If an active energy event persists in the database, it's inefficient
            status = "INEFFICIENT"
        elif diff_pct >= 20.0:
            status = "INEFFICIENT"
        elif diff_pct >= 10.0:
            status = "ELEVATED"
        else:
            status = "NORMAL"

        return {
            "machine_id": machine_id_upper,
            "operating_state": state,
            "current_power_kw": round(current_power, 2),
            "baseline_power_kw": round(baseline_power, 2),
            "difference_percentage": round(diff_pct, 1),
            "energy_status": status,
            "actual_energy_kwh": actual_kwh,
            "expected_energy_kwh": expected_kwh,
            "excess_energy_kwh": excess_kwh,
            "estimated_excess_cost": round(estimated_excess_cost, 2)
        }
