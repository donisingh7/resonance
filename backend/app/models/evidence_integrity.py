from pydantic import BaseModel, Field


class EvidenceIntegrityIssue(BaseModel):
    evidence_index: int
    category: str
    reason: str
    asset_id: str
    processing_result_id: str


class EvidenceIntegrityReport(BaseModel):
    """Result of checking one ProjectIntelligence's evidence list against
    the project's real assets/processing results. Never repairs or invents
    a replacement for an invalid reference — only reports what it finds."""

    intelligence_id: str
    project_id: str
    total_evidence_items: int
    valid_evidence_items: int
    invalid_evidence_items: int
    all_valid: bool
    issues: list[EvidenceIntegrityIssue] = Field(default_factory=list)
