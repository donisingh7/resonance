from fastapi import APIRouter, File, HTTPException, UploadFile

from app.models.asset import Asset
from app.models.project import Project, ProjectCreateRequest
from app.services import ingestion, storage

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=Project)
def create_project(payload: ProjectCreateRequest):
    return storage.create_project(payload.name, payload.description)


@router.get("/{project_id}", response_model=Project)
def get_project(project_id: str):
    try:
        return storage.get_project(project_id)
    except storage.ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found")


@router.post("/{project_id}/upload", response_model=Asset)
async def upload_file(project_id: str, file: UploadFile = File(...)):
    content = await file.read()

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
