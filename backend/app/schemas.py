from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, field_validator

class MachineBase(BaseModel):
    machine_id: str = Field(..., min_length=1)
    machine_name: str = Field(..., min_length=1)
    machine_type: str = Field(..., min_length=1)
    location: str = Field(..., min_length=1)

class MachineCreate(MachineBase):
    pass

class MachineResponse(MachineBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True
        orm_mode = True


class SensorReadingBase(BaseModel):
    machine_id: str = Field(..., min_length=1)
    timestamp: datetime
    voltage: float = Field(..., ge=0.0)
    current: float = Field(..., ge=0.0)
    power: float = Field(..., ge=0.0)
    temperature: float = Field(..., ge=-50.0)
    vibration: float = Field(..., ge=0.0)
    power_factor: float = Field(..., ge=0.0, le=1.0)
    operating_state: str

    @field_validator("operating_state")
    @classmethod
    def validate_state(cls, v: str) -> str:
        valid_states = ["OFF", "STARTING", "IDLE", "RUNNING", "STOPPED", "COOLDOWN", "STOPPING"]
        upper_v = v.upper()
        if upper_v not in valid_states:
            raise ValueError(f"operating_state must be one of {valid_states}")
        return upper_v

class SensorReadingCreate(SensorReadingBase):
    pass

class AnomalyDetailResponse(BaseModel):
    is_anomaly: bool
    anomaly_score: float
    severity: str
    parameter_deviations: Dict[str, str]

class SensorReadingResponse(SensorReadingBase):
    id: int
    anomaly: Optional[AnomalyDetailResponse] = None

    class Config:
        from_attributes = True
        orm_mode = True

# Wrapper response schema for POST /api/readings
class ReadingIngestResponse(BaseModel):
    reading: SensorReadingResponse
    anomaly: Dict[str, Any] # Can hold AnomalyDetailResponse or AnomalyNotAvailable dicts

# Response schema for POST /api/anomaly/train/{machine_id}
class ModelTrainingResponse(BaseModel):
    machine_id: str
    status: str
    training_samples: int
    features: List[str]

class BehaviorChangeResponse(BaseModel):
    id: int
    machine_id: str
    detected_at: datetime
    parameter: str
    baseline_value: float
    recent_value: float
    percentage_change: float
    change_type: str
    change_score: float
    persistence_count: int
    status: str

    class Config:
        from_attributes = True
        orm_mode = True

class EnergyConfigResponse(BaseModel):
    tariff: float

class EnergyStatusResponse(BaseModel):
    machine_id: str
    operating_state: str
    current_power_kw: float
    baseline_power_kw: float
    difference_percentage: float
    energy_status: str  # NORMAL, ELEVATED, INEFFICIENT
    actual_energy_kwh: float
    expected_energy_kwh: float
    excess_energy_kwh: float
    estimated_excess_cost: float

class EnergySummaryResponse(BaseModel):
    machine_id: str
    period: str
    actual_energy_kwh: float
    expected_energy_kwh: float
    excess_energy_kwh: float
    excess_percentage: float
    estimated_excess_cost: float
    average_power: float

class FactoryOverviewResponse(BaseModel):
    total_energy_kwh: float
    expected_energy_kwh: float
    excess_energy_kwh: float
    estimated_excess_cost: float
    inefficient_machines: List[str]

class UnifiedEventResponse(BaseModel):
    id: int
    machine_id: str
    event_type: str
    severity: str
    timestamp: datetime
    title: str
    description: str
    evidence: Dict[str, Any] = {}
    status: str
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class DemoResetResponse(BaseModel):
    status: str
    message: str
    cleared_events_count: int
    reset_timestamp: datetime
