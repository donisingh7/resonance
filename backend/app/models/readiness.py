from pydantic import BaseModel, Field


class ReadinessCheck(BaseModel):
    name: str
    ok: bool
    required: bool
    detail: str


class ReadinessReport(BaseModel):
    """Structured capability/readiness snapshot. `ready` reflects only the
    `required` checks — an optional modality dependency being unavailable
    (e.g. ffmpeg, hachoir) is reported for visibility but never marks the
    whole app unready, since other modalities/features remain fully usable."""

    ready: bool
    checks: list[ReadinessCheck] = Field(default_factory=list)
