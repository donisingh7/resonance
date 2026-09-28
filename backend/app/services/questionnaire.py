import uuid
from datetime import datetime, timezone

from app.models.questionnaire import Question, Questionnaire, QuestionnaireStatus
from app.services import intelligence as intelligence_service
from app.services import storage
from app.services.ai_providers import get_ai_provider
from app.services.ai_providers.base import IntelligenceContext


def _deterministic_questionnaire_id(intelligence_id: str, provider_name: str) -> str:
    """Stable id per (intelligence_id, provider), mirroring the idempotency
    strategy used for processing results and project intelligence:
    regenerating overwrites the previous questionnaire instead of creating
    a duplicate."""
    return str(
        uuid.uuid5(uuid.NAMESPACE_URL, f"resonance-questionnaire:{intelligence_id}:{provider_name}")
    )


def generate_questionnaire(
    project_id: str, intelligence_id: str | None = None, provider_name: str | None = None
) -> Questionnaire:
    """Generates a follow-up questionnaire from a project's intelligence.

    Raises storage.ProjectNotFoundError / storage.ProjectIntelligenceNotFoundError
    if the project or a specifically-requested intelligence id doesn't
    exist. Raises ValueError if no intelligence exists at all and none was
    specified. A provider failure is caught and turned into a
    status="failed" Questionnaire, mirroring processing.py/intelligence.py.
    """
    storage.get_project(project_id)
    target_intelligence = intelligence_service.resolve_intelligence(project_id, intelligence_id)

    provider = get_ai_provider(provider_name)
    questionnaire_id = _deterministic_questionnaire_id(target_intelligence.id, provider.name)
    now = datetime.now(timezone.utc)

    intelligence_context: IntelligenceContext = {
        "summary": target_intelligence.summary,
        "top_themes": target_intelligence.top_themes,
        "sentiment_summary": target_intelligence.sentiment_summary,
        "pain_points": target_intelligence.pain_points,
        "positive_signals": target_intelligence.positive_signals,
        "questions_or_concerns": target_intelligence.questions_or_concerns,
        "opportunities": target_intelligence.opportunities,
    }

    try:
        generation = provider.generate_questionnaire(intelligence_context)
        questions = [Question(id=str(uuid.uuid4()), **q) for q in generation["questions"]]
        questionnaire = Questionnaire(
            id=questionnaire_id,
            project_id=project_id,
            intelligence_id=target_intelligence.id,
            provider=provider.name,
            status=QuestionnaireStatus.completed,
            created_at=now,
            updated_at=now,
            questions=questions,
        )
    except Exception as exc:
        questionnaire = Questionnaire(
            id=questionnaire_id,
            project_id=project_id,
            intelligence_id=target_intelligence.id,
            provider=provider.name,
            status=QuestionnaireStatus.failed,
            created_at=now,
            updated_at=now,
            error=str(exc),
        )

    storage.save_questionnaire(questionnaire)
    return questionnaire


def update_questionnaire(
    project_id: str, questionnaire_id: str, questions: list[Question]
) -> Questionnaire:
    """Replaces a questionnaire's question list (manual edit), preserving
    its id/created_at/status and bumping updated_at. Raises
    storage.ProjectNotFoundError / storage.QuestionnaireNotFoundError if
    either doesn't exist."""
    existing = storage.get_questionnaire(project_id, questionnaire_id)
    updated = existing.model_copy(
        update={"questions": questions, "updated_at": datetime.now(timezone.utc)}
    )
    storage.save_questionnaire(updated)
    return updated
