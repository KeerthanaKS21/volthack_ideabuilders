import json
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session

from app.models import Machine, DiagnosisEvent
from app.diagnosis.evidence import EvidenceCollector, EvidenceBundle
from app.diagnosis.rules import DiagnosisRulesEvaluator
from app.diagnosis.explanations import DiagnosisExplainer, RuleBasedExplainer
from app.diagnosis.schemas import (
    DiagnosisResponse,
    PossibleCause,
    EvidenceItem,
    DiagnosisOverviewItem,
    DiagnosisOverviewResponse
)

class DiagnosisEngine:
    """
    Coordinates evidence gathering, deterministic rule evaluation,
    AI/Rule-based explanations, and persistent diagnosis event lifecycle management.
    """

    @classmethod
    def analyze_machine(
        cls,
        db: Session,
        machine_id: str,
        explainer: Optional[DiagnosisExplainer] = None
    ) -> DiagnosisResponse:
        machine_id_upper = machine_id.upper()
        if explainer is None:
            explainer = RuleBasedExplainer()

        # 1. Gather all evidence
        bundle = EvidenceCollector.gather_evidence(db, machine_id_upper)
        if not bundle:
            return DiagnosisResponse(
                machine_id=machine_id_upper,
                status="INSUFFICIENT_EVIDENCE",
                explanation=f"Machine {machine_id_upper} not found or no telemetry readings available."
            )

        if not bundle.has_baseline:
            return DiagnosisResponse(
                machine_id=machine_id_upper,
                status="INSUFFICIENT_EVIDENCE",
                evidence_items=bundle.items,
                explanation=f"Machine {machine_id_upper} has fewer than required historical normal running samples to build a baseline."
            )

        # 2. Evaluate deterministic rules
        possible_causes: List[PossibleCause] = DiagnosisRulesEvaluator.evaluate(bundle)

        # 3. Generate explanation
        explanation = explainer.explain(machine_id_upper, bundle.machine_type, possible_causes, bundle)

        # 4. Handle persistence in diagnosis_events table
        active_event = db.query(DiagnosisEvent)\
            .filter(DiagnosisEvent.machine_id == machine_id_upper)\
            .filter(DiagnosisEvent.status == "ACTIVE")\
            .first()

        if possible_causes:
            primary = possible_causes[0]
            evidence_json_str = json.dumps([item.dict() for item in bundle.items])
            causes_json_str = json.dumps([cause.dict() for cause in possible_causes])
            inspections_json_str = json.dumps(primary.suggested_inspections)

            if active_event:
                if active_event.primary_possible_cause == primary.cause:
                    # Update ongoing event metrics while preserving human review status
                    active_event.timestamp = datetime.utcnow()
                    active_event.evidence_score = primary.evidence_score
                    active_event.evidence_json = evidence_json_str
                    active_event.possible_causes_json = causes_json_str
                    active_event.explanation = explanation
                    active_event.suggested_inspections_json = inspections_json_str
                    db.commit()
                    event_id = active_event.id
                    human_review = active_event.human_review_status
                else:
                    # Previous cause resolved / replaced by new cause
                    active_event.status = "RESOLVED"
                    new_event = DiagnosisEvent(
                        machine_id=machine_id_upper,
                        timestamp=datetime.utcnow(),
                        primary_possible_cause=primary.cause,
                        evidence_score=primary.evidence_score,
                        evidence_json=evidence_json_str,
                        possible_causes_json=causes_json_str,
                        explanation=explanation,
                        suggested_inspections_json=inspections_json_str,
                        human_review_status="UNDER_REVIEW",
                        status="ACTIVE"
                    )
                    db.add(new_event)
                    db.commit()
                    db.refresh(new_event)
                    event_id = new_event.id
                    human_review = new_event.human_review_status
            else:
                new_event = DiagnosisEvent(
                    machine_id=machine_id_upper,
                    timestamp=datetime.utcnow(),
                    primary_possible_cause=primary.cause,
                    evidence_score=primary.evidence_score,
                    evidence_json=evidence_json_str,
                    possible_causes_json=causes_json_str,
                    explanation=explanation,
                    suggested_inspections_json=inspections_json_str,
                    human_review_status="UNDER_REVIEW",
                    status="ACTIVE"
                )
                db.add(new_event)
                db.commit()
                db.refresh(new_event)
                event_id = new_event.id
                human_review = new_event.human_review_status

            return DiagnosisResponse(
                machine_id=machine_id_upper,
                status="DIAGNOSIS_AVAILABLE",
                primary_cause=primary.cause,
                evidence_score=primary.evidence_score,
                possible_causes=possible_causes,
                evidence_items=bundle.items,
                explanation=explanation,
                suggested_inspections=primary.suggested_inspections,
                human_review_status=human_review,
                event_id=event_id,
                timestamp=datetime.utcnow()
            )
        else:
            # Normal or resolved condition
            if active_event:
                active_event.status = "RESOLVED"
                db.commit()

            return DiagnosisResponse(
                machine_id=machine_id_upper,
                status="NORMAL",
                primary_cause=None,
                evidence_score=None,
                possible_causes=[],
                evidence_items=bundle.items,
                explanation=explanation,
                suggested_inspections=[],
                human_review_status="UNDER_REVIEW",
                event_id=None,
                timestamp=datetime.utcnow()
            )

    @classmethod
    def get_latest_diagnosis(cls, db: Session, machine_id: str) -> DiagnosisResponse:
        return cls.analyze_machine(db, machine_id)

    @classmethod
    def get_factory_overview(cls, db: Session) -> DiagnosisOverviewResponse:
        machines = db.query(Machine).all()
        attention_items: List[DiagnosisOverviewItem] = []
        unreviewed = 0

        for machine in machines:
            active_event = db.query(DiagnosisEvent)\
                .filter(DiagnosisEvent.machine_id == machine.machine_id)\
                .filter(DiagnosisEvent.status == "ACTIVE")\
                .first()

            if active_event:
                if active_event.human_review_status == "UNDER_REVIEW":
                    unreviewed += 1

                # Determine priority based on evidence score and cause
                priority = "LOW"
                if active_event.evidence_score >= 0.70 or active_event.primary_possible_cause == "MECHANICAL_DEGRADATION":
                    priority = "HIGH"
                elif active_event.evidence_score >= 0.45:
                    priority = "MEDIUM"

                attention_items.append(DiagnosisOverviewItem(
                    machine_id=machine.machine_id,
                    machine_name=machine.machine_name,
                    machine_type=machine.machine_type,
                    location=machine.location,
                    primary_cause=active_event.primary_possible_cause,
                    evidence_score=active_event.evidence_score,
                    priority=priority,
                    human_review_status=active_event.human_review_status,
                    event_id=active_event.id,
                    timestamp=active_event.timestamp
                ))

        # Sort priority HIGH > MEDIUM > LOW, then evidence_score desc
        priority_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        attention_items.sort(key=lambda x: (priority_order.get(x.priority, 3), -x.evidence_score))

        return DiagnosisOverviewResponse(
            machines_requiring_attention=attention_items,
            total_active_diagnoses=len(attention_items),
            unreviewed_count=unreviewed
        )
