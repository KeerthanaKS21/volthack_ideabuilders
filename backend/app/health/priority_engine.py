from typing import Dict, List, Any, Tuple
from app.health.config import (
    ANOMALY_WEIGHT,
    CHANGE_WEIGHT,
    ENERGY_WEIGHT,
    DIAGNOSIS_WEIGHT,
    PERSISTENCE_WEIGHT,
    MULTI_SIGNAL_BONUS_3,
    MULTI_SIGNAL_BONUS_4,
    HEALTHY_THRESHOLD,
    WATCH_THRESHOLD,
    ATTENTION_THRESHOLD
)
from app.health.health_schemas import SignalScoreItem

class PriorityEngine:
    @staticmethod
    def evaluate(
        anomaly_info: Dict[str, Any],
        behavior_changes: List[Dict[str, Any]],
        energy_info: Dict[str, Any],
        diagnosis_info: Dict[str, Any],
        persistence_count: int,
        param_deviations: Dict[str, float]
    ) -> Tuple[int, str, str, List[str], List[str], Dict[str, SignalScoreItem]]:
        """
        Evaluate normalized multi-signal intelligence and compute:
        1. priority_score (0 - 100)
        2. health_status (HEALTHY, WATCH, ATTENTION, CRITICAL)
        3. primary_reason (concise explanation)
        4. contributing_factors (bulleted human-readable explanations)
        5. active_issues (list of issue tag names)
        6. signals (detailed signal breakdown)
        """
        contributing_factors: List[str] = []
        active_issues: List[str] = []

        # 1. Normalize Anomaly Signal
        s_anomaly = 0.0
        anomaly_rating = "NORMAL"
        anomaly_details = "Telemetry pattern is normal"
        
        if anomaly_info and anomaly_info.get("is_anomaly"):
            sev = anomaly_info.get("severity", "NORMAL")
            raw_score = float(anomaly_info.get("anomaly_score", 0.0))
            if sev == "HIGH":
                s_anomaly = 1.00
                anomaly_rating = "HIGH"
                contributing_factors.append(f"High anomaly score ({raw_score:.2f})")
                active_issues.append("High Anomaly")
                anomaly_details = f"Severe anomaly detected (score: {raw_score:.2f})"
            elif sev == "MEDIUM":
                s_anomaly = 0.70
                anomaly_rating = "MEDIUM"
                contributing_factors.append(f"Moderate anomaly detected (score: {raw_score:.2f})")
                active_issues.append("Moderate Anomaly")
                anomaly_details = f"Moderate anomaly detected (score: {raw_score:.2f})"
            elif sev == "LOW":
                s_anomaly = 0.40
                anomaly_rating = "LOW"
                contributing_factors.append(f"Minor point-in-time anomaly detected (score: {raw_score:.2f})")
                active_issues.append("Minor Anomaly")
                anomaly_details = f"Minor anomaly detected (score: {raw_score:.2f})"

        # 2. Normalize Behavioral Change Signal
        s_change = 0.0
        change_rating = "NORMAL"
        change_details = "Operating within historical baseline"
        
        if behavior_changes and len(behavior_changes) > 0:
            num_changes = len(behavior_changes)
            affected_params = [c.get("parameter", "") for c in behavior_changes if c.get("parameter")]
            params_str = ", ".join(affected_params) if affected_params else f"{num_changes} parameters"
            
            if num_changes >= 3:
                s_change = 1.00
                change_rating = "HIGH"
                contributing_factors.append(f"Persistent behavioral change across {num_changes} parameters ({params_str})")
                active_issues.append(f"Multi-Parameter Drift ({num_changes})")
                change_details = f"Significant trend shift across {params_str}"
            elif num_changes == 2:
                s_change = 0.80
                change_rating = "HIGH"
                contributing_factors.append(f"Persistent behavioral change in {params_str}")
                active_issues.append(f"Behavioral Drift ({params_str})")
                change_details = f"Persistent shift in {params_str}"
            else:
                s_change = 0.50
                change_rating = "MEDIUM"
                contributing_factors.append(f"Behavioral trend shift in {params_str}")
                active_issues.append(f"Behavioral Drift ({params_str})")
                change_details = f"Trend shift in {params_str}"

        # 3. Normalize Energy Inefficiency Signal
        s_energy = 0.0
        energy_rating = "NORMAL"
        energy_details = "Energy consumption matches expected power"
        
        if energy_info:
            e_status = energy_info.get("energy_status", "NORMAL")
            diff_pct = float(energy_info.get("difference_percentage", 0.0))
            if e_status == "INEFFICIENT" or diff_pct >= 20.0:
                s_energy = 1.00
                energy_rating = "HIGH"
                contributing_factors.append(f"Active energy inefficiency (+{diff_pct:.0f}% excess consumption)")
                active_issues.append("Energy Inefficiency")
                energy_details = f"Excessive energy consumption (+{diff_pct:.0f}% above expected)"
            elif e_status == "ELEVATED" or diff_pct >= 10.0:
                s_energy = 0.50
                energy_rating = "MEDIUM"
                contributing_factors.append(f"Elevated power consumption (+{diff_pct:.0f}% above expected)")
                active_issues.append("Elevated Energy")
                energy_details = f"Elevated power consumption (+{diff_pct:.0f}%)"

        # 4. Normalize Diagnosis Signal
        s_diagnosis = 0.0
        diagnosis_rating = "NORMAL"
        diagnosis_details = "No fault signatures diagnosed"
        
        if diagnosis_info and diagnosis_info.get("status") == "DIAGNOSIS_AVAILABLE":
            primary_cause = diagnosis_info.get("primary_cause", "FAULT")
            evidence_score = float(diagnosis_info.get("evidence_score", 0.50))
            s_diagnosis = min(1.0, max(0.35, evidence_score))
            
            cause_readable = primary_cause.replace("_", " ").title()
            if s_diagnosis >= 0.75:
                diagnosis_rating = "HIGH"
            elif s_diagnosis >= 0.50:
                diagnosis_rating = "MEDIUM"
            else:
                diagnosis_rating = "LOW"

            contributing_factors.append(f"Possible {cause_readable.lower()} (Evidence Score: {int(evidence_score * 100)}%)")
            active_issues.append(f"Possible {cause_readable}")
            diagnosis_details = f"Evidence indicates possible {cause_readable.lower()} ({int(evidence_score * 100)}%)"

        # 5. Normalize Persistence Factor
        s_persistence = 0.0
        persistence_rating = "NORMAL"
        persistence_details = "Transient or normal telemetry"
        
        if persistence_count >= 9:
            s_persistence = 1.00
            persistence_rating = "HIGH"
            contributing_factors.append(f"Persistent abnormal behavior across {persistence_count}+ readings")
            persistence_details = f"Abnormal state sustained for {persistence_count}+ consecutive readings"
        elif persistence_count >= 5:
            s_persistence = 0.70
            persistence_rating = "MEDIUM"
            contributing_factors.append(f"Sustained abnormal behavior ({persistence_count} readings)")
            persistence_details = f"Abnormal state sustained for {persistence_count} readings"
        elif persistence_count >= 2:
            s_persistence = 0.40
            persistence_rating = "LOW"
            persistence_details = f"Early abnormal readings ({persistence_count} readings)"

        # 6. Parameter Deviation Highlights (Specific explainable bullets)
        if param_deviations:
            vib_pct = param_deviations.get("vibration", 0.0)
            pwr_pct = param_deviations.get("power", 0.0)
            tmp_pct = param_deviations.get("temperature", 0.0)
            cur_pct = param_deviations.get("current", 0.0)

            if vib_pct >= 50.0:
                contributing_factors.append(f"Vibration {vib_pct:+.0f}% above historical baseline")
            if pwr_pct >= 20.0:
                contributing_factors.append(f"Power draw {pwr_pct:+.0f}% above historical baseline")
            if tmp_pct >= 20.0:
                contributing_factors.append(f"Temperature {tmp_pct:+.0f}% above historical baseline")
            if cur_pct >= 20.0:
                contributing_factors.append(f"Current draw {cur_pct:+.0f}% above historical baseline")

        # 7. Compute Base Floor and Weighted Priority Score
        has_any_signal = (s_anomaly > 0 or s_change > 0 or s_energy > 0 or s_diagnosis > 0)
        
        if not has_any_signal:
            final_priority = 0
            health_status = "HEALTHY"
        else:
            # Active signal baseline floor
            base_floor = 28.0
            if s_anomaly >= 0.90 or s_diagnosis >= 0.80 or (s_change >= 0.80 and s_energy >= 0.80):
                base_floor = 55.0
            elif s_anomaly >= 0.65 or s_change >= 0.70 or s_energy >= 0.80 or s_persistence >= 0.70:
                base_floor = 42.0

            weighted_contrib = 40.0 * (
                (ANOMALY_WEIGHT * s_anomaly) +
                (CHANGE_WEIGHT * s_change) +
                (ENERGY_WEIGHT * s_energy) +
                (DIAGNOSIS_WEIGHT * s_diagnosis)
            ) + (20.0 * s_persistence)

            # 8. Multi-Signal Correlation Amplification
            active_signals_count = sum(1 for s in [s_anomaly, s_change, s_energy, s_diagnosis] if s >= 0.35)
            bonus = 0.0
            if active_signals_count >= 4:
                bonus = MULTI_SIGNAL_BONUS_4
                contributing_factors.append("Multi-signal agreement across Anomaly, Behavior, Energy, and Diagnosis")
            elif active_signals_count == 3:
                bonus = MULTI_SIGNAL_BONUS_3
                contributing_factors.append("Multi-signal correlation across 3 independent detection systems")
            elif active_signals_count == 2:
                bonus = 5.0

            total_score = base_floor + weighted_contrib + bonus
            final_priority = int(round(min(100.0, max(0.0, total_score))))

            # 9. Map Priority Score to Health Status
            if final_priority <= HEALTHY_THRESHOLD:
                health_status = "HEALTHY"
            elif final_priority <= WATCH_THRESHOLD:
                health_status = "WATCH"
            elif final_priority <= ATTENTION_THRESHOLD:
                health_status = "ATTENTION"
            else:
                health_status = "CRITICAL"

        # 10. Synthesize Primary Reason
        if health_status == "HEALTHY":
            primary_reason = "Operating within normal baseline bounds"
            if len(contributing_factors) == 0:
                contributing_factors.append("All sensor readings match normal operational profiles")
        elif health_status == "CRITICAL":
            if active_signals_count >= 3:
                primary_reason = "Multiple persistent abnormal signals requiring immediate investigation"
            elif s_diagnosis >= 0.70 and diagnosis_info:
                cause_str = diagnosis_info.get("primary_cause", "severe fault").replace("_", " ").title()
                primary_reason = f"Severe {cause_str.lower()} signature with compounding telemetry deviations"
            elif s_anomaly >= 0.90:
                primary_reason = "Severe anomaly with critical sensor deviations"
            else:
                primary_reason = "Critical abnormal operating state requiring immediate attention"
        elif health_status == "ATTENTION":
            if s_energy >= 0.80:
                primary_reason = "Persistent energy inefficiency with elevated consumption"
            elif s_change >= 0.70:
                primary_reason = "Persistent behavioral trend shift across key parameters"
            elif s_anomaly >= 0.60:
                primary_reason = "Moderate anomaly with elevated operating deviations"
            else:
                primary_reason = "Persistent abnormal behavior requiring investigation"
        else:  # WATCH
            if s_change > 0:
                primary_reason = "Early behavioral shift detected"
            elif s_anomaly > 0:
                primary_reason = "Minor anomaly detected"
            elif s_energy > 0:
                primary_reason = "Slightly elevated energy consumption"
            else:
                primary_reason = "Minor variance observed in telemetry"

        # 11. Compile Signal Breakdown Map
        signals = {
            "anomaly": SignalScoreItem(
                name="Anomaly Detection",
                normalized_score=round(s_anomaly, 2),
                rating=anomaly_rating,
                details=anomaly_details
            ),
            "behavior": SignalScoreItem(
                name="Behavioral Drift",
                normalized_score=round(s_change, 2),
                rating=change_rating,
                details=change_details
            ),
            "energy": SignalScoreItem(
                name="Energy Intelligence",
                normalized_score=round(s_energy, 2),
                rating=energy_rating,
                details=energy_details
            ),
            "diagnosis": SignalScoreItem(
                name="Fault Diagnosis",
                normalized_score=round(s_diagnosis, 2),
                rating=diagnosis_rating,
                details=diagnosis_details
            ),
            "persistence": SignalScoreItem(
                name="Signal Persistence",
                normalized_score=round(s_persistence, 2),
                rating=persistence_rating,
                details=persistence_details
            ),
        }

        return (final_priority, health_status, primary_reason, contributing_factors, active_issues, signals)
