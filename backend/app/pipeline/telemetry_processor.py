from typing import Optional, Dict, Any, Tuple
from datetime import datetime
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Machine, SensorReading
from app.schemas import SensorReadingCreate

VALID_OPERATING_STATES = {
    "RUNNING", "IDLE", "STOPPED", "STARTING", "COOLDOWN", "OFF", "STOPPING"
}

class TelemetryProcessor:
    @classmethod
    def validate_reading(cls, db: Session, reading_in: SensorReadingCreate) -> Machine:
        """
        Validates incoming sensor telemetry values against nominal physical boundaries
        and verifies machine registration. Rejects corrupted or impossible values.
        """
        machine_id_upper = reading_in.machine_id.upper()
        machine = db.query(Machine).filter(Machine.machine_id == machine_id_upper).first()
        if not machine:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Machine '{reading_in.machine_id}' is not registered in GridLite inventory."
            )

        # 1. State validation
        state_upper = reading_in.operating_state.upper()
        if state_upper not in VALID_OPERATING_STATES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid operating state '{reading_in.operating_state}'. Must be one of: {', '.join(sorted(VALID_OPERATING_STATES))}"
            )

        # 2. Electrical boundaries
        if reading_in.voltage < 0.0 or reading_in.voltage > 600.0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid voltage reading {reading_in.voltage}V. Acceptable nominal range is 0V - 600V."
            )

        if reading_in.current < 0.0 or reading_in.current > 1000.0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid current reading {reading_in.current}A. Current cannot be negative."
            )

        if reading_in.power < 0.0 or reading_in.power > 500.0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid active power reading {reading_in.power}kW. Power cannot be negative."
            )

        if reading_in.power_factor < 0.0 or reading_in.power_factor > 1.0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid power factor {reading_in.power_factor}. Power factor must be between 0.0 and 1.0."
            )

        # 3. Mechanical & Thermal boundaries
        if reading_in.temperature < -40.0 or reading_in.temperature > 250.0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid temperature reading {reading_in.temperature}°C. Acceptable range is -40°C to 250°C."
            )

        if reading_in.vibration < 0.0 or reading_in.vibration > 100.0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid vibration reading {reading_in.vibration}. Vibration cannot be negative."
            )

        return machine

    @classmethod
    def check_state_transition(
        cls, 
        db: Session, 
        machine_id: str, 
        new_state: str
    ) -> Optional[Tuple[str, str]]:
        """
        Checks if the operating state has changed compared to the machine's previous reading.
        Returns (previous_state, new_state) if transition occurred, otherwise None.
        """
        machine_id_upper = machine_id.upper()
        latest_reading = db.query(SensorReading)\
            .filter(SensorReading.machine_id == machine_id_upper)\
            .order_by(SensorReading.timestamp.desc())\
            .first()

        if not latest_reading:
            # First reading ever for this machine
            return ("OFF", new_state.upper()) if new_state.upper() != "OFF" else None

        prev_state = latest_reading.operating_state.upper()
        new_state_upper = new_state.upper()

        if prev_state != new_state_upper:
            return (prev_state, new_state_upper)

        return None
