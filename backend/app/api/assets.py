from fastapi import APIRouter, HTTPException

from app.models.asset import Asset
from app.services import storage

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
