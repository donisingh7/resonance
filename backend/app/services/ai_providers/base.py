from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, TypedDict


class TranscriptionResult(TypedDict):
    transcript: str
    metadata: dict[str, Any]


class ImageAnalysisResult(TypedDict):
    extracted_text: str | None
    visual_description: str
    metadata: dict[str, Any]


class ProjectAssetContext(TypedDict):
    """One processed asset's bounded text content, as input to project synthesis."""

    asset_id: str
    processing_result_id: str
    source_filename: str
    modality: str
    text: str


class ProjectEvidenceItem(TypedDict):
    """A synthesis insight paired with the exact asset/excerpt that supports it.

    `excerpt`, when present, must be a real substring of the corresponding
    `ProjectAssetContext.text` that was passed in — never fabricated.
    """

    category: str
    statement: str
    asset_id: str
    processing_result_id: str
    source_filename: str
    excerpt: str | None


class ProjectSynthesisResult(TypedDict):
    summary: str
    top_themes: list[str]
    sentiment_summary: str
    pain_points: list[str]
    positive_signals: list[str]
    questions_or_concerns: list[str]
    opportunities: list[str]
    recommended_actions: list[str]
    evidence: list[ProjectEvidenceItem]
    metadata: dict[str, Any]


class AIProvider(ABC):
    """Interface for AI-dependent operations (transcription, vision, synthesis).

    Every provider used by the processing/intelligence services must
    implement this interface. Real cloud providers (e.g. a hosted
    transcription, vision, or LLM API) should live in a sibling module and
    register in `ai_providers/__init__.get_ai_provider`.
    """

    name: str

    @abstractmethod
    def transcribe_audio(self, audio_path: Path) -> TranscriptionResult:
        """Transcribes an audio file at `audio_path` into text."""

    @abstractmethod
    def analyze_image(self, image_path: Path) -> ImageAnalysisResult:
        """Extracts visible text and a visual description from an image."""

    @abstractmethod
    def synthesize_project(
        self, assets: list[ProjectAssetContext]
    ) -> ProjectSynthesisResult:
        """Synthesizes cross-asset project-level intelligence.

        `assets` is a bounded list of already-processed, non-empty per-asset
        text content. Implementations must not invent evidence: every
        `ProjectEvidenceItem` returned must reference an `asset_id` /
        `processing_result_id` present in `assets`, with an excerpt (if any)
        drawn from that asset's own `text`.
        """
