from typing import List, Dict, Any, Tuple
from app.diagnosis.evidence import EvidenceBundle
from app.diagnosis.schemas import PossibleCause

class DiagnosisRulesEvaluator:
    """
    Deterministic rule engine evaluating physical sensor evidence, statistical baseline deviations,
    anomaly scores, and energy telemetry to rank plausible machine fault causes.
    """

    @classmethod
    def evaluate(cls, bundle: EvidenceBundle) -> List[PossibleCause]:
        if not bundle.has_baseline:
            return []

        # If machine is OFF or IDLE with no abnormal readings, return empty
        if bundle.operating_state == "OFF":
            return []

        causes: List[PossibleCause] = []

        # 1. MECHANICAL_DEGRADATION
        mech_score, mech_evidence, mech_inspections = cls._eval_mechanical_degradation(bundle)
        if mech_score >= 0.35:
            causes.append(PossibleCause(
                cause="MECHANICAL_DEGRADATION",
                evidence_score=round(min(mech_score, 1.0), 2),
                evidence=mech_evidence,
                suggested_inspections=mech_inspections
            ))

        # 2. OVERLOAD
        overload_score, overload_evidence, overload_inspections = cls._eval_overload(bundle)
        if overload_score >= 0.35:
            causes.append(PossibleCause(
                cause="OVERLOAD",
                evidence_score=round(min(overload_score, 1.0), 2),
                evidence=overload_evidence,
                suggested_inspections=overload_inspections
            ))

        # 3. OVERHEATING
        heat_score, heat_evidence, heat_inspections = cls._eval_overheating(bundle)
        if heat_score >= 0.35:
            causes.append(PossibleCause(
                cause="OVERHEATING",
                evidence_score=round(min(heat_score, 1.0), 2),
                evidence=heat_evidence,
                suggested_inspections=heat_inspections
            ))

        # 4. ELECTRICAL_ANOMALY
        elec_score, elec_evidence, elec_inspections = cls._eval_electrical_anomaly(bundle)
        if elec_score >= 0.35:
            causes.append(PossibleCause(
                cause="ELECTRICAL_ANOMALY",
                evidence_score=round(min(elec_score, 1.0), 2),
                evidence=elec_evidence,
                suggested_inspections=elec_inspections
            ))

        # Sort descending by evidence score
        causes.sort(key=lambda c: c.evidence_score, reverse=True)
        return causes

    @classmethod
    def _eval_mechanical_degradation(cls, bundle: EvidenceBundle) -> Tuple[float, List[str], List[str]]:
        score = 0.0
        evidence: List[str] = []
        vib_dev = bundle.param_deviations.get("vibration", 0.0)
        pwr_dev = bundle.param_deviations.get("power", 0.0)
        temp_dev = bundle.param_deviations.get("temperature", 0.0)

        # Vibration is the primary mechanical indicator
        if vib_dev >= 50.0:
            score += 0.40
            evidence.append(f"Vibration is significantly elevated (+{vib_dev:.1f}% above baseline)")
        elif vib_dev >= 25.0:
            score += 0.25
            evidence.append(f"Vibration is moderately elevated (+{vib_dev:.1f}% above baseline)")
        elif vib_dev >= 15.0:
            score += 0.15
            evidence.append(f"Slight vibration elevation detected (+{vib_dev:.1f}% above baseline)")

        # Accompanying friction power increase
        if pwr_dev >= 15.0:
            score += 0.25
            evidence.append(f"Power draw increased by +{pwr_dev:.1f}% consistent with increased mechanical drag")
        elif pwr_dev >= 8.0:
            score += 0.15
            evidence.append(f"Power draw slightly elevated (+{pwr_dev:.1f}% above baseline)")

        # Accompanying frictional heating
        if temp_dev >= 10.0:
            score += 0.20
            evidence.append(f"Temperature increased by +{temp_dev:.1f}% indicating potential friction")
        elif temp_dev >= 5.0:
            score += 0.10
            evidence.append(f"Temperature slightly above normal (+{temp_dev:.1f}%)")

        # Persistent behavioral change confirmation
        if "vibration" in bundle.active_behavior_changes or "power" in bundle.active_behavior_changes:
            score += 0.15
            evidence.append("Change detection engine confirmed persistent upward shift over multiple cycles")

        # Anomaly model corroboration
        if bundle.is_anomaly and score >= 0.30:
            score += 0.10
            evidence.append(f"Isolation Forest flagged anomaly condition ({bundle.anomaly_severity} severity)")

        inspections = [
            "Inspect bearings for physical wear, spalling, or lubrication depletion.",
            "Check shaft alignment, coupling integrity, and mounting bolt torque.",
            "Inspect belts, pulleys, and mechanical drive linkages for binding or uneven tension."
        ]
        return score, evidence, inspections

    @classmethod
    def _eval_overload(cls, bundle: EvidenceBundle) -> Tuple[float, List[str], List[str]]:
        score = 0.0
        evidence: List[str] = []
        cur_dev = bundle.param_deviations.get("current", 0.0)
        pwr_dev = bundle.param_deviations.get("power", 0.0)
        temp_dev = bundle.param_deviations.get("temperature", 0.0)

        # High current and power indicate heavy load
        if cur_dev >= 20.0:
            score += 0.35
            evidence.append(f"Current draw is heavily elevated (+{cur_dev:.1f}% above baseline)")
        elif cur_dev >= 10.0:
            score += 0.20
            evidence.append(f"Current draw is elevated (+{cur_dev:.1f}% above baseline)")

        if pwr_dev >= 20.0:
            score += 0.35
            evidence.append(f"Active power consumption is +{pwr_dev:.1f}% above nominal baseline")
        elif pwr_dev >= 10.0:
            score += 0.20
            evidence.append(f"Active power consumption is elevated (+{pwr_dev:.1f}% above baseline)")

        if temp_dev >= 10.0:
            score += 0.20
            evidence.append(f"Thermal accumulation observed (+{temp_dev:.1f}% temperature)")

        if bundle.is_energy_inefficient:
            score += 0.10
            evidence.append("Persistent energy inefficiency detected with sustained excess power draw")

        inspections = [
            "Check whether equipment is operating beyond rated throughput or design capacity.",
            "Inspect material feed rate and product flow for jamming or over-packing.",
            "Verify motor nameplate Full Load Amperage (FLA) against measured continuous current."
        ]
        return score, evidence, inspections

    @classmethod
    def _eval_overheating(cls, bundle: EvidenceBundle) -> Tuple[float, List[str], List[str]]:
        score = 0.0
        evidence: List[str] = []
        temp_dev = bundle.param_deviations.get("temperature", 0.0)

        # Primary indicator is severe temperature rise
        if temp_dev >= 30.0:
            score += 0.50
            evidence.append(f"Severe temperature deviation detected (+{temp_dev:.1f}% above baseline)")
        elif temp_dev >= 15.0:
            score += 0.35
            evidence.append(f"Elevated operating temperature (+{temp_dev:.1f}% above baseline)")
        elif temp_dev >= 8.0:
            score += 0.20
            evidence.append(f"Moderate temperature increase (+{temp_dev:.1f}% above baseline)")

        if "temperature" in bundle.active_behavior_changes:
            score += 0.30
            evidence.append("Behavioral change engine confirmed persistent upward thermal drift")

        if bundle.operating_state == "RUNNING":
            score += 0.20
            evidence.append("Heat accumulation occurring during active running duty cycle")

        inspections = [
            "Inspect cooling fans, ventilation ducts, and cooling fins for dirt or obstructions.",
            "Check ambient ventilation, coolant flow (if liquid cooled), and enclosure temperatures.",
            "Inspect internal lubricant viscosity and levels to ensure adequate heat dissipation."
        ]
        return score, evidence, inspections

    @classmethod
    def _eval_electrical_anomaly(cls, bundle: EvidenceBundle) -> Tuple[float, List[str], List[str]]:
        score = 0.0
        evidence: List[str] = []
        volt_dev = abs(bundle.param_deviations.get("voltage", 0.0))
        pf_dev = bundle.param_deviations.get("power_factor", 0.0)
        cur_dev = bundle.param_deviations.get("current", 0.0)

        # Voltage fluctuation
        if volt_dev >= 5.0:
            score += 0.35
            evidence.append(f"Supply voltage deviation observed ({volt_dev:.1f}% variance from nominal)")
        elif volt_dev >= 3.0:
            score += 0.20
            evidence.append(f"Minor supply voltage instability ({volt_dev:.1f}% variance)")

        # Power factor degradation
        if pf_dev <= -15.0:
            score += 0.35
            evidence.append(f"Significant power factor drop ({pf_dev:.1f}% degradation from baseline)")
        elif pf_dev <= -8.0:
            score += 0.20
            evidence.append(f"Moderate power factor degradation ({pf_dev:.1f}%)")

        # Disproportionate current
        if abs(cur_dev) >= 15.0:
            score += 0.30
            evidence.append(f"Current instability observed ({cur_dev:+.1f}% shift)")

        inspections = [
            "Verify electrical supply quality, phase balance, and line voltage stability.",
            "Check power factor correction capacitor banks and switchgear connections.",
            "Inspect terminal lugs, contactors, and grounding for loose or high-resistance joints."
        ]
        return score, evidence, inspections
