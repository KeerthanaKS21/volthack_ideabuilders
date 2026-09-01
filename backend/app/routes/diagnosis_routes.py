import json
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Machine, DiagnosisEvent
from app.diagnosis.diagnosis_engine import DiagnosisEngine
from app.diagnosis.schemas import (
    DiagnosisResponse,
    DiagnosisOverviewResponse,
    HumanReviewRequest,
    HumanReviewResponse
)

router = APIRouter(prefix="/api/diagnosis", tags=["Fault Diagnosis Engine"])


@router.get("/machines/{machine_id}", response_model=DiagnosisResponse)
def get_machine_diagnosis(machine_id: str, db: Session = Depends(get_db)):
    """
    Retrieve the current AI-assisted diagnostic evaluation and traceable evidence for a machine.
    """
    machine = db.query(Machine).filter(Machine.machine_id == machine_id.upper()).first()
    if not machine:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Machine {machine_id} not found."
        )

    return DiagnosisEngine.get_latest_diagnosis(db, machine_id)


@router.post("/analyze/{machine_id}", response_model=DiagnosisResponse)
def analyze_machine_diagnosis(machine_id: str, db: Session = Depends(get_db)):
    """
    Trigger on-demand deterministic rule evaluation and AI explanation for a machine.
    """
    machine = db.query(Machine).filter(Machine.machine_id == machine_id.upper()).first()
    if not machine:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Machine {machine_id} not found."
        )

    return DiagnosisEngine.analyze_machine(db, machine_id)


@router.get("/overview", response_model=DiagnosisOverviewResponse)
def get_diagnosis_overview(db: Session = Depends(get_db)):
    """
    Retrieve factory-wide list of machines requiring maintenance attention, prioritized by severity.
    """
    return DiagnosisEngine.get_factory_overview(db)


@router.put("/events/{event_id}/review", response_model=HumanReviewResponse)
def update_human_review(
    event_id: int,
    review: HumanReviewRequest,
    db: Session = Depends(get_db)
):
    """
    Update human review status (CONFIRMED, REJECTED, UNDER_REVIEW) for a diagnosis event.
    Stores human decision separately without modifying verified sensor evidence.
    """
    event = db.query(DiagnosisEvent).filter(DiagnosisEvent.id == event_id).first()
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Diagnosis event ID {event_id} not found."
        )

    valid_statuses = ["UNDER_REVIEW", "CONFIRMED", "REJECTED"]
    normalized_status = review.status.upper()
    if normalized_status not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid review status '{review.status}'. Must be one of {valid_statuses}."
        )

    event.human_review_status = normalized_status
    db.commit()

    return HumanReviewResponse(
        event_id=event.id,
        machine_id=event.machine_id,
        human_review_status=event.human_review_status,
        message=f"Human review status updated to {normalized_status} for event {event.id}."
    )


@router.get("/machines/{machine_id}/history")
def get_machine_diagnosis_history(
    machine_id: str,
    limit: int = 10,
    db: Session = Depends(get_db)
):
    """
    Retrieve historical diagnosis events for a machine.
    """
    machine = db.query(Machine).filter(Machine.machine_id == machine_id.upper()).first()
    if not machine:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Machine {machine_id} not found."
        )

    events = db.query(DiagnosisEvent)\
        .filter(DiagnosisEvent.machine_id == machine_id.upper())\
        .order_by(DiagnosisEvent.timestamp.desc())\
        .limit(limit)\
        .all()

    results = []
    for e in events:
        results.append({
            "id": e.id,
            "machine_id": e.machine_id,
            "timestamp": e.timestamp,
            "primary_possible_cause": e.primary_possible_cause,
            "evidence_score": e.evidence_score,
            "explanation": e.explanation,
            "human_review_status": e.human_review_status,
            "status": e.status,
            "evidence": json.loads(e.evidence_json) if e.evidence_json else [],
            "possible_causes": json.loads(e.possible_causes_json) if e.possible_causes_json else [],
            "suggested_inspections": json.loads(e.suggested_inspections_json) if e.suggested_inspections_json else []
        })

    return results
