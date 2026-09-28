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


class IntelligenceContext(TypedDict):
    """The already-generated ProjectIntelligence fields, as input to
    questionnaire generation. No new asset text is re-read here — a
    questionnaire is derived from intelligence output, not raw content."""

    summary: str
    top_themes: list[str]
    sentiment_summary: str
    pain_points: list[str]
    positive_signals: list[str]
    questions_or_concerns: list[str]
    opportunities: list[str]


class GeneratedQuestion(TypedDict):
    question_type: str
    text: str
    rationale: str
    related_theme: str | None
    required: bool
    options: list[str] | None


class QuestionnaireGenerationResult(TypedDict):
    questions: list[GeneratedQuestion]
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

    @abstractmethod
    def generate_questionnaire(
        self, intelligence: IntelligenceContext
    ) -> QuestionnaireGenerationResult:
        """Generates a follow-up questionnaire from already-synthesized
        project intelligence.

        Implementations must not invent new signals: every generated
        question's `related_theme` (when set) must be text that literally
        appears in `intelligence` — a theme, pain point, concern, or
        opportunity already produced by `synthesize_project`.
        """
