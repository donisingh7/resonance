from fastapi import APIRouter, HTTPException

from app.models.workflow import WorkflowRunResult
from app.services import storage, workflow

router = APIRouter(prefix="/projects/{project_id}/workflow", tags=["workflow"])


@router.post("/run", response_model=WorkflowRunResult)
def run_workflow(project_id: str):
    try:
        return workflow.run_workflow(project_id)
    except storage.ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found")
