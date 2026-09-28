from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class QuestionType(str, Enum):
    likert = "likert"
    multiple_choice = "multiple_choice"
    free_text = "free_text"
    yes_no = "yes_no"


class QuestionnaireStatus(str, Enum):
    completed = "completed"
    failed = "failed"


class Question(BaseModel):
    id: str
    question_type: QuestionType
    text: str
    rationale: str
    related_theme: str | None = None
    required: bool = True
    options: list[str] | None = None


class Questionnaire(BaseModel):
    id: str
    project_id: str
    intelligence_id: str
    provider: str
    status: QuestionnaireStatus
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    questions: list[Question] = Field(default_factory=list)
    error: str | None = None


class QuestionnaireGenerateRequest(BaseModel):
    provider: str | None = None
    intelligence_id: str | None = None


class QuestionnaireUpdateRequest(BaseModel):
    questions: list[Question]
