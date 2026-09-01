import uuid
from typing import Dict, Optional, List, Any
from datetime import datetime
from sqlalchemy.orm import Session

from app.assistant.schemas import (
    AssistantQueryRequest,
    AssistantQueryResponse,
    AssistantEvidenceItem,
    QuickQuestionItem
)
from app.assistant.question_classifier import QuestionClassifier
from app.assistant.context_builder import ContextBuilder
from app.assistant.answer_generator import RuleBasedAnswerGenerator, LLMAnswerGenerator

# In-memory conversation context cache (maps conversation_id -> { "last_machine_id": "MOTOR-01", "updated_at": ... })
CONVERSATION_CACHE: Dict[str, Dict[str, Any]] = {}

QUICK_QUESTIONS: List[QuickQuestionItem] = [
    QuickQuestionItem(label="Factory Summary", query="Give me a summary of the factory.", category="Overview"),
    QuickQuestionItem(label="Top Priority", query="Which machine should I investigate first?", category="Health"),
    QuickQuestionItem(label="Energy Waste", query="Which machine is wasting the most energy?", category="Energy"),
    QuickQuestionItem(label="Anomalies", query="Which machines have anomalies?", category="Anomalies"),
    QuickQuestionItem(label="Behavior Changes", query="Which machines have changed behavior?", category="Behavior"),
    QuickQuestionItem(label="MOTOR-01 Power", query="What is MOTOR-01's current power?", category="Telemetry"),
    QuickQuestionItem(label="MOTOR-01 Diagnosis", query="What could be wrong with MOTOR-01?", category="Diagnosis")
]

class AssistantService:
    @classmethod
    def process_query(cls, db: Session, req: AssistantQueryRequest) -> AssistantQueryResponse:
        """
        Executes the verified AI query pipeline:
        1. Classifies question and extracts machine ID / parameters.
        2. Resolves conversational pronouns against session memory.
        3. Retrieves verified data from database and builds context.
        4. Generates grounded answer and extracts evidence.
        5. Updates conversation memory.
        """
        conv_id = req.conversation_id or str(uuid.uuid4())
        session_info = CONVERSATION_CACHE.get(conv_id, {})
        last_machine_id = session_info.get("last_machine_id")

        # 1. Extract Machine ID & Intent
        machine_id = QuestionClassifier.extract_machine_id(
            req.question,
            conversation_machine_id=last_machine_id,
            active_machine_id=req.active_machine_id
        )

        intent, metadata = QuestionClassifier.classify_intent(req.question, machine_id=machine_id)
        metadata["machine_id"] = machine_id

        # Update conversation session cache
        if machine_id:
            CONVERSATION_CACHE[conv_id] = {
                "last_machine_id": machine_id,
                "updated_at": datetime.utcnow()
            }

        # 2. Build Verified Context
        if machine_id:
            context = ContextBuilder.build_machine_context(db, machine_id)
            context["_db"] = db
        else:
            context = ContextBuilder.build_factory_context(db)
            context["_db"] = db

        # 3. Generate Answer
        # For complex diagnostic/health explanation questions, try LLM if configured
        llm_answer = None
        if intent in ["DIAGNOSIS", "HEALTH"] and machine_id:
            llm_answer = LLMAnswerGenerator.generate(req.question, context)

        if llm_answer:
            answer_text = llm_answer
            _, evidence_items, suggestions, is_general = RuleBasedAnswerGenerator.generate(intent, metadata, context)
        else:
            answer_text, evidence_items, suggestions, is_general = RuleBasedAnswerGenerator.generate(intent, metadata, context)

        return AssistantQueryResponse(
            question=req.question,
            answer=answer_text,
            intent=intent,
            machine_id=machine_id,
            evidence=evidence_items,
            confidence=1.0,
            suggestions=suggestions,
            is_general_knowledge=is_general,
            timestamp=datetime.utcnow()
        )

    @classmethod
    def get_quick_questions(cls) -> List[QuickQuestionItem]:
        return QUICK_QUESTIONS

    @classmethod
    def clear_conversation(cls, conversation_id: str) -> bool:
        if conversation_id in CONVERSATION_CACHE:
            del CONVERSATION_CACHE[conversation_id]
            return True
        return False
