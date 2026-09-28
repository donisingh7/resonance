from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.models.asset import Modality


class ProcessingStatus(str, Enum):
    completed = "completed"
    failed = "failed"


class ProcessingResult(BaseModel):
    id: str
    project_id: str
    asset_id: str
    modality: Modality
    status: ProcessingStatus
    provider: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    extracted_text: str | None = None
    transcript: str | None = None
    visual_description: str | None = None
    modality_metadata: dict[str, Any] = Field(default_factory=dict)
    processing_metadata: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
