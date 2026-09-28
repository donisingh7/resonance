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


class AIProvider(ABC):
    """Interface for AI-dependent operations (transcription, vision).

    Every provider used by the processing service must implement this
    interface. Real cloud providers (e.g. a hosted transcription or vision
    API) should live in a sibling module and register in
    `ai_providers/__init__.get_ai_provider`.
    """

    name: str

    @abstractmethod
    def transcribe_audio(self, audio_path: Path) -> TranscriptionResult:
        """Transcribes an audio file at `audio_path` into text."""

    @abstractmethod
    def analyze_image(self, image_path: Path) -> ImageAnalysisResult:
        """Extracts visible text and a visual description from an image."""
