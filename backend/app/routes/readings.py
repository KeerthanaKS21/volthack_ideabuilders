import json
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Machine, SensorReading, Anomaly
from app.schemas import SensorReadingCreate, SensorReadingResponse, ReadingIngestResponse
from app.ml.model_manager import ModelManager
from app.ml.config import ANOMALY_THRESHOLD_LOW, ANOMALY_THRESHOLD_MEDIUM, ANOMALY_THRESHOLD_HIGH, CHANGE_DETECTION_INTERVAL

router = APIRouter(prefix="/api/readings", tags=["readings"])

# Global tracker for Phase 6 energy persistence
ENERGY_PERSISTENCE = {}

# Database retention configuration: keep readings for 2 hours
KEEP_READINGS_HOURS = 2

def format_reading(reading: SensorReading) -> dict:
    """Format an ORM SensorReading to match SensorReadingResponse schema, attaching nested anomaly metadata."""
    anomaly_data = None
    if reading.anomaly:
        try:
            deviations = json.loads(reading.anomaly.affected_parameters)
        except Exception:
            deviations = {}
        anomaly_data = {
            "is_anomaly": reading.anomaly.severity != "NORMAL",
            "anomaly_score": reading.anomaly.anomaly_score,
            "severity": reading.anomaly.severity,
            "parameter_deviations": deviations
        }
    
    return {
        "id": reading.id,
        "machine_id": reading.machine_id,
        "timestamp": reading.timestamp,
        "voltage": reading.voltage,
        "current": reading.current,
        "power": reading.power,
        "temperature": reading.temperature,
        "vibration": reading.vibration,
        "power_factor": reading.power_factor,
        "operating_state": reading.operating_state,
        "anomaly": anomaly_data
    }

@router.post("", response_model=ReadingIngestResponse, status_code=status.HTTP_201_CREATED)
def create_reading(reading_data: SensorReadingCreate, db: Session = Depends(get_db)):
    """
    Accept standard GridLite sensor telemetry, validate physical parameters,
    persist to database, execute full intelligence pipeline (Anomalies, Behavior,
    Energy, Diagnosis, Health), emit unified events, and prune historical telemetry.
    """
    from app.pipeline.pipeline_service import PipelineService
    from app.pipeline.auto_simulator import record_external_ingest
    record_external_ingest()
    
    db_reading, anomaly_info = PipelineService.ingest_and_process(db, reading_data)

    return {
        "reading": format_reading(db_reading),
        "anomaly": anomaly_info
    }

@router.get("/latest", response_model=List[SensorReadingResponse])
def get_latest_readings(db: Session = Depends(get_db)):
    """Retrieve the single most recent telemetry reading for each machine."""
    machines = db.query(Machine).all()
    latest_readings = []
    
    for machine in machines:
        reading = db.query(SensorReading)\
            .filter(SensorReading.machine_id == machine.machine_id)\
            .order_by(SensorReading.timestamp.desc())\
            .first()
        if reading:
            latest_readings.append(format_reading(reading))
            
    return latest_readings

# Define routes on a separate prefix for historical values
history_router = APIRouter(prefix="/api/machines", tags=["history"])

@history_router.get("/{machine_id}/readings", response_model=List[SensorReadingResponse])
def get_machine_readings(
    machine_id: str, 
    limit: int = Query(default=100, ge=1, le=1000), 
    db: Session = Depends(get_db)
):
    """Retrieve historical telemetry readings for a machine, ordered newest to oldest."""
    machine_id_upper = machine_id.upper()
    
    # Validate machine exists
    machine = db.query(Machine).filter(Machine.machine_id == machine_id_upper).first()
    if not machine:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Machine with ID '{machine_id}' not found."
        )

    readings = db.query(SensorReading)\
        .filter(SensorReading.machine_id == machine_id_upper)\
        .order_by(SensorReading.timestamp.desc())\
        .limit(limit)\
        .all()
        
    return [format_reading(r) for r in readings]
