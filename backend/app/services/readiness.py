import importlib
import shutil
from pathlib import Path

from app.core.config import settings
from app.models.readiness import ReadinessCheck, ReadinessReport
from app.services.ai_providers import get_ai_provider


def _check_data_directory_writable() -> ReadinessCheck:
    try:
        data_dir = Path(settings.data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)
        probe = data_dir / ".readiness_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return ReadinessCheck(
            name="data_directory_writable",
            ok=True,
            required=True,
            detail="runtime data directory exists and is writable",
        )
    except OSError as exc:
        return ReadinessCheck(
            name="data_directory_writable",
            ok=False,
            required=True,
            detail=f"runtime data directory is not writable: {exc.strerror or exc}",
        )


def _check_ai_provider_configured() -> ReadinessCheck:
    try:
        provider = get_ai_provider()
        return ReadinessCheck(
            name="ai_provider_configured",
            ok=True,
            required=True,
            detail=f"configured provider '{settings.ai_provider}' resolved to '{provider.name}'",
        )
    except ValueError as exc:
        return ReadinessCheck(
            name="ai_provider_configured", ok=False, required=True, detail=str(exc)
        )


def _check_ffmpeg_available() -> ReadinessCheck:
    ffmpeg_ok = shutil.which("ffmpeg") is not None
    ffprobe_ok = shutil.which("ffprobe") is not None
    ok = ffmpeg_ok and ffprobe_ok
    return ReadinessCheck(
        name="ffmpeg_available",
        ok=ok,
        required=False,
        detail=(
            "ffmpeg/ffprobe found on PATH" if ok else "ffmpeg/ffprobe not found on PATH"
        )
        + " — only required for video asset audio/keyframe extraction; other modalities unaffected.",
    )


def _check_hachoir_available() -> ReadinessCheck:
    try:
        importlib.import_module("hachoir.parser")
        return ReadinessCheck(
            name="hachoir_available",
            ok=True,
            required=False,
            detail="hachoir importable",
        )
    except ImportError:
        return ReadinessCheck(
            name="hachoir_available",
            ok=False,
            required=False,
            detail=(
                "hachoir not importable — video technical-metadata extraction will fail "
                "per-asset (ingestion_status='failed' for that asset only); every other "
                "modality is unaffected."
            ),
        )


def build_readiness_report() -> ReadinessReport:
    """Runs only checks that are actually meaningful to run locally.
    `ready` is true iff every `required` check passes — an unavailable
    optional modality dependency (ffmpeg, hachoir) is reported for
    visibility but never marks the whole app unready."""
    checks = [
        _check_data_directory_writable(),
        _check_ai_provider_configured(),
        _check_ffmpeg_available(),
        _check_hachoir_available(),
    ]
    ready = all(check.ok for check in checks if check.required)
    return ReadinessReport(ready=ready, checks=checks)
