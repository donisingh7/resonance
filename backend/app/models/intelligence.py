from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class IntelligenceStatus(str, Enum):
    completed = "completed"
    failed = "failed"


class EvidenceItem(BaseModel):
    """A single generated insight traced back to the asset/result that supports it."""

    category: str
    statement: str
    asset_id: str
    processing_result_id: str
    source_filename: str
    excerpt: str | None = None


class ProjectIntelligence(BaseModel):
    id: str
    project_id: str
    status: IntelligenceStatus
    provider: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source_result_ids: list[str] = Field(default_factory=list)
    summary: str = ""
    top_themes: list[str] = Field(default_factory=list)
    sentiment_summary: str = ""
    pain_points: list[str] = Field(default_factory=list)
    positive_signals: list[str] = Field(default_factory=list)
    questions_or_concerns: list[str] = Field(default_factory=list)
    opportunities: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    processing_metadata: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class IntelligenceGenerateRequest(BaseModel):
    provider: str | None = None
