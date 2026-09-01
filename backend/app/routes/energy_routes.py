from typing import List, Dict, Any
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Machine, SensorReading, EnergyEvent
from app.schemas import EnergyConfigResponse, EnergyStatusResponse, EnergySummaryResponse, FactoryOverviewResponse
from app.energy.config import ENERGY_ANALYSIS_WINDOW
from app.energy.tariff import load_tariff, save_tariff
from app.energy.energy_analyzer import EnergyAnalyzer
from app.ml.baseline_manager import BaselineManager

router = APIRouter(prefix="/api/energy", tags=["energy"])

class TariffRequest(BaseModel):
    tariff: float = Field(..., gt=0.0, description="Electricity tariff rate per kWh (must be greater than 0)")

@router.get("/config", response_model=EnergyConfigResponse)
def get_energy_config():
    """Retrieve the current persistent electricity tariff config."""
    return {"tariff": load_tariff()}

@router.put("/config", response_model=EnergyConfigResponse)
def update_energy_config(payload: TariffRequest):
    """Update the persistent electricity tariff config (validates tariff > 0)."""
    if payload.tariff <= 0.0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tariff must be a positive number."
        )
    save_tariff(payload.tariff)
    return {"tariff": payload.tariff}

@router.get("/machines/{machine_id}", response_model=EnergyStatusResponse)
def get_machine_energy_status(machine_id: str, db: Session = Depends(get_db)):
    """Retrieve current energy intelligence for a single machine over its recent window."""
    machine_id_upper = machine_id.upper()
    
    # Verify machine exists
    machine = db.query(Machine).filter(Machine.machine_id == machine_id_upper).first()
    if not machine:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Machine with ID '{machine_id}' not found."
        )

    # Retrieve last 50 readings
    readings = db.query(SensorReading)\
        .filter(SensorReading.machine_id == machine_id_upper)\
        .order_by(SensorReading.timestamp.desc())\
        .limit(ENERGY_ANALYSIS_WINDOW)\
        .all()
        
    analysis = EnergyAnalyzer.analyze_machine_efficiency(db, machine_id_upper, machine.machine_type, readings)
    return analysis

@router.get("/machines/{machine_id}/summary", response_model=EnergySummaryResponse)
def get_machine_energy_summary(machine_id: str, hours: int = 24, db: Session = Depends(get_db)):
    """Retrieve historical energy summary statistics for a machine over a selected hour range."""
    machine_id_upper = machine_id.upper()
    
    # Verify machine exists
    machine = db.query(Machine).filter(Machine.machine_id == machine_id_upper).first()
    if not machine:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Machine with ID '{machine_id}' not found."
        )

    # Get baseline power
    stats = BaselineManager.calculate_baseline_statistics(db, machine_id_upper, machine.machine_type)
    baseline_power = stats["power"]["mean"] if (stats and "power" in stats) else 0.0

    # Get readings in range
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    readings = db.query(SensorReading)\
        .filter(SensorReading.machine_id == machine_id_upper)\
        .filter(SensorReading.timestamp >= cutoff)\
        .all()

    energy_metrics = EnergyAnalyzer.calculate_window_energy(readings, baseline_power)
    
    actual_kwh = energy_metrics["actual_kwh"]
    expected_kwh = energy_metrics["expected_kwh"]
    excess_kwh = energy_metrics["excess_kwh"]
    
    excess_pct = ((actual_kwh - expected_kwh) / expected_kwh * 100.0) if expected_kwh > 0.0 else 0.0
    estimated_excess_cost = excess_kwh * load_tariff()
    
    # Calculate average power
    avg_power = sum(float(r.power) for r in readings) / len(readings) if readings else 0.0

    return {
        "machine_id": machine_id_upper,
        "period": f"{hours}h",
        "actual_energy_kwh": round(actual_kwh, 2),
        "expected_energy_kwh": round(expected_kwh, 2),
        "excess_energy_kwh": round(excess_kwh, 2),
        "excess_percentage": round(excess_pct, 1),
        "estimated_excess_cost": round(estimated_excess_cost, 2),
        "average_power": round(avg_power, 2)
    }

@router.get("/overview", response_model=FactoryOverviewResponse)
def get_factory_energy_overview(db: Session = Depends(get_db)):
    """Retrieve an overall aggregated energy summary for all virtual machines in the last 24h."""
    machines = db.query(Machine).all()
    
    total_actual = 0.0
    total_expected = 0.0
    total_excess = 0.0
    total_cost = 0.0
    inefficient_machines = []
    
    cutoff = datetime.utcnow() - timedelta(hours=24)
    tariff = load_tariff()

    for m in machines:
        # Get baseline power
        stats = BaselineManager.calculate_baseline_statistics(db, m.machine_id, m.machine_type)
        baseline_power = stats["power"]["mean"] if (stats and "power" in stats) else 0.0

        # Get readings in last 24h
        readings = db.query(SensorReading)\
            .filter(SensorReading.machine_id == m.machine_id)\
            .filter(SensorReading.timestamp >= cutoff)\
            .all()

        metrics = EnergyAnalyzer.calculate_window_energy(readings, baseline_power)
        
        total_actual += metrics["actual_kwh"]
        total_expected += metrics["expected_kwh"]
        total_excess += metrics["excess_kwh"]
        
        # Determine if machine is inefficient (has active DB energy event or high excess percentage)
        active_event = db.query(EnergyEvent)\
            .filter(EnergyEvent.machine_id == m.machine_id)\
            .filter(EnergyEvent.status == "ACTIVE")\
            .first()

        pct = ((metrics["actual_kwh"] - metrics["expected_kwh"]) / metrics["expected_kwh"] * 100.0) if metrics["expected_kwh"] > 0.0 else 0.0

        if active_event or pct >= 20.0:
            inefficient_machines.append(m.machine_id)

    total_cost = total_excess * tariff

    return {
        "total_energy_kwh": round(total_actual, 1),
        "expected_energy_kwh": round(total_expected, 1),
        "excess_energy_kwh": round(total_excess, 1),
        "estimated_excess_cost": round(total_cost, 2),
        "inefficient_machines": inefficient_machines
    }
