from fastapi import APIRouter, HTTPException

from app.models.intelligence import IntelligenceGenerateRequest, ProjectIntelligence
from app.services import intelligence, storage

router = APIRouter(prefix="/projects/{project_id}/intelligence", tags=["intelligence"])


@router.post("", response_model=ProjectIntelligence)
def generate_project_intelligence(
    project_id: str, payload: IntelligenceGenerateRequest = IntelligenceGenerateRequest()
):
    try:
        return intelligence.generate_project_intelligence(project_id, payload.provider)
    except storage.ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("", response_model=list[ProjectIntelligence])
def list_project_intelligence(project_id: str):
    try:
        return storage.list_project_intelligence(project_id)
    except storage.ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found")


@router.get("/{intelligence_id}", response_model=ProjectIntelligence)
def get_project_intelligence(project_id: str, intelligence_id: str):
    try:
        return storage.get_project_intelligence(project_id, intelligence_id)
    except storage.ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found")
    except storage.ProjectIntelligenceNotFoundError:
        raise HTTPException(status_code=404, detail="Project intelligence not found")
