import os
from abc import ABC, abstractmethod
from typing import List, Optional
from app.diagnosis.evidence import EvidenceBundle
from app.diagnosis.schemas import PossibleCause

class DiagnosisExplainer(ABC):
    @abstractmethod
    def explain(
        self,
        machine_id: str,
        machine_type: str,
        possible_causes: List[PossibleCause],
        bundle: EvidenceBundle
    ) -> str:
        """Generate human-readable diagnostic explanation based on verified evidence."""
        pass


class RuleBasedExplainer(DiagnosisExplainer):
    """
    Deterministic rule-based explainer that formats structured evidence into natural,
    professional maintenance diagnostics without requiring an external LLM.
    """

    def explain(
        self,
        machine_id: str,
        machine_type: str,
        possible_causes: List[PossibleCause],
        bundle: EvidenceBundle
    ) -> str:
        if not bundle.has_baseline:
            return (
                f"Machine {machine_id} ({machine_type}) has insufficient historical baseline readings "
                f"to establish normal operating telemetry. Diagnosis cannot be reliably computed."
            )

        if not possible_causes:
            return (
                f"Machine {machine_id} ({machine_type}) is currently operating within normal historical baseline "
                f"parameters. No abnormal fault signatures or operational degradation patterns were detected."
            )

        primary = possible_causes[0]
        primary_title = primary.cause.replace("_", " ").title()

        lines = [
            f"{machine_id} ({machine_type}) shows evidence of possible {primary_title} "
            f"(evidence score: {primary.evidence_score:.2f}).",
            "",
            "Key Observed Evidence:"
        ]

        for ev in primary.evidence:
            lines.append(f"• {ev}")

        if len(possible_causes) > 1:
            secondary = possible_causes[1]
            sec_title = secondary.cause.replace("_", " ").title()
            lines.append("")
            lines.append(f"Secondary plausible factor: Possible {sec_title} (evidence score: {secondary.evidence_score:.2f}).")

        lines.append("")
        lines.append("Suggested Physical Inspection:")
        for insp in primary.suggested_inspections:
            lines.append(f"• {insp}")

        lines.append("")
        lines.append(
            "* Notice: This is an AI-assisted diagnostic suggestion generated from verified sensor evidence. "
            "It does not constitute a certified equipment failure report and must be verified by qualified personnel."
        )

        return "\n".join(lines)


class LLMExplainer(DiagnosisExplainer):
    """
    Optional LLM explanation layer. Uses external model strictly for natural language synthesis
    of verified evidence without inventing or overriding deterministic scores.
    Falls back gracefully to RuleBasedExplainer if unavailable or on error.
    """

    def __init__(self):
        self.fallback = RuleBasedExplainer()

    def explain(
        self,
        machine_id: str,
        machine_type: str,
        possible_causes: List[PossibleCause],
        bundle: EvidenceBundle
    ) -> str:
        # If no external API key is configured, fallback immediately
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            return self.fallback.explain(machine_id, machine_type, possible_causes, bundle)

        # In production with API key, LLM can be invoked here with strict ground-truth prompt
        # For prototype reliability, fall back safely to deterministic rules
        return self.fallback.explain(machine_id, machine_type, possible_causes, bundle)
