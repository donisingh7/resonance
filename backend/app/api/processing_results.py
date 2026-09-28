from fastapi import APIRouter, HTTPException

from app.models.processing import ProcessingResult
from app.services import storage

router = APIRouter(prefix="/projects/{project_id}/processing-results", tags=["processing-results"])


@router.get("", response_model=list[ProcessingResult])
def list_processing_results(project_id: str):
    try:
        return storage.list_processing_results(project_id)
    except storage.ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found")


@router.get("/{result_id}", response_model=ProcessingResult)
def get_processing_result(project_id: str, result_id: str):
    try:
        return storage.get_processing_result(project_id, result_id)
    except storage.ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found")
    except storage.ProcessingResultNotFoundError:
        raise HTTPException(status_code=404, detail="Processing result not found")
