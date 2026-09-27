import json
import re
import uuid
from pathlib import Path

from app.core.config import settings
from app.models.project import Project

ALLOWED_EXTENSIONS = {
    ".mp3",
    ".wav",
    ".mp4",
    ".jpg",
    ".jpeg",
    ".png",
    ".pdf",
    ".txt",
}


class ProjectNotFoundError(Exception):
    pass


class UnsupportedFileTypeError(Exception):
    pass


def _data_root() -> Path:
    return Path(settings.data_dir) / "projects"


def _project_dir(project_id: str) -> Path:
    return _data_root() / project_id


def _project_file(project_id: str) -> Path:
    return _project_dir(project_id) / "project.json"


def _uploads_dir(project_id: str) -> Path:
    return _project_dir(project_id) / "uploads"


def create_project(name: str, description: str) -> Project:
    project = Project(id=str(uuid.uuid4()), name=name, description=description)

    project_dir = _project_dir(project.id)
    project_dir.mkdir(parents=True, exist_ok=True)
    _uploads_dir(project.id).mkdir(parents=True, exist_ok=True)

    _project_file(project.id).write_text(project.model_dump_json(indent=2))
    return project


def get_project(project_id: str) -> Project:
    project_file = _project_file(project_id)
    if not project_file.exists():
        raise ProjectNotFoundError(project_id)

    return Project.model_validate_json(project_file.read_text())


def _safe_stored_filename(original_filename: str, extension: str) -> str:
    stem = Path(original_filename).stem
    safe_stem = re.sub(r"[^A-Za-z0-9_-]+", "_", stem).strip("_") or "file"
    return f"{uuid.uuid4().hex}_{safe_stem}{extension}"


def save_upload(project_id: str, original_filename: str, content: bytes) -> dict:
    # raises ProjectNotFoundError if missing
    get_project(project_id)

    extension = Path(original_filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise UnsupportedFileTypeError(extension)

    uploads_dir = _uploads_dir(project_id)
    uploads_dir.mkdir(parents=True, exist_ok=True)

    stored_filename = _safe_stored_filename(original_filename, extension)
    stored_path = uploads_dir / stored_filename
    stored_path.write_bytes(content)

    return {
        "project_id": project_id,
        "original_filename": original_filename,
        "stored_filename": stored_filename,
        "stored_path": str(stored_path.relative_to(Path(settings.data_dir).parent)),
        "file_type": extension.lstrip("."),
        "size_bytes": len(content),
    }
