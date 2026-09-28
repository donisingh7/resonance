from enum import Enum

from pydantic import BaseModel, Field


class StageStatus(str, Enum):
    not_started = "not_started"
    ready = "ready"
    in_progress = "in_progress"
    partial = "partial"
    completed = "completed"
    blocked = "blocked"
    failed = "failed"


class ProjectOverview(BaseModel):
    """A read-only snapshot of a project's pipeline state, derived entirely
    from already-persisted data (assets, processing results, intelligence,
    questionnaires, reports). No progress percentage is computed — status
    is always a discrete stage derived from what actually exists on disk.
    """

    project_id: str
    project_name: str
    total_assets: int
    assets_by_modality: dict[str, int] = Field(default_factory=dict)
    processed_assets: int
    failed_processing_assets: int
    pending_processing_assets: int
    latest_intelligence_id: str | None = None
    intelligence_status: str | None = None
    active_provider: str | None = None
    questionnaire_available: bool = False
    latest_questionnaire_id: str | None = None
    report_available: bool = False
    latest_report_id: str | None = None
    pdf_available: bool = False
    overall_pipeline_status: StageStatus
    current_stage: str
    next_recommended_action: str
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
