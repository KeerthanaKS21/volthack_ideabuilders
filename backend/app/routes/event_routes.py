import json
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import UnifiedEvent
from app.schemas import UnifiedEventResponse, DemoResetResponse
from app.pipeline.event_manager import EventManager

router = APIRouter(prefix="/api", tags=["events"])

def format_event(event: UnifiedEvent) -> dict:
    try:
        evidence = json.loads(event.evidence_json) if event.evidence_json else {}
    except Exception:
        evidence = {}

    return {
        "id": event.id,
        "machine_id": event.machine_id,
        "event_type": event.event_type,
        "severity": event.severity,
        "timestamp": event.timestamp,
        "title": event.title,
        "description": event.description,
        "evidence": evidence,
        "status": event.status,
        "acknowledged_at": event.acknowledged_at,
        "resolved_at": event.resolved_at
    }

@router.get("/events", response_model=List[UnifiedEventResponse])
def list_events(
    machine_id: Optional[str] = None,
    event_type: Optional[str] = None,
    severity: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db)
):
    """Retrieve unified events with optional filtering by machine, event type, severity, and status."""
    events = EventManager.get_events(
        db=db,
        machine_id=machine_id,
        event_type=event_type,
        severity=severity,
        status=status,
        limit=limit,
        offset=offset
    )
    return [format_event(e) for e in events]

@router.get("/events/recent", response_model=List[UnifiedEventResponse])
def get_recent_events(
    limit: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Retrieve top recent events prioritized by severity weight (CRITICAL > HIGH > MEDIUM > LOW > INFO)."""
    events = EventManager.get_recent_events(db=db, limit=limit)
    return [format_event(e) for e in events]

@router.get("/events/machines/{machine_id}/timeline", response_model=List[UnifiedEventResponse])
def get_machine_timeline(
    machine_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """Retrieve chronological event history for a specific machine."""
    events = EventManager.get_machine_timeline(db=db, machine_id=machine_id, limit=limit)
    return [format_event(e) for e in events]

@router.get("/events/{event_id}", response_model=UnifiedEventResponse)
def get_event_detail(
    event_id: int,
    db: Session = Depends(get_db)
):
    """Retrieve details for a single unified event."""
    event = db.query(UnifiedEvent).filter(UnifiedEvent.id == event_id).first()
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unified event with ID {event_id} not found."
        )
    return format_event(event)

@router.post("/events/{event_id}/acknowledge", response_model=UnifiedEventResponse)
def acknowledge_event(
    event_id: int,
    db: Session = Depends(get_db)
):
    """Mark an active event as ACKNOWLEDGED by an operator."""
    event = EventManager.acknowledge_event(db=db, event_id=event_id)
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unified event with ID {event_id} not found."
        )
    return format_event(event)

@router.post("/events/{event_id}/resolve", response_model=UnifiedEventResponse)
def resolve_event(
    event_id: int,
    db: Session = Depends(get_db)
):
    """Manually mark an event as RESOLVED by an operator."""
    event = EventManager.manually_resolve_event(db=db, event_id=event_id)
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unified event with ID {event_id} not found."
        )
    return format_event(event)

@router.post("/demo/reset", response_model=DemoResetResponse)
def reset_demo(
    db: Session = Depends(get_db)
):
    """Reset active events, anomalies, and health states, restoring a clean demonstration baseline."""
    from app.pipeline.auto_simulator import clear_all_simulator_faults
    clear_all_simulator_faults()
    cleared_count = EventManager.reset_demo(db=db)
    return {
        "status": "success",
        "message": f"Demo state reset successfully. {cleared_count} unified events cleared.",
        "cleared_events_count": cleared_count,
        "reset_timestamp": datetime.utcnow()
    }

@router.post("/demo/inject-fault")
def inject_fault(
    machine_id: str,
    fault_type: str = "MECHANICAL_DEGRADATION",
    db: Session = Depends(get_db)
):
    """Inject a simulated industrial fault into a specific machine."""
    from app.pipeline.auto_simulator import inject_simulator_fault
    success = inject_simulator_fault(machine_id, fault_type)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Machine {machine_id} not found in simulator."
        )
    return {
        "status": "success",
        "machine_id": machine_id.upper(),
        "fault_type": fault_type.upper(),
        "message": f"Injected {fault_type} into {machine_id.upper()}."
    }

@router.post("/demo/clear-faults")
def clear_faults():
    """Clear all active simulator faults."""
    from app.pipeline.auto_simulator import clear_all_simulator_faults
    clear_all_simulator_faults()
    return {"status": "success", "message": "All active simulator faults cleared."}

