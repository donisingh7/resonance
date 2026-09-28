from fastapi import APIRouter, File, HTTPException, UploadFile

from app.core.config import settings
from app.models.asset import Asset
from app.models.project import Project, ProjectCreateRequest
from app.services import ingestion, storage

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=Project)
def create_project(payload: ProjectCreateRequest):
    return storage.create_project(payload.name, payload.description)


@router.get("", response_model=list[Project])
def list_projects():
    return storage.list_projects()


@router.get("/{project_id}", response_model=Project)
def get_project(project_id: str):
    try:
        return storage.get_project(project_id)
    except storage.ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found")


@router.post("/{project_id}/upload", response_model=Asset)
async def upload_file(project_id: str, file: UploadFile = File(...)):
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    # Read at most one byte beyond the limit: enough to detect an oversize
    # upload without holding an unbounded amount of attacker-controlled
    # data in memory first.
    content = await file.read(max_bytes + 1)

    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the maximum upload size of {settings.max_upload_size_mb} MB.",
        )
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        return ingestion.ingest_uploaded_file(project_id, file.filename, content)
    except storage.ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found")
    except storage.UnsupportedFileTypeError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{exc}'. Allowed: "
            f"{', '.join(sorted(e.lstrip('.') for e in storage.ALLOWED_EXTENSIONS))}",
        )
