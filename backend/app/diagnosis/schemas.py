from typing import List, Optional, Any, Dict
from datetime import datetime
from pydantic import BaseModel, Field

class EvidenceItem(BaseModel):
    parameter: str
    baseline: Optional[float] = None
    current: Optional[float] = None
    change_percent: Optional[float] = None
    severity: str = "NORMAL"  # NORMAL, LOW, MODERATE, HIGH, CRITICAL
    source: str  # sensor_reading, anomaly_detection, behavioral_change, energy_intelligence
    description: str

class PossibleCause(BaseModel):
    cause: str  # MECHANICAL_DEGRADATION, OVERLOAD, OVERHEATING, ELECTRICAL_ANOMALY
    evidence_score: float = Field(..., ge=0.0, le=1.0)
    evidence: List[str]
    suggested_inspections: List[str]

class DiagnosisResponse(BaseModel):
    machine_id: str
    status: str  # DIAGNOSIS_AVAILABLE, INSUFFICIENT_EVIDENCE, NORMAL
    primary_cause: Optional[str] = None
    evidence_score: Optional[float] = None
    possible_causes: List[PossibleCause] = []
    evidence_items: List[EvidenceItem] = []
    explanation: str
    suggested_inspections: List[str] = []
    human_review_status: Optional[str] = "UNDER_REVIEW"
    event_id: Optional[int] = None
    timestamp: Optional[datetime] = None

    class Config:
        from_attributes = True
        orm_mode = True

class HumanReviewRequest(BaseModel):
    status: str = Field(..., description="Review status: UNDER_REVIEW, CONFIRMED, or REJECTED")
    notes: Optional[str] = None

class HumanReviewResponse(BaseModel):
    event_id: int
    machine_id: str
    human_review_status: str
    message: str

class DiagnosisOverviewItem(BaseModel):
    machine_id: str
    machine_name: str
    machine_type: str
    location: str
    primary_cause: str
    evidence_score: float
    priority: str  # HIGH, MEDIUM, LOW
    human_review_status: str
    event_id: Optional[int] = None
    timestamp: datetime

class DiagnosisOverviewResponse(BaseModel):
    machines_requiring_attention: List[DiagnosisOverviewItem]
    total_active_diagnoses: int
    unreviewed_count: int
