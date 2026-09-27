from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Modality(str, Enum):
    audio = "audio"
    video = "video"
    image = "image"
    document = "document"


class IngestionStatus(str, Enum):
    completed = "completed"
    failed = "failed"


MODALITY_BY_EXTENSION: dict[str, Modality] = {
    ".mp3": Modality.audio,
    ".wav": Modality.audio,
    ".mp4": Modality.video,
    ".jpg": Modality.image,
    ".jpeg": Modality.image,
    ".png": Modality.image,
    ".pdf": Modality.document,
    ".txt": Modality.document,
}


class Asset(BaseModel):
    id: str
    project_id: str
    original_filename: str
    stored_filename: str
    stored_path: str
    modality: Modality
    mime_type: str
    extension: str
    size_bytes: int
    sha256: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ingestion_status: IngestionStatus
    technical_metadata: dict[str, Any] = Field(default_factory=dict)
