from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime

class SignalScoreItem(BaseModel):
    name: str
    normalized_score: float = Field(..., ge=0.0, le=1.0)
    rating: str  # HIGH, MEDIUM, LOW, NORMAL
    details: str

class MachineHealthResponse(BaseModel):
    machine_id: str
    machine_type: str
    health_status: str  # HEALTHY, WATCH, ATTENTION, CRITICAL
    priority_score: int = Field(..., ge=0, le=100)
    primary_reason: str
    contributing_factors: List[str]
    signals: Dict[str, SignalScoreItem]
    active_issues: List[str]
    operator_status: str  # INVESTIGATE, UNDER_REVIEW, RESOLVED
    event_id: Optional[int] = None
    timestamp: datetime

    class Config:
        from_attributes = True

class HealthOverviewItem(BaseModel):
    machine_id: str
    machine_name: str
    machine_type: str
    location: str
    health_status: str
    priority_score: int
    primary_reason: str
    operator_status: str
    active_issues_count: int

class HealthOverviewResponse(BaseModel):
    total_machines: int
    healthy_count: int
    watch_count: int
    attention_count: int
    critical_count: int
    top_priority_machine: Optional[str] = None
    machines: List[HealthOverviewItem]
    ranked_machines: Optional[List[HealthOverviewItem]] = None

class OperatorReviewRequest(BaseModel):
    status: str  # INVESTIGATE, UNDER_REVIEW, RESOLVED

class OperatorReviewResponse(BaseModel):
    event_id: int
    operator_status: str
    message: str

class HealthEventHistoryItem(BaseModel):
    id: int
    machine_id: str
    timestamp: datetime
    health_status: str
    priority_score: int
    primary_reason: str
    contributing_factors: List[str]
    operator_status: str
    status: str  # ACTIVE, RESOLVED
