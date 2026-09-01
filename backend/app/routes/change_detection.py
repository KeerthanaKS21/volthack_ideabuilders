from typing import List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Machine, SensorReading, BehaviorChange
from app.schemas import BehaviorChangeResponse
from app.ml.config import RECENT_WINDOW_SIZE, PERSISTENCE_THRESHOLD, MIN_TRAINING_SAMPLES
from app.ml.baseline_manager import BaselineManager
from app.ml.change_detector import ChangeDetector

router = APIRouter(prefix="/api/change-detection", tags=["change-detection"])

@router.get("/machines/{machine_id}/changes", response_model=List[BehaviorChangeResponse])
def get_machine_changes(machine_id: str, db: Session = Depends(get_db)):
    """
    Retrieve all current active behavioral changes for a machine.
    Filters by ACTIVE status and persistence_count >= PERSISTENCE_THRESHOLD.
    """
    machine_id_upper = machine_id.upper()
    changes = db.query(BehaviorChange)\
        .filter(BehaviorChange.machine_id == machine_id_upper)\
        .filter(BehaviorChange.status == "ACTIVE")\
        .filter(BehaviorChange.persistence_count >= PERSISTENCE_THRESHOLD)\
        .all()
    return changes

@router.post("/analyze/{machine_id}", response_model=List[BehaviorChangeResponse])
def analyze_machine_behavior(machine_id: str, db: Session = Depends(get_db)):
    """
    Manually trigger a behavioral change analysis for a machine.
    Compares baseline statistics against recent window values.
    """
    machine_id_upper = machine_id.upper()

    # 1. Verify machine exists
    machine = db.query(Machine).filter(Machine.machine_id == machine_id_upper).first()
    if not machine:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Machine with ID '{machine_id}' not found."
        )

    # 2. Retrieve historical baseline stats (min MIN_TRAINING_SAMPLES)
    stats = BaselineManager.calculate_baseline_statistics(db, machine_id_upper, machine.machine_type)
    
    first_param = list(stats.keys())[0] if stats else None
    if not stats or stats[first_param]["count"] < MIN_TRAINING_SAMPLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Insufficient historical data for machine {machine_id_upper} baseline. "
                f"Need at least {MIN_TRAINING_SAMPLES} normal running samples in database."
            )
        )

    # 3. Retrieve recent readings window
    recent_readings = db.query(SensorReading)\
        .filter(SensorReading.machine_id == machine_id_upper)\
        .order_by(SensorReading.timestamp.desc())\
        .limit(RECENT_WINDOW_SIZE)\
        .all()
        
    if len(recent_readings) < 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient recent readings window (found {len(recent_readings)}, need at least 10)."
        )

    # Reverse to chronological order
    recent_readings.reverse()

    # 4. Extract recent values list per parameter
    params_data = {
        "power": [float(r.power) for r in recent_readings],
        "temperature": [float(r.temperature) for r in recent_readings],
        "vibration": [float(r.vibration) for r in recent_readings],
        "current": [float(r.current) for r in recent_readings],
        "power_factor": [float(r.power_factor) for r in recent_readings]
    }

    # 5. Run change detection per parameter and apply persistence/resolution logic
    for param, vals in params_data.items():
        param_stats = stats.get(param)
        if not param_stats:
            continue
            
        change_result = ChangeDetector.analyze_parameter_change(param, vals, param_stats)
        
        # Query active event
        active_event = db.query(BehaviorChange)\
            .filter(BehaviorChange.machine_id == machine_id_upper)\
            .filter(BehaviorChange.parameter == param)\
            .filter(BehaviorChange.status == "ACTIVE")\
            .first()

        if change_result:
            # Change detected!
            if active_event:
                # Update existing active event
                active_event.recent_value = change_result["recent"]
                active_event.percentage_change = change_result["percentage_change"]
                active_event.change_score = change_result["change_score"]
                active_event.persistence_count += 1
                db.commit()
            else:
                # Create a new active event
                new_event = BehaviorChange(
                    machine_id=machine_id_upper,
                    detected_at=datetime.utcnow(),
                    parameter=param,
                    baseline_value=change_result["baseline"],
                    recent_value=change_result["recent"],
                    percentage_change=change_result["percentage_change"],
                    change_type=change_result["change_type"],
                    change_score=change_result["change_score"],
                    persistence_count=1,
                    status="ACTIVE"
                )
                db.add(new_event)
                db.commit()
        else:
            # No change detected (or resolved back to baseline)
            if active_event:
                # Resolve the active event
                active_event.status = "RESOLVED"
                db.commit()

    # 6. Query and return all verified ACTIVE changes
    active_changes = db.query(BehaviorChange)\
        .filter(BehaviorChange.machine_id == machine_id_upper)\
        .filter(BehaviorChange.status == "ACTIVE")\
        .filter(BehaviorChange.persistence_count >= PERSISTENCE_THRESHOLD)\
        .all()
        
    return active_changes

@router.get("/baseline/{machine_id}")
def get_machine_baseline(machine_id: str, db: Session = Depends(get_db)):
    """Retrieve historical baseline statistics for a machine."""
    machine_id_upper = machine_id.upper()
    machine = db.query(Machine).filter(Machine.machine_id == machine_id_upper).first()
    if not machine:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Machine with ID '{machine_id}' not found."
        )
    stats = BaselineManager.calculate_baseline_statistics(db, machine_id_upper, machine.machine_type)
    return stats or {}
