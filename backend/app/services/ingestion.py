import hashlib
import mimetypes
import uuid
from pathlib import Path
from typing import Any

from app.models.asset import MODALITY_BY_EXTENSION, Asset, IngestionStatus
from app.services import storage

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
AUDIO_EXTENSIONS = {".mp3", ".wav"}
VIDEO_EXTENSIONS = {".mp4"}


def _extract_image_metadata(path: Path) -> dict[str, Any]:
    from PIL import Image

    with Image.open(path) as img:
        return {"width": img.width, "height": img.height, "format": img.format}


def _extract_audio_metadata(path: Path) -> dict[str, Any]:
    import mutagen

    audio = mutagen.File(str(path))
    if audio is None or audio.info is None:
        return {"duration_seconds": None, "sample_rate": None, "channels": None}

    info = audio.info
    return {
        "duration_seconds": getattr(info, "length", None),
        "sample_rate": getattr(info, "sample_rate", None),
        "channels": getattr(info, "channels", None),
    }


def _extract_video_metadata(path: Path) -> dict[str, Any]:
    from hachoir.metadata import extractMetadata
    from hachoir.parser import createParser

    result: dict[str, Any] = {
        "duration_seconds": None,
        "width": None,
        "height": None,
        "fps": None,
    }

    parser = createParser(str(path))
    if parser is None:
        return result

    with parser:
        metadata = extractMetadata(parser)

    if metadata is None:
        return result

    if metadata.has("duration"):
        result["duration_seconds"] = metadata.get("duration").total_seconds()
    if metadata.has("width"):
        result["width"] = metadata.get("width")
    if metadata.has("height"):
        result["height"] = metadata.get("height")
    if metadata.has("frame_rate"):
        result["fps"] = float(metadata.get("frame_rate"))

    return result


def _extract_pdf_metadata(path: Path) -> dict[str, Any]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return {"page_count": len(reader.pages)}


def _extract_txt_metadata(content: bytes) -> dict[str, Any]:
    from charset_normalizer import from_bytes

    best = from_bytes(content).best()
    if best is None:
        text = content.decode("utf-8", errors="replace")
        encoding = "unknown"
    else:
        text = str(best)
        encoding = best.encoding

    return {
        "character_count": len(text),
        "line_count": len(text.splitlines()),
        "encoding": encoding,
    }


def _extract_technical_metadata(
    extension: str, absolute_path: Path, content: bytes
) -> tuple[dict[str, Any], IngestionStatus]:
    try:
        if extension in IMAGE_EXTENSIONS:
            metadata = _extract_image_metadata(absolute_path)
        elif extension in AUDIO_EXTENSIONS:
            metadata = _extract_audio_metadata(absolute_path)
        elif extension in VIDEO_EXTENSIONS:
            metadata = _extract_video_metadata(absolute_path)
        elif extension == ".pdf":
            metadata = _extract_pdf_metadata(absolute_path)
        elif extension == ".txt":
            metadata = _extract_txt_metadata(content)
        else:
            metadata = {}
        return metadata, IngestionStatus.completed
    except Exception as exc:
        return {"error": storage.redact_absolute_paths(str(exc))}, IngestionStatus.failed


def ingest_uploaded_file(project_id: str, original_filename: str, content: bytes) -> Asset:
    """Writes the uploaded file to disk and produces its normalized Asset record.

    Raises storage.ProjectNotFoundError or storage.UnsupportedFileTypeError,
    same as the underlying write, before anything is persisted.
    """
    write_info = storage.write_uploaded_file(project_id, original_filename, content)
    extension = write_info["extension"]
    absolute_path: Path = write_info["absolute_path"]

    modality = MODALITY_BY_EXTENSION[extension]
    mime_type, _ = mimetypes.guess_type(original_filename)
    sha256 = hashlib.sha256(content).hexdigest()
    technical_metadata, ingestion_status = _extract_technical_metadata(
        extension, absolute_path, content
    )

    asset = Asset(
        id=str(uuid.uuid4()),
        project_id=project_id,
        original_filename=original_filename,
        stored_filename=write_info["stored_filename"],
        stored_path=write_info["relative_path"],
        modality=modality,
        mime_type=mime_type or "application/octet-stream",
        extension=extension.lstrip("."),
        size_bytes=len(content),
        sha256=sha256,
        ingestion_status=ingestion_status,
        technical_metadata=technical_metadata,
    )

    storage.save_asset(asset)
    return asset
