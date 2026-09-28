import shutil
import subprocess
from pathlib import Path


class FFmpegNotAvailableError(Exception):
    pass


def _require_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise FFmpegNotAvailableError("ffmpeg not found on PATH")


def probe_duration_seconds(video_path: Path) -> float | None:
    if shutil.which("ffprobe") is None:
        return None

    try:
        proc = subprocess.run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-show_entries",
                "format=duration",
                "-of",
                "csv=p=0",
                str(video_path),
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        return float(proc.stdout.strip())
    except (subprocess.CalledProcessError, ValueError, subprocess.TimeoutExpired):
        return None


def extract_audio(video_path: Path, output_path: Path) -> bool:
    """Extracts a mono 16kHz WAV track, suitable for transcription. Returns
    False (instead of raising) if the source has no audio track or ffmpeg
    otherwise fails, so callers can degrade gracefully."""
    _require_ffmpeg()

    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-vn",
            "-acodec",
            "pcm_s16le",
            "-ar",
            "16000",
            "-ac",
            "1",
            str(output_path),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    return result.returncode == 0 and output_path.exists()


def extract_keyframes(
    video_path: Path, output_dir: Path, timestamps: list[float]
) -> list[tuple[float, Path]]:
    """Extracts one JPEG frame per timestamp. Timestamps that fail to
    extract (e.g. past end of stream) are silently skipped."""
    _require_ffmpeg()

    frames: list[tuple[float, Path]] = []
    for index, timestamp in enumerate(timestamps):
        frame_path = output_dir / f"frame_{index}.jpg"
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                str(timestamp),
                "-i",
                str(video_path),
                "-frames:v",
                "1",
                "-q:v",
                "2",
                str(frame_path),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0 and frame_path.exists():
            frames.append((timestamp, frame_path))

    return frames
