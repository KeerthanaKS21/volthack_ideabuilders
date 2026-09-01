import re
from typing import Optional, Tuple, Dict, Any, List

KNOWN_MACHINES = {
    "MOTOR-01": ["motor 1", "motor-1", "motor 01", "motor-01", "motor1"],
    "MOTOR-02": ["motor 2", "motor-2", "motor 02", "motor-02", "motor2"],
    "PUMP-01": ["pump 1", "pump-1", "pump 01", "pump-01", "pump1"],
    "PUMP-02": ["pump 2", "pump-2", "pump 02", "pump-02", "pump2"],
    "COMPRESSOR-01": ["compressor 1", "compressor-1", "compressor 01", "compressor-01", "compressor1"],
    "CONVEYOR-01": ["conveyor 1", "conveyor-1", "conveyor 01", "conveyor-01", "conveyor1"],
    "FAN-01": ["fan 1", "fan-1", "fan 01", "fan-01", "fan1"]
}

PARAMETER_KEYWORDS = {
    "power": ["power", "kw", "wattage", "power draw", "consumption", "power usage"],
    "temperature": ["temperature", "temp", "thermal", "heat", "celsius", "hot"],
    "vibration": ["vibration", "vib", "shaking", "vibrating", "oscillation"],
    "current": ["current", "amperage", "amps", "amp"],
    "voltage": ["voltage", "volts", "volt"],
    "power_factor": ["power factor", "pf", "cos phi"]
}

GENERAL_CONCEPTS = {
    "power factor": "Power factor is the ratio of real working power (kW) to apparent power (kVA). A lower power factor indicates inductive inefficiency and excess reactive power demand.",
    "vibration": "Vibration in industrial rotating machinery measures mechanical oscillation. Elevated vibration typically signals mechanical unbalance, shaft misalignment, or bearing race degradation.",
    "isolation forest": "Isolation Forest is an unsupervised machine learning algorithm that isolates anomalies by randomly partitioning feature space into decision trees. Anomalies require fewer random splits to isolate.",
    "baseline": "An empirical historical baseline represents the statistical normal operating mean, standard deviation, and nominal ranges of healthy running telemetry."
}

class QuestionClassifier:
    @classmethod
    def extract_machine_id(
        cls, 
        question: str, 
        conversation_machine_id: Optional[str] = None, 
        active_machine_id: Optional[str] = None
    ) -> Optional[str]:
        """
        Extracts canonical machine ID from question text or resolves pronouns
        using conversation context and active UI selection.
        """
        q_lower = question.lower()

        # 1. Direct match against canonical IDs and aliases
        for canonical, aliases in KNOWN_MACHINES.items():
            if canonical.lower() in q_lower:
                return canonical
            for alias in aliases:
                # Use word boundary check
                if re.search(rf"\b{re.escape(alias)}\b", q_lower):
                    return canonical

        # 2. General regex check for [TYPE]-[NUMBER]
        match = re.search(r"\b(motor|pump|compressor|conveyor|fan)[-\s_]?0?([1-9])\b", q_lower)
        if match:
            m_type = match.group(1).upper()
            m_num = int(match.group(2))
            return f"{m_type}-0{m_num}"

        # 3. Pronoun resolution
        pronoun_match = re.search(r"\b(it|its|this machine|that machine|the machine|the unit|same machine)\b", q_lower)
        if pronoun_match:
            if conversation_machine_id:
                return conversation_machine_id
            if active_machine_id:
                return active_machine_id

        return None

    @classmethod
    def extract_parameter(cls, question: str) -> Optional[str]:
        """Extracts sensor parameter keyword from question text."""
        q_lower = question.lower()
        for param, keywords in PARAMETER_KEYWORDS.items():
            for kw in keywords:
                if kw == "current":
                    # Disambiguate temporal adjective 'current' from electrical current parameter
                    if re.search(r"\bcurrent\s+(status|state|health|overview|summary|condition|situation|priority)\b", q_lower):
                        continue
                    if re.search(r"\b(current\s+draw|electric\s+current|amperage|amps|amp)\b", q_lower):
                        return "current"
                    if re.search(r"\bcurrent\b", q_lower) and not ("status" in q_lower or "state" in q_lower or "health" in q_lower):
                        return "current"
                else:
                    if re.search(rf"\b{re.escape(kw)}\b", q_lower):
                        return param
        return None

    @classmethod
    def classify_intent(cls, question: str, machine_id: Optional[str] = None) -> Tuple[str, Dict[str, Any]]:
        """
        Deterministically classifies the user's question into an intent category
        and extracts relevant query metadata.
        """
        q_lower = question.lower().strip()
        metadata: Dict[str, Any] = {
            "parameter": cls.extract_parameter(question),
            "machine_id": machine_id
        }

        # 0. Check for speculative future predictions or out-of-domain queries
        if any(phrase in q_lower for phrase in [
            "next year", "next month", "tomorrow", "in the future", "will look like", 
            "will happen", "predict the future", "who made you", "weather", "stock price"
        ]):
            return "UNKNOWN", metadata

        # 1. Check for General Concept
        for concept, definition in GENERAL_CONCEPTS.items():
            if re.search(rf"\b(what is|what does|explain|definition of)\s+{re.escape(concept)}\b", q_lower) or q_lower == concept:
                metadata["concept"] = concept
                metadata["definition"] = definition
                return "GENERAL_CONCEPT", metadata

        # 2. Factory Overview / Summary
        if any(phrase in q_lower for phrase in [
            "factory summary", "plant summary", "overview of the factory", 
            "give me a summary", "factory status", "how is the factory", 
            "how are all machines", "summary of all machines", "plant overview"
        ]):
            return "FACTORY_SUMMARY", metadata

        # 3. Health & Priority / Investigation Order
        if any(phrase in q_lower for phrase in [
            "which machine should i investigate first", "which machine to investigate", 
            "investigate first", "highest priority", "highest investigation priority", 
            "top priority", "recommended investigation order", "how many machines need attention", 
            "machines requiring attention", "which machines need attention", "priority score",
            "health status of all", "overall health", "which machine is critical"
        ]):
            return "HEALTH", metadata

        # Specific single machine health check
        if machine_id and any(phrase in q_lower for phrase in [
            "health status", "is it healthy", "is it critical", "health score", "priority score"
        ]):
            return "HEALTH", metadata

        # 4. Energy Intelligence
        if any(phrase in q_lower for phrase in [
            "wasting the most", "wasting energy", "most power", "highest energy", 
            "highest power", "excess energy", "excess power", "excess cost", 
            "energy cost", "energy waste", "inefficient", "inefficiency", "how much energy"
        ]):
            return "ENERGY", metadata

        # 5. Fault Diagnosis / Root Cause
        if any(phrase in q_lower for phrase in [
            "what could be wrong", "what is wrong", "possible fault", "fault detected", 
            "why does gridlite suspect", "why suspect", "diagnosis", "diagnose", 
            "mechanical degradation", "overload", "overheating", "electrical anomaly", 
            "what should be inspected", "suggested inspection", "root cause", "why is it critical"
        ]):
            return "DIAGNOSIS", metadata

        # 6. Behavioral Change Detection
        if any(phrase in q_lower for phrase in [
            "what changed", "which machines have changed", "changed behavior", 
            "behavioral change", "behavior change", "drift", "shifted level", 
            "why is it showing behavioral change", "any changes"
        ]):
            return "BEHAVIOR_CHANGE", metadata

        # 7. Anomaly Detection
        if any(phrase in q_lower for phrase in [
            "which machines have anomalies", "show anomalies", "any anomalies", 
            "flagged as an anomaly", "anomaly score", "anomaly severity", 
            "why was it flagged", "is there an anomaly", "anomaly detected"
        ]):
            return "ANOMALY", metadata

        # 8. Sensor Readings
        if metadata["parameter"] is not None and ("what is" in q_lower or "current" in q_lower or "reading" in q_lower or "level" in q_lower or "value" in q_lower):
            return "SENSOR_VALUE", metadata

        # 9. Machine Status / Operating State
        if any(phrase in q_lower for phrase in [
            "is it running", "is it stopped", "is it idle", "is it off", 
            "operating state", "current state", "current status", "is running"
        ]) or (machine_id and ("status" in q_lower or "state" in q_lower or "running" in q_lower)):
            return "MACHINE_STATUS", metadata

        # 10. Direct single parameter question (e.g. "motor 1 power")
        if metadata["parameter"] is not None and machine_id:
            return "SENSOR_VALUE", metadata

        # 11. General machine lookup without explicit intent (e.g. "tell me about MOTOR-01")
        if machine_id:
            return "MACHINE_STATUS", metadata

        # 12. Fallback to UNKNOWN
        return "UNKNOWN", metadata
