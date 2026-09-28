from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.models.intelligence import EvidenceItem


class ReportStatus(str, Enum):
    completed = "completed"
    failed = "failed"


class RiskSeverity(str, Enum):
    info = "info"
    warning = "warning"
    critical = "critical"


class RiskFlag(BaseModel):
    """A deterministic, rule-based pipeline/data-quality flag.

    These are NOT a content-moderation or safety classifier — they only
    check trustworthiness of the reporting pipeline itself (failures,
    exclusions, missing evidence, mock-provider output, coverage gaps).
    """

    code: str
    severity: RiskSeverity
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class QuestionnaireSummary(BaseModel):
    questionnaire_id: str
    question_count: int
    status: str


class ExecutiveReport(BaseModel):
    id: str
    project_id: str
    intelligence_id: str
    questionnaire_id: str | None = None
    status: ReportStatus
    provider: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    executive_summary: str = ""
    source_coverage: dict[str, Any] = Field(default_factory=dict)
    overall_sentiment: str = ""
    top_themes: list[str] = Field(default_factory=list)
    pain_points: list[str] = Field(default_factory=list)
    positive_signals: list[str] = Field(default_factory=list)
    questions_or_concerns: list[str] = Field(default_factory=list)
    opportunities: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    questionnaire_summary: QuestionnaireSummary | None = None
    risk_flags: list[RiskFlag] = Field(default_factory=list)
    pdf_path: str | None = None
    error: str | None = None


class ReportGenerateRequest(BaseModel):
    intelligence_id: str | None = None
    questionnaire_id: str | None = None
