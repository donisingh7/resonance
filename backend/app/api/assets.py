from fastapi import APIRouter, HTTPException

from app.models.asset import Asset
from app.models.processing import ProcessingResult
from app.services import processing, storage

router = APIRouter(prefix="/projects/{project_id}/assets", tags=["assets"])


@router.get("", response_model=list[Asset])
def list_assets(project_id: str):
    try:
        return storage.list_assets(project_id)
    except storage.ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found")


@router.get("/{asset_id}", response_model=Asset)
def get_asset(project_id: str, asset_id: str):
    try:
        return storage.get_asset(project_id, asset_id)
    except storage.ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found")
    except storage.AssetNotFoundError:
        raise HTTPException(status_code=404, detail="Asset not found")


@router.post("/{asset_id}/process", response_model=ProcessingResult)
def process_asset(project_id: str, asset_id: str):
    try:
        return processing.process_asset(project_id, asset_id)
    except storage.ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found")
    except storage.AssetNotFoundError:
        raise HTTPException(status_code=404, detail="Asset not found")


@router.post("/{asset_id}/retry", response_model=ProcessingResult)
def retry_asset_processing(project_id: str, asset_id: str):
    """Re-runs processing for one asset, typically after a failure.

    Identical to POST .../process — a distinct route purely for UX
    discoverability (a "Retry" action next to a failed asset) — it reuses
    processing.process_asset() rather than duplicating any logic, and
    inherits its existing idempotency (overwrites the asset's one
    deterministic ProcessingResult rather than creating a duplicate).
    """
    try:
        return processing.process_asset(project_id, asset_id)
    except storage.ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found")
    except storage.AssetNotFoundError:
        raise HTTPException(status_code=404, detail="Asset not found")
