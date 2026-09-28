from fastapi import APIRouter, HTTPException

from app.models.overview import ProjectOverview
from app.services import overview, storage

router = APIRouter(prefix="/projects/{project_id}/overview", tags=["overview"])


@router.get("", response_model=ProjectOverview)
def get_project_overview(project_id: str):
    try:
        return overview.build_project_overview(project_id)
    except storage.ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found")
