from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.assistant.schemas import (
    AssistantQueryRequest,
    AssistantQueryResponse,
    QuickQuestionItem
)
from app.assistant.assistant_service import AssistantService

router = APIRouter(prefix="/api/assistant", tags=["assistant"])

@router.post("/query", response_model=AssistantQueryResponse)
def query_assistant(req: AssistantQueryRequest, db: Session = Depends(get_db)):
    """Process natural language question and return verified, grounded answer and evidence."""
    try:
        return AssistantService.process_query(db, req)
    except Exception as e:
        print(f"[Assistant Route Error] Failed to process query: {e}")
        return AssistantQueryResponse(
            question=req.question,
            answer="I couldn't generate a verified answer from the available GridLite data.",
            intent="UNKNOWN",
            machine_id=req.active_machine_id,
            evidence=[],
            confidence=0.0,
            suggestions=["Give me a factory summary.", "Which machine should I investigate first?"]
        )

@router.get("/quick-questions", response_model=List[QuickQuestionItem])
def get_quick_questions():
    """Retrieve list of suggested quick questions for the UI."""
    return AssistantService.get_quick_questions()

@router.delete("/conversations/{conversation_id}")
def clear_conversation(conversation_id: str):
    """Clear conversation history for a session."""
    cleared = AssistantService.clear_conversation(conversation_id)
    return {"conversation_id": conversation_id, "cleared": cleared}
