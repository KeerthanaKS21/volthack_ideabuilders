import json
from typing import Optional, List, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import desc, case

from app.models import (
    UnifiedEvent,
    Anomaly,
    BehaviorChange,
    EnergyEvent,
    DiagnosisEvent,
    MachineHealthEvent,
    SensorReading,
    Machine
)

SEVERITY_ORDER = {
    "CRITICAL": 5,
    "HIGH": 4,
    "MEDIUM": 3,
    "LOW": 2,
    "INFO": 1
}

class EventManager:
    @classmethod
    def create_or_update_event(
        cls,
        db: Session,
        machine_id: str,
        event_type: str,
        severity: str,
        title: str,
        description: str,
        evidence: Optional[Dict[str, Any]] = None
    ) -> UnifiedEvent:
        """
        Emits a unified event with smart deduplication. If an event of the same type
        is already ACTIVE or ACKNOWLEDGED for this machine, updates it in place to prevent event storms.
        """
        machine_id_upper = machine_id.upper()
        evidence_str = json.dumps(evidence or {})

        # For discrete state transitions, resolve the previous state event and create a new transition milestone
        if event_type == "MACHINE_STATE_CHANGED":
            prev_active = db.query(UnifiedEvent)\
                .filter(UnifiedEvent.machine_id == machine_id_upper)\
                .filter(UnifiedEvent.event_type == event_type)\
                .filter(UnifiedEvent.status.in_(["ACTIVE", "ACKNOWLEDGED"]))\
                .first()
            if prev_active:
                prev_active.status = "RESOLVED"
                prev_active.resolved_at = datetime.utcnow()
                db.commit()

            new_event = UnifiedEvent(
                machine_id=machine_id_upper,
                event_type=event_type,
                severity=severity,
                timestamp=datetime.utcnow(),
                title=title,
                description=description,
                evidence_json=evidence_str,
                status="ACTIVE"
            )
            db.add(new_event)
            db.commit()
            db.refresh(new_event)
            return new_event

        active_event = db.query(UnifiedEvent)\
            .filter(UnifiedEvent.machine_id == machine_id_upper)\
            .filter(UnifiedEvent.event_type == event_type)\
            .filter(UnifiedEvent.status.in_(["ACTIVE", "ACKNOWLEDGED"]))\
            .first()

        if active_event:
            # Update continuous active condition in place (deduplication)
            active_event.severity = severity
            active_event.title = title
            active_event.description = description
            active_event.evidence_json = evidence_str
            active_event.timestamp = datetime.utcnow()
            db.commit()
            db.refresh(active_event)
            return active_event

        # Create new active event
        new_event = UnifiedEvent(
            machine_id=machine_id_upper,
            event_type=event_type,
            severity=severity,
            timestamp=datetime.utcnow(),
            title=title,
            description=description,
            evidence_json=evidence_str,
            status="ACTIVE"
        )
        db.add(new_event)
        db.commit()
        db.refresh(new_event)
        return new_event

    @classmethod
    def resolve_active_event(
        cls,
        db: Session,
        machine_id: str,
        event_type: str
    ) -> Optional[UnifiedEvent]:
        """
        Resolves an active event when machine telemetry or analytics normalize.
        """
        machine_id_upper = machine_id.upper()
        active_event = db.query(UnifiedEvent)\
            .filter(UnifiedEvent.machine_id == machine_id_upper)\
            .filter(UnifiedEvent.event_type == event_type)\
            .filter(UnifiedEvent.status.in_(["ACTIVE", "ACKNOWLEDGED"]))\
            .first()

        if active_event:
            active_event.status = "RESOLVED"
            active_event.resolved_at = datetime.utcnow()
            db.commit()
            db.refresh(active_event)
            return active_event

        return None

    @classmethod
    def acknowledge_event(cls, db: Session, event_id: int) -> Optional[UnifiedEvent]:
        """Marks an active event as ACKNOWLEDGED by an operator."""
        event = db.query(UnifiedEvent).filter(UnifiedEvent.id == event_id).first()
        if event and event.status == "ACTIVE":
            event.status = "ACKNOWLEDGED"
            event.acknowledged_at = datetime.utcnow()
            db.commit()
            db.refresh(event)
        return event

    @classmethod
    def manually_resolve_event(cls, db: Session, event_id: int) -> Optional[UnifiedEvent]:
        """Manually marks an event as RESOLVED by an operator."""
        event = db.query(UnifiedEvent).filter(UnifiedEvent.id == event_id).first()
        if event and event.status != "RESOLVED":
            event.status = "RESOLVED"
            event.resolved_at = datetime.utcnow()
            db.commit()
            db.refresh(event)
        return event

    @classmethod
    def get_events(
        cls,
        db: Session,
        machine_id: Optional[str] = None,
        event_type: Optional[str] = None,
        severity: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[UnifiedEvent]:
        query = db.query(UnifiedEvent)
        if machine_id:
            query = query.filter(UnifiedEvent.machine_id == machine_id.upper())
        if event_type:
            query = query.filter(UnifiedEvent.event_type == event_type.upper())
        if severity:
            query = query.filter(UnifiedEvent.severity == severity.upper())
        if status:
            query = query.filter(UnifiedEvent.status == status.upper())

        return query.order_by(UnifiedEvent.timestamp.desc()).offset(offset).limit(limit).all()

    @classmethod
    def get_recent_events(cls, db: Session, limit: int = 25) -> List[UnifiedEvent]:
        """
        Retrieves top events prioritized by severity weight (CRITICAL > HIGH > MEDIUM > LOW > INFO)
        and recency.
        """
        severity_case = case(
            (UnifiedEvent.severity == "CRITICAL", 5),
            (UnifiedEvent.severity == "HIGH", 4),
            (UnifiedEvent.severity == "MEDIUM", 3),
            (UnifiedEvent.severity == "LOW", 2),
            else_=1
        )

        return db.query(UnifiedEvent)\
            .order_by(UnifiedEvent.status.asc(), severity_case.desc(), UnifiedEvent.timestamp.desc())\
            .limit(limit)\
            .all()

    @classmethod
    def get_machine_timeline(cls, db: Session, machine_id: str, limit: int = 50) -> List[UnifiedEvent]:
        """Returns chronological event history for a specific machine."""
        return db.query(UnifiedEvent)\
            .filter(UnifiedEvent.machine_id == machine_id.upper())\
            .order_by(UnifiedEvent.timestamp.desc())\
            .limit(limit)\
            .all()

    @classmethod
    def reset_demo(cls, db: Session) -> int:
        """
        Resets all active intelligence events, anomalies, behavioral changes,
        and machine health events, restoring a clean healthy demonstration baseline.
        """
        cleared_count = db.query(UnifiedEvent).delete()
        db.query(Anomaly).delete()
        db.query(BehaviorChange).delete()
        db.query(EnergyEvent).delete()
        db.query(DiagnosisEvent).delete()
        db.query(MachineHealthEvent).delete()
        db.commit()
        return cleared_count
