from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class ProjectStatus(str, Enum):
    active = "active"
    archived = "archived"


class Project(BaseModel):
    id: str
    name: str
    description: str = ""
    status: ProjectStatus = ProjectStatus.active
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ProjectCreateRequest(BaseModel):
    name: str
    description: str = ""
