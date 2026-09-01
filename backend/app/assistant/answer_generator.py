import os
import json
from typing import Dict, Any, List, Tuple, Optional
from app.assistant.schemas import AssistantEvidenceItem
from app.assistant.query_engine import QueryEngine

SYSTEM_PROMPT = """You are the GridLite Industrial Intelligence Assistant.
Answer ONLY using the verified GridLite context provided to you.
Never invent machine readings, events, diagnoses, dates, causes, or statistics.
If the context does not contain enough information, say that there is insufficient verified information.

Distinguish strictly between:
- observed measurement
- detected anomaly
- behavioral change
- energy inefficiency
- possible diagnosis

Never present a possible diagnosis as a confirmed fault.
Do not claim physical certainty or certified failure guarantees.
Keep answers concise, professional, and operationally useful for industrial plant operators."""

class RuleBasedAnswerGenerator:
    @classmethod
    def generate(
        cls, 
        intent: str, 
        metadata: Dict[str, Any], 
        context: Dict[str, Any]
    ) -> Tuple[str, List[AssistantEvidenceItem], List[str], bool]:
        """
        Generates a 100% grounded, deterministic answer from verified context.
        Returns: (answer_text, evidence_list, suggested_followups, is_general_knowledge)
        """
        # 1. General Engineering Concept
        if intent == "GENERAL_CONCEPT":
            concept = metadata.get("concept", "general concept").title()
            definition = metadata.get("definition", "Industrial engineering metric.")
            ans = f"{concept}: {definition}\n\n(Note: This is general technical knowledge and does not represent live machine telemetry.)"
            return ans, [], ["Give me a factory summary.", "Which machine needs attention?"], True

        # 2. Factory Overview / Summary
        if intent == "FACTORY_SUMMARY":
            health_ov = context.get("health_overview")
            energy_ov = context.get("energy_overview")
            anomalies_count = context.get("active_anomalies_count", 0)

            if not health_ov:
                return "I don't have enough verified factory telemetry to generate a summary.", [], [], False

            total = health_ov.total_machines
            healthy = health_ov.healthy_count
            watch = health_ov.watch_count
            attention = health_ov.attention_count
            critical = health_ov.critical_count
            top_machine = health_ov.top_priority_machine

            lines = [
                f"GridLite is currently monitoring {total} machines.",
                f"• {healthy} Healthy",
                f"• {watch} in Watch status",
                f"• {attention} requiring Attention",
                f"• {critical} Critical"
            ]

            if top_machine:
                # Find top machine details
                top_item = next((m for m in health_ov.machines if m.machine_id == top_machine), None)
                reason = f" ({top_item.primary_reason})" if top_item else ""
                lines.append(f"\n{top_machine} currently has the highest investigation priority{reason}.")
            else:
                lines.append("\nAll machines are operating within normal baseline parameters.")

            if energy_ov and energy_ov.excess_energy_kwh > 0:
                lines.append(f"Total excess energy waste: {energy_ov.excess_energy_kwh:.2f} kWh (Estimated cost: ₹{energy_ov.estimated_excess_cost:.2f}).")

            evidence = []
            if top_machine:
                evidence.append(AssistantEvidenceItem(
                    parameter="Top Priority Machine",
                    variance=f"{top_machine}",
                    note=f"{top_machine} ranked #1 in factory investigation queue"
                ))

            suggestions = [
                "Which machine should I investigate first?",
                "Which machines have anomalies?",
                "Which machine is consuming the most power?"
            ]
            return "\n".join(lines), evidence, suggestions, False

        # 3. Machine-Specific Context Checks
        machine_id = metadata.get("machine_id")

        # 3A. Factory-level Health & Priority Query (No specific machine specified)
        if intent == "HEALTH" and not machine_id:
            health_ov = context.get("health_overview")
            if not health_ov or not health_ov.machines:
                return "I don't have verified factory health data available.", [], [], False

            non_healthy = [m for m in health_ov.machines if m.health_status != "HEALTHY"]
            if not non_healthy:
                return "All machines are currently Healthy (Priority: 0/100). No immediate investigations required.", [], ["Give me a factory summary."], False

            top = health_ov.machines[0]
            lines = [
                f"You should investigate {top.machine_id} first.",
                f"{top.machine_id} has the highest priority score ({top.priority_score}/100) with health status {top.health_status}.",
                f"Primary reason: {top.primary_reason}."
            ]

            if len(non_healthy) > 1:
                lines.append(f"\nOther units requiring attention: {', '.join([m.machine_id for m in non_healthy[1:]])}.")

            evidence = [
                AssistantEvidenceItem(
                    parameter="Investigation Ranking",
                    current=float(top.priority_score),
                    variance=top.health_status,
                    note=f"{top.machine_id}: {top.primary_reason}"
                )
            ]
            suggestions = [
                f"Why is {top.machine_id} critical?",
                f"What could be wrong with {top.machine_id}?",
                f"How much energy is {top.machine_id} consuming?"
            ]
            return "\n".join(lines), evidence, suggestions, False

        # 3B. Factory-level Anomaly Query (No specific machine)
        if intent == "ANOMALY" and not machine_id:
            health_ov = context.get("health_overview")
            machines = QueryEngine.get_all_machines(context.get("_db")) if context.get("_db") else []
            anomalous = []
            if context.get("_db"):
                for m in machines:
                    an = QueryEngine.get_latest_anomaly(context.get("_db"), m.machine_id)
                    if an and an.severity != "NORMAL":
                        anomalous.append((m.machine_id, an.severity, an.anomaly_score))

            if not anomalous:
                return "No machines are currently flagged with active anomalies. All telemetry points are within normal distribution.", [], ["Factory summary"], False

            lines = ["Active anomalies detected:"]
            for mid, sev, score in anomalous:
                lines.append(f"• {mid}: {sev} severity (Score: {score:.2f})")
            
            return "\n".join(lines), [], [f"Why was {anomalous[0][0]} flagged as an anomaly?"], False

        # 3C. Factory-level Behavioral Changes (No specific machine)
        if intent == "BEHAVIOR_CHANGE" and not machine_id:
            if context.get("_db"):
                changes = QueryEngine.get_all_active_behavior_changes(context.get("_db"))
                if not changes:
                    return "No active persistent behavioral changes are currently detected across any machines.", [], ["Factory summary"], False

                mids = sorted(list(set(c.machine_id for c in changes)))
                lines = [f"The following {len(mids)} machine(s) have active behavioral changes:"]
                for mid in mids:
                    m_changes = [c for c in changes if c.machine_id == mid]
                    details = ", ".join([f"{c.parameter} ({c.percentage_change:+.1f}%)" for c in m_changes])
                    lines.append(f"• {mid}: {details}")
                return "\n".join(lines), [], [f"What changed in {mids[0]}?"], False

        # 3D. Factory-level Energy Query (No specific machine)
        if intent == "ENERGY" and not machine_id:
            energy_ov = context.get("energy_overview")
            if not energy_ov or not energy_ov.machines:
                return "I don't have verified factory energy records available.", [], [], False

            # Sort by actual power
            sorted_power = sorted(energy_ov.machines, key=lambda x: x.actual_power, reverse=True)
            top_pwr = sorted_power[0]

            # Sort by excess energy
            sorted_waste = sorted(energy_ov.machines, key=lambda x: x.excess_energy_kwh, reverse=True)
            top_waste = sorted_waste[0]

            lines = [
                f"{top_pwr.machine_id} is currently consuming the most power ({top_pwr.actual_power:.2f} kW)."
            ]
            if top_waste.excess_energy_kwh > 0:
                lines.append(f"{top_waste.machine_id} is wasting the most excess energy with {top_waste.excess_energy_kwh:.2f} kWh excess (Estimated waste cost: ₹{top_waste.estimated_cost:.2f}).")
            else:
                lines.append("No machines are currently showing excess energy waste above baseline thresholds.")

            return "\n".join(lines), [], [f"What is {top_pwr.machine_id}'s current power?", f"Why is {top_waste.machine_id} wasting energy?"], False

        # 4. Specific Machine Operations
        if not context.get("exists"):
            return f"Machine '{machine_id}' was not found in GridLite's registered machine inventory.", [], ["Factory summary", "Which machine should I investigate first?"], False

        reading = context.get("reading")
        baseline = context.get("baseline")
        anomaly = context.get("anomaly")
        changes = context.get("behavior_changes", [])
        energy = context.get("energy")
        diagnosis = context.get("diagnosis")
        health = context.get("health")
        evidence_items = context.get("evidence_items", [])

        # 4A. Specific Sensor Reading
        if intent == "SENSOR_VALUE":
            param = metadata.get("parameter")
            if not reading:
                return f"I don't have verified telemetry readings recorded for {machine_id}.", [], [], False

            if not param:
                # General readings summary
                pwr = reading.get("power")
                tmp = reading.get("temperature")
                vib = reading.get("vibration")
                curr = reading.get("current")
                ans = f"{machine_id} current telemetry ({reading.get('state')}):\n• Power: {pwr:.2f} kW\n• Temperature: {tmp:.1f} °C\n• Vibration: {vib:.3f}\n• Current: {curr:.2f} A"
                return ans, evidence_items, [f"What is {machine_id}'s health status?", f"What changed in {machine_id}?"], False

            val = reading.get(param)
            if val is None:
                return f"I don't have a verified {param} reading for {machine_id}.", [], [], False

            unit_map = {
                "power": "kW",
                "temperature": "°C",
                "vibration": "",
                "current": "A",
                "voltage": "V",
                "power_factor": ""
            }
            unit = unit_map.get(param, "")
            
            base_str = ""
            if baseline and param in baseline:
                b_mean = baseline[param]["mean"]
                diff = ((val - b_mean) / b_mean) * 100.0 if b_mean > 0 else 0
            val_str = f"{val:.2f}" if isinstance(val, float) else str(val)
            ans = f"{machine_id}'s current {param} is {val_str} {unit}{base_str}."
            return ans, evidence_items, [f"Is {machine_id} running?", f"What changed in {machine_id}?"], False

        # 4B. Machine Status / Operating State
        if intent == "MACHINE_STATUS":
            if not reading:
                return f"I don't have verified telemetry readings recorded for {machine_id}.", [], [], False

            state = reading.get("state", "UNKNOWN")
            health_str = f" with {health['status']} health (Priority: {health['priority_score']}/100)" if health else ""
            ans = f"{machine_id} is currently {state}{health_str}.\n• Power: {reading.get('power', 0):.2f} kW\n• Temperature: {reading.get('temperature', 0):.1f} °C\n• Vibration: {reading.get('vibration', 0):.3f}"
            return ans, evidence_items, [f"What could be wrong with {machine_id}?", f"What is {machine_id}'s current power?"], False

        # 4C. Machine Anomaly
        if intent == "ANOMALY":
            if anomaly:
                ans = f"{machine_id} has an active {anomaly['severity']} severity anomaly (Anomaly Score: {anomaly['score']:.2f})."
                return ans, evidence_items, [f"What could be wrong with {machine_id}?", f"What changed in {machine_id}?"], False
            else:
                return f"{machine_id} has no active anomaly detected. Recent telemetry points fall within normal learned clusters.", evidence_items, [f"What is {machine_id}'s status?"], False

        # 4D. Machine Behavioral Change
        if intent == "BEHAVIOR_CHANGE":
            if changes:
                change_descs = [f"{c['parameter']} has shifted {c['direction'].lower()} by {c['magnitude_pct']:+.1f}%" for c in changes]
                ans = f"GridLite detected active behavioral change on {machine_id}:\n• " + "\n• ".join(change_descs) + "\n\nThese shifts have persisted across multiple consecutive evaluation cycles."
                return ans, evidence_items, [f"What could be wrong with {machine_id}?", f"How much energy is {machine_id} wasting?"], False
            else:
                return f"No persistent behavioral changes are active for {machine_id}. Operating parameters match historical baselines.", evidence_items, [f"What is {machine_id}'s status?"], False

        # 4E. Machine Energy
        if intent == "ENERGY":
            if not energy:
                pwr = reading.get("power") if reading else "N/A"
                return f"{machine_id} is currently operating within expected energy parameters (Power: {pwr} kW). No excess waste detected.", evidence_items, [f"What is {machine_id}'s status?"], False

            status_lbl = energy.get("status", "NORMAL")
            excess_kwh = energy.get("excess_energy_kwh", 0.0)
            cost = energy.get("estimated_cost", 0.0)

            if status_lbl == "INEFFICIENT" or excess_kwh > 0:
                ans = f"{machine_id} is classified as {status_lbl} in energy intelligence.\n• Total Excess Energy: {excess_kwh:.2f} kWh\n• Estimated Excess Cost: ₹{cost:.2f}\n• Actual Power: {reading.get('power', 0):.2f} kW vs Baseline Normal: {baseline.get('power', {}).get('mean', 0):.2f} kW."
            else:
                ans = f"{machine_id} is operating with normal energy efficiency. No excess power consumption is detected."
            return ans, evidence_items, [f"What could be wrong with {machine_id}?", f"Why is {machine_id} critical?"], False

        # 4F. Machine Diagnosis
        if intent == "DIAGNOSIS":
            if diagnosis:
                cause_str = diagnosis["primary_cause"].replace("_", " ").title()
                score_pct = int(diagnosis["evidence_score"] * 100)
                ans = f"GridLite currently identifies possible {cause_str.lower()} for {machine_id} (Evidence Score: {score_pct}%).\n\n" \
                      f"Assessment: {diagnosis.get('explanation', 'Evidence indicates parameter deviations matching fault signature.')}\n\n" \
                      f"⚠️ Note: This is an AI-assisted diagnostic hypothesis based on telemetry evidence, not a certified physical breakdown confirmation."
                return ans, evidence_items, [f"Why is {machine_id} critical?", f"How much energy is {machine_id} wasting?"], False
            else:
                return f"No active fault signatures are detected for {machine_id}. Telemetry correlates with healthy historical baselines.", evidence_items, [f"What is {machine_id}'s status?"], False

        # 4G. Machine Health & Priority
        if intent == "HEALTH":
            if health:
                status_lbl = health["status"]
                score = health["priority_score"]
                reason = health["primary_reason"]
                ans = f"{machine_id} is currently classified as {status_lbl} with an investigation priority score of {score}/100.\n\nPrimary Assessment: {reason}."
                return ans, evidence_items, [f"What could be wrong with {machine_id}?", f"What changed in {machine_id}?"], False
            else:
                return f"{machine_id} is Healthy (Priority: 0/100). No active alerts.", evidence_items, [f"What is {machine_id}'s status?"], False

        # 5. Unknown Intent / Fallback
        return "I don't have enough verified GridLite data to answer that question.", [], ["Give me a factory summary.", "Which machine should I investigate first?"], False


class LLMAnswerGenerator:
    @classmethod
    def generate(
        cls, 
        question: str, 
        context: Dict[str, Any]
    ) -> Optional[str]:
        """
        Attempts to generate an explanatory answer via external LLM using verified context.
        Returns None if no LLM key is configured or if an error occurs.
        """
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            return None

        # Build clean prompt with verified context
        clean_context = {k: v for k, v in context.items() if k != "_db" and v is not None}
        prompt = f"Verified GridLite Context:\n{json.dumps(clean_context, indent=2)}\n\nUser Question:\n{question}"

        try:
            # Prefer Google Gemini SDK if available
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-1.5-flash", system_instruction=SYSTEM_PROMPT)
            response = model.generate_content(prompt)
            if response and response.text:
                return response.text.strip()
        except Exception as e:
            print(f"[LLMAnswerGenerator] LLM generation failed, falling back to rule-based: {e}")
            return None

        return None
