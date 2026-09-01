from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Machine
from app.schemas import MachineResponse, BehaviorChangeResponse

router = APIRouter(prefix="/api/machines", tags=["machines"])

@router.get("", response_model=List[MachineResponse])
def get_machines(db: Session = Depends(get_db)):
    """Retrieve all registered virtual machines."""
    return db.query(Machine).all()

@router.get("/{machine_id}", response_model=MachineResponse)
def get_machine(machine_id: str, db: Session = Depends(get_db)):
    """Retrieve details for a single machine by its ID."""
    machine = db.query(Machine).filter(Machine.machine_id == machine_id.upper()).first()
    if not machine:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Machine with ID '{machine_id}' not found."
        )
    return machine

@router.get("/{machine_id}/changes", response_model=List[BehaviorChangeResponse])
def get_machine_behavior_changes(machine_id: str, db: Session = Depends(get_db)):
    """Retrieve current active behavioral changes for a machine (Phase 5)."""
    from app.models import BehaviorChange
    from app.ml.config import PERSISTENCE_THRESHOLD
    
    machine_id_upper = machine_id.upper()
    machine = db.query(Machine).filter(Machine.machine_id == machine_id_upper).first()
    if not machine:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Machine with ID '{machine_id}' not found."
        )
        
    return db.query(BehaviorChange)\
        .filter(BehaviorChange.machine_id == machine_id_upper)\
        .filter(BehaviorChange.status == "ACTIVE")\
        .filter(BehaviorChange.persistence_count >= PERSISTENCE_THRESHOLD)\
        .all()
