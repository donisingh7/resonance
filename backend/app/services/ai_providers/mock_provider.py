from pathlib import Path

from app.services.ai_providers.base import AIProvider, ImageAnalysisResult, TranscriptionResult


class MockAIProvider(AIProvider):
    """Deterministic stand-in for a real transcription/vision provider.

    Produces clearly-labeled placeholder output derived from the file
    itself (name, size, dimensions) so behavior is stable and repeatable
    without any external API or credentials. Used as the default provider
    so the app is fully runnable offline.
    """

    name = "mock"

    def transcribe_audio(self, audio_path: Path) -> TranscriptionResult:
        size_bytes = audio_path.stat().st_size
        transcript = (
            f"[mock transcript] MockAIProvider does not perform real speech-to-text. "
            f"Placeholder transcription for '{audio_path.name}' ({size_bytes} bytes)."
        )
        return {
            "transcript": transcript,
            "metadata": {"mock": True, "source_file": audio_path.name, "size_bytes": size_bytes},
        }

    def analyze_image(self, image_path: Path) -> ImageAnalysisResult:
        from PIL import Image

        with Image.open(image_path) as img:
            width, height = img.size
            image_format = img.format

        visual_description = (
            f"[mock description] MockAIProvider does not perform real vision analysis. "
            f"Placeholder description for a {width}x{height} {image_format} image "
            f"'{image_path.name}'."
        )
        return {
            "extracted_text": None,
            "visual_description": visual_description,
            "metadata": {
                "mock": True,
                "source_file": image_path.name,
                "width": width,
                "height": height,
                "format": image_format,
            },
        }
