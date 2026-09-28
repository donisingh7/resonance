from fastapi import APIRouter, HTTPException

from app.models.questionnaire import (
    Questionnaire,
    QuestionnaireGenerateRequest,
    QuestionnaireUpdateRequest,
)
from app.services import questionnaire, storage

router = APIRouter(prefix="/projects/{project_id}/questionnaires", tags=["questionnaires"])


@router.post("", response_model=Questionnaire)
def generate_questionnaire(
    project_id: str, payload: QuestionnaireGenerateRequest = QuestionnaireGenerateRequest()
):
    try:
        return questionnaire.generate_questionnaire(
            project_id, payload.intelligence_id, payload.provider
        )
    except storage.ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found")
    except storage.ProjectIntelligenceNotFoundError:
        raise HTTPException(status_code=404, detail="Project intelligence not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("", response_model=list[Questionnaire])
def list_questionnaires(project_id: str):
    try:
        return storage.list_questionnaires(project_id)
    except storage.ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found")


@router.get("/{questionnaire_id}", response_model=Questionnaire)
def get_questionnaire(project_id: str, questionnaire_id: str):
    try:
        return storage.get_questionnaire(project_id, questionnaire_id)
    except storage.ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found")
    except storage.QuestionnaireNotFoundError:
        raise HTTPException(status_code=404, detail="Questionnaire not found")


@router.put("/{questionnaire_id}", response_model=Questionnaire)
def update_questionnaire(
    project_id: str, questionnaire_id: str, payload: QuestionnaireUpdateRequest
):
    try:
        return questionnaire.update_questionnaire(project_id, questionnaire_id, payload.questions)
    except storage.ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found")
    except storage.QuestionnaireNotFoundError:
        raise HTTPException(status_code=404, detail="Questionnaire not found")
