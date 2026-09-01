import sys
import os
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

# Add project root to python path to allow importing from simulator config
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.append(project_root)

from app.database import get_db
from app.models import Machine, SensorReading
from app.schemas import ModelTrainingResponse
from app.ml.config import MIN_TRAINING_SAMPLES, PROFILES
from app.ml.preprocessing import extract_features, FEATURE_NAMES
from app.ml.anomaly_detector import AnomalyDetector
from app.ml.model_manager import ModelManager

router = APIRouter(prefix="/api/anomaly", tags=["anomaly"])

@router.post("/train/{machine_id}", response_model=ModelTrainingResponse)
def train_machine_model(machine_id: str, db: Session = Depends(get_db)):
    """
    Train an unsupervised anomaly model for a machine using normal historical readings.
    Requires at least MIN_TRAINING_SAMPLES normal readings.
    """
    machine_id_upper = machine_id.upper()

    # 1. Validate machine exists
    machine = db.query(Machine).filter(Machine.machine_id == machine_id_upper).first()
    if not machine:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Machine with ID '{machine_id}' not found."
        )

    # 2. Get machine type profile bounds to isolate "normal" data
    profile = PROFILES.get(machine.machine_type)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Machine type profile '{machine.machine_type}' not configured in simulator configs."
        )

    # 3. Retrieve historical running telemetry
    all_readings = db.query(SensorReading)\
        .filter(SensorReading.machine_id == machine_id_upper)\
        .filter(SensorReading.operating_state == "RUNNING")\
        .all()

    # 4. Filter for "normal" readings (excluding anomalous fault periods)
    normal_readings = []
    for r in all_readings:
        is_normal = (
            profile["voltage"]["min"] <= r.voltage <= profile["voltage"]["max"] and
            profile["power"]["min"] <= r.power <= profile["power"]["max"] and
            profile["temperature"]["min"] <= r.temperature <= profile["temperature"]["max"] and
            profile["vibration"]["min"] <= r.vibration <= profile["vibration"]["max"] and
            profile["power_factor"]["min"] <= r.power_factor <= profile["power_factor"]["max"]
        )
        if is_normal:
            normal_readings.append(r)

    # 5. Check if we have sufficient samples
    samples_count = len(normal_readings)
    if samples_count < MIN_TRAINING_SAMPLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Insufficient normal training data for machine {machine_id_upper}. "
                f"Found {samples_count} normal samples, but need at least {MIN_TRAINING_SAMPLES}. "
                "Ensure the simulator is running normally to collect sufficient baseline data."
            )
        )

    # 6. Train the Isolation Forest model
    try:
        X = extract_features(normal_readings)
        detector = AnomalyDetector()
        detector.train(X)
        
        # Save model pickle weights
        ModelManager.save_model(machine_id_upper, detector, samples_count)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fit anomaly model: {e}"
        )

    return {
        "machine_id": machine_id_upper,
        "status": "trained",
        "training_samples": samples_count,
        "features": FEATURE_NAMES
    }
