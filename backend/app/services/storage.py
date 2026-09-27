import re
import uuid
from pathlib import Path

from app.core.config import settings
from app.models.asset import MODALITY_BY_EXTENSION, Asset
from app.models.project import Project

ALLOWED_EXTENSIONS = set(MODALITY_BY_EXTENSION)


class ProjectNotFoundError(Exception):
    pass


class AssetNotFoundError(Exception):
    pass


class UnsupportedFileTypeError(Exception):
    pass


def project_root() -> Path:
    return Path(settings.data_dir).parent


def _data_root() -> Path:
    return Path(settings.data_dir) / "projects"


def _project_dir(project_id: str) -> Path:
    return _data_root() / project_id


def _project_file(project_id: str) -> Path:
    return _project_dir(project_id) / "project.json"


def uploads_dir(project_id: str) -> Path:
    return _project_dir(project_id) / "uploads"


def _assets_dir(project_id: str) -> Path:
    return _project_dir(project_id) / "assets"


def _asset_file(project_id: str, asset_id: str) -> Path:
    return _assets_dir(project_id) / f"{asset_id}.json"


def create_project(name: str, description: str) -> Project:
    project = Project(id=str(uuid.uuid4()), name=name, description=description)

    project_dir = _project_dir(project.id)
    project_dir.mkdir(parents=True, exist_ok=True)
    uploads_dir(project.id).mkdir(parents=True, exist_ok=True)
    _assets_dir(project.id).mkdir(parents=True, exist_ok=True)

    _project_file(project.id).write_text(project.model_dump_json(indent=2))
    return project


def get_project(project_id: str) -> Project:
    project_file = _project_file(project_id)
    if not project_file.exists():
        raise ProjectNotFoundError(project_id)

    return Project.model_validate_json(project_file.read_text())


def safe_stored_filename(original_filename: str, extension: str) -> str:
    stem = Path(original_filename).stem
    safe_stem = re.sub(r"[^A-Za-z0-9_-]+", "_", stem).strip("_") or "file"
    return f"{uuid.uuid4().hex}_{safe_stem}{extension}"


def write_uploaded_file(project_id: str, original_filename: str, content: bytes) -> dict:
    """Validates project + extension, writes bytes to disk, returns write info."""
    # raises ProjectNotFoundError if missing
    get_project(project_id)

    extension = Path(original_filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise UnsupportedFileTypeError(extension)

    target_dir = uploads_dir(project_id)
    target_dir.mkdir(parents=True, exist_ok=True)

    stored_filename = safe_stored_filename(original_filename, extension)
    absolute_path = target_dir / stored_filename
    absolute_path.write_bytes(content)

    return {
        "extension": extension,
        "stored_filename": stored_filename,
        "absolute_path": absolute_path,
        "relative_path": str(absolute_path.relative_to(project_root())),
    }


def save_asset(asset: Asset) -> None:
    assets_dir = _assets_dir(asset.project_id)
    assets_dir.mkdir(parents=True, exist_ok=True)
    _asset_file(asset.project_id, asset.id).write_text(asset.model_dump_json(indent=2))


def get_asset(project_id: str, asset_id: str) -> Asset:
    get_project(project_id)

    asset_file = _asset_file(project_id, asset_id)
    if not asset_file.exists():
        raise AssetNotFoundError(asset_id)

    return Asset.model_validate_json(asset_file.read_text())


def list_assets(project_id: str) -> list[Asset]:
    get_project(project_id)

    assets_dir = _assets_dir(project_id)
    if not assets_dir.exists():
        return []

    assets = [
        Asset.model_validate_json(asset_file.read_text())
        for asset_file in sorted(assets_dir.glob("*.json"))
    ]
    return sorted(assets, key=lambda asset: asset.created_at)
