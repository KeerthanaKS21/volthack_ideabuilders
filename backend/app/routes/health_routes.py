import json
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Machine, MachineHealthEvent
from app.health.health_schemas import (
    MachineHealthResponse,
    HealthOverviewResponse,
    OperatorReviewRequest,
    OperatorReviewResponse,
    HealthEventHistoryItem
)
from app.health.health_engine import HealthEngine

router = APIRouter(prefix="/api/health", tags=["health"])

@router.get("/overview", response_model=HealthOverviewResponse)
def get_factory_health_overview(db: Session = Depends(get_db)):
    """Retrieve factory-wide machine health summary and ranked priority list."""
    return HealthEngine.get_factory_overview(db)

@router.get("/machines/{machine_id}", response_model=MachineHealthResponse)
def get_machine_health(machine_id: str, db: Session = Depends(get_db)):
    """Retrieve current machine health status, priority score, and explainability breakdown."""
    machine_id_upper = machine_id.upper()
    machine = db.query(Machine).filter(Machine.machine_id == machine_id_upper).first()
    if not machine:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Machine with ID '{machine_id}' not found."
        )
    return HealthEngine.evaluate_machine(db, machine_id_upper)

@router.post("/analyze/{machine_id}", response_model=MachineHealthResponse)
def analyze_machine_health(machine_id: str, db: Session = Depends(get_db)):
    """Trigger on-demand health and priority analysis for a machine."""
    machine_id_upper = machine_id.upper()
    machine = db.query(Machine).filter(Machine.machine_id == machine_id_upper).first()
    if not machine:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Machine with ID '{machine_id}' not found."
        )
    return HealthEngine.evaluate_machine(db, machine_id_upper)

@router.put("/events/{event_id}/operator-status", response_model=OperatorReviewResponse)
def update_operator_status(
    event_id: int,
    req: OperatorReviewRequest,
    db: Session = Depends(get_db)
):
    """Update human operator investigation status (INVESTIGATE, UNDER_REVIEW, RESOLVED)."""
    valid_statuses = ["INVESTIGATE", "UNDER_REVIEW", "RESOLVED"]
    status_upper = req.status.upper()
    if status_upper not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid operator status '{req.status}'. Must be one of: {valid_statuses}"
        )

    event = db.query(MachineHealthEvent).filter(MachineHealthEvent.id == event_id).first()
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Health event with ID {event_id} not found."
        )

    event.operator_status = status_upper
    if status_upper == "RESOLVED":
        event.status = "RESOLVED"
    db.commit()

    return OperatorReviewResponse(
        event_id=event.id,
        operator_status=event.operator_status,
        message=f"Operator status updated to '{event.operator_status}'."
    )

@router.get("/machines/{machine_id}/history", response_model=List[HealthEventHistoryItem])
def get_machine_health_history(
    machine_id: str,
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db)
):
    """Retrieve historical machine health event records for audit trail."""
    machine_id_upper = machine_id.upper()
    machine = db.query(Machine).filter(Machine.machine_id == machine_id_upper).first()
    if not machine:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Machine with ID '{machine_id}' not found."
        )

    events = db.query(MachineHealthEvent)\
        .filter(MachineHealthEvent.machine_id == machine_id_upper)\
        .order_by(MachineHealthEvent.timestamp.desc())\
        .limit(limit)\
        .all()

    result = []
    for ev in events:
        try:
            factors = json.loads(ev.contributing_factors_json)
        except Exception:
            factors = []

        result.append(HealthEventHistoryItem(
            id=ev.id,
            machine_id=ev.machine_id,
            timestamp=ev.timestamp,
            health_status=ev.health_status,
            priority_score=ev.priority_score,
            primary_reason=ev.primary_reason,
            contributing_factors=factors,
            operator_status=ev.operator_status,
            status=ev.status
        ))

    return result
