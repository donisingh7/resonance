from datetime import datetime, timezone

from pydantic import BaseModel, Field

from app.models.overview import ProjectOverview


class WorkflowRunResult(BaseModel):
    """The outcome of one synchronous orchestration run: which pipeline
    stages were attempted/completed/skipped, what happened to each pending
    asset, and which intelligence/questionnaire/report were generated or
    reused. Every id here refers to a real persisted record — nothing is
    fabricated."""

    project_id: str
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    stages_attempted: list[str] = Field(default_factory=list)
    stages_completed: list[str] = Field(default_factory=list)
    stages_skipped: list[str] = Field(default_factory=list)
    asset_processing_successes: list[str] = Field(default_factory=list)
    asset_processing_failures: list[str] = Field(default_factory=list)
    intelligence_id: str | None = None
    intelligence_action: str = "skipped"
    questionnaire_id: str | None = None
    questionnaire_action: str = "skipped"
    report_id: str | None = None
    report_action: str = "skipped"
    warnings: list[str] = Field(default_factory=list)
    overview: ProjectOverview
