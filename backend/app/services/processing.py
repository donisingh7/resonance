import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from app.models.asset import Asset, Modality
from app.models.processing import ProcessingResult, ProcessingStatus
from app.services import storage, video_tools
from app.services.ai_providers import get_ai_provider
from app.services.ai_providers.base import AIProvider

MAX_VIDEO_KEYFRAMES = 3


def _deterministic_result_id(asset_id: str, provider_name: str) -> str:
    """Stable id per (asset, provider) so re-processing overwrites the
    previous result instead of accumulating duplicates."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"resonance-processing:{asset_id}:{provider_name}"))


def _process_document(asset: Asset, absolute_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    if asset.extension == "pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(absolute_path))
        pages = [
            {"page_number": index + 1, "text": page.extract_text() or ""}
            for index, page in enumerate(reader.pages)
        ]
        extracted_text = "\n\n".join(page["text"] for page in pages)
        return (
            {"extracted_text": extracted_text},
            {"page_count": len(pages), "pages": pages},
        )

    if asset.extension == "txt":
        raw = absolute_path.read_bytes()
        encoding = asset.technical_metadata.get("encoding") or "utf-8"
        try:
            text = raw.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            from charset_normalizer import from_bytes

            best = from_bytes(raw).best()
            text = str(best) if best is not None else raw.decode("utf-8", errors="replace")
            encoding = best.encoding if best is not None else "unknown"

        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        return (
            {"extracted_text": normalized},
            {"encoding_used": encoding, "character_count": len(normalized)},
        )

    raise ValueError(f"Unsupported document extension: {asset.extension}")


def _process_image(
    absolute_path: Path, provider: AIProvider
) -> tuple[dict[str, Any], dict[str, Any]]:
    analysis = provider.analyze_image(absolute_path)
    return (
        {
            "extracted_text": analysis["extracted_text"],
            "visual_description": analysis["visual_description"],
        },
        analysis["metadata"],
    )


def _process_audio(
    absolute_path: Path, provider: AIProvider
) -> tuple[dict[str, Any], dict[str, Any]]:
    transcription = provider.transcribe_audio(absolute_path)
    return ({"transcript": transcription["transcript"]}, transcription["metadata"])


def _process_video(
    asset: Asset, absolute_path: Path, provider: AIProvider
) -> tuple[dict[str, Any], dict[str, Any]]:
    tmp_dir = storage.runtime_tmp_dir() / uuid.uuid4().hex
    tmp_dir.mkdir(parents=True, exist_ok=True)

    try:
        duration = asset.technical_metadata.get("duration_seconds")
        if not duration:
            duration = video_tools.probe_duration_seconds(absolute_path)

        if duration and duration > 0:
            timestamps = [duration * fraction for fraction in (0.1, 0.5, 0.9)][
                :MAX_VIDEO_KEYFRAMES
            ]
        else:
            timestamps = [0.0]

        audio_path = tmp_dir / "audio.wav"
        audio_extracted = video_tools.extract_audio(absolute_path, audio_path)

        transcript = None
        audio_metadata: dict[str, Any] = {}
        if audio_extracted:
            transcription = provider.transcribe_audio(audio_path)
            transcript = transcription["transcript"]
            audio_metadata = transcription["metadata"]

        frames = video_tools.extract_keyframes(absolute_path, tmp_dir, timestamps)

        frame_descriptions = []
        frame_texts = []
        frame_details = []
        for timestamp, frame_path in frames:
            analysis = provider.analyze_image(frame_path)
            frame_descriptions.append(
                f"Frame at {timestamp:.2f}s: {analysis['visual_description']}"
            )
            if analysis["extracted_text"]:
                frame_texts.append(f"Frame at {timestamp:.2f}s: {analysis['extracted_text']}")
            frame_details.append(
                {"timestamp_seconds": timestamp, "metadata": analysis["metadata"]}
            )

        result_fields = {
            "transcript": transcript,
            "visual_description": "\n".join(frame_descriptions) or None,
            "extracted_text": "\n".join(frame_texts) or None,
        }
        modality_metadata = {
            "duration_seconds": duration,
            "audio_extracted": audio_extracted,
            "audio_metadata": audio_metadata,
            "frame_count": len(frames),
            "frames": frame_details,
        }
        return result_fields, modality_metadata
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def process_asset(project_id: str, asset_id: str) -> ProcessingResult:
    """Processes a single asset per its modality and persists the result.

    Raises storage.ProjectNotFoundError / storage.AssetNotFoundError if the
    asset doesn't exist. A failure during modality-specific processing does
    not raise: it is captured as a failed ProcessingResult instead, so one
    bad asset never corrupts the project or blocks other assets.
    """
    asset = storage.get_asset(project_id, asset_id)
    provider = get_ai_provider()
    result_id = _deterministic_result_id(asset.id, provider.name)
    absolute_path = storage.project_root() / asset.stored_path

    start = time.monotonic()
    try:
        if asset.modality == Modality.document:
            result_fields, modality_metadata = _process_document(asset, absolute_path)
        elif asset.modality == Modality.image:
            result_fields, modality_metadata = _process_image(absolute_path, provider)
        elif asset.modality == Modality.audio:
            result_fields, modality_metadata = _process_audio(absolute_path, provider)
        elif asset.modality == Modality.video:
            result_fields, modality_metadata = _process_video(asset, absolute_path, provider)
        else:
            raise ValueError(f"Unsupported modality: {asset.modality}")

        result = ProcessingResult(
            id=result_id,
            project_id=project_id,
            asset_id=asset.id,
            modality=asset.modality,
            status=ProcessingStatus.completed,
            provider=provider.name,
            modality_metadata=modality_metadata,
            processing_metadata={
                "provider": provider.name,
                "duration_ms": int((time.monotonic() - start) * 1000),
            },
            **result_fields,
        )
    except Exception as exc:
        result = ProcessingResult(
            id=result_id,
            project_id=project_id,
            asset_id=asset.id,
            modality=asset.modality,
            status=ProcessingStatus.failed,
            provider=provider.name,
            processing_metadata={
                "provider": provider.name,
                "duration_ms": int((time.monotonic() - start) * 1000),
            },
            error=str(exc),
        )

    storage.save_processing_result(result)
    return result
