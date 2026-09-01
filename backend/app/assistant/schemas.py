from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

class AssistantEvidenceItem(BaseModel):
    parameter: str = Field(..., description="Parameter or signal name")
    baseline: Optional[float] = Field(None, description="Historical baseline normal mean")
    current: Optional[float] = Field(None, description="Current observed reading or metric")
    variance: Optional[str] = Field(None, description="Percentage deviation or status label")
    note: str = Field(..., description="Human-readable explanation of this verified evidence point")

class AssistantQueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000, description="Natural language question from operator")
    conversation_id: Optional[str] = Field(None, description="Optional conversation session ID for follow-up pronoun resolution")
    active_machine_id: Optional[str] = Field(None, description="Optional currently selected machine in the UI")

class AssistantQueryResponse(BaseModel):
    question: str = Field(..., description="Echo of the input query")
    answer: str = Field(..., description="Verified plain-English response grounded in database telemetry")
    intent: str = Field(..., description="Classified query intent category")
    machine_id: Optional[str] = Field(None, description="Target machine ID if applicable")
    evidence: List[AssistantEvidenceItem] = Field(default_factory=list, description="List of verified data points and evidence")
    confidence: float = Field(default=1.0, description="Confidence score of the generated answer")
    suggestions: List[str] = Field(default_factory=list, description="Follow-up quick question suggestions")
    is_general_knowledge: bool = Field(default=False, description="True if answering a general industrial engineering concept")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Timestamp of the query response")

class QuickQuestionItem(BaseModel):
    label: str = Field(..., description="Short button text for UI chip")
    query: str = Field(..., description="Full natural language query")
    category: str = Field(..., description="Category group (e.g., General, Machine, Priority)")
