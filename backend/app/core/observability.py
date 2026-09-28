"""Lightweight structured logging for important operations.

Not an external monitoring integration — just one structured JSON log line
per tracked operation (and per HTTP request, via the middleware registered
in main.py), written through the standard `logging` module. Good enough to
grep/pipe locally or into any log aggregator later without committing to one.

Callers must never pass file contents, extracted text, transcripts, evidence
excerpts, secrets, or API keys into a tracked field — only identifiers,
status, timing, and short error summaries.
"""

import json
import logging
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger("resonance")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def new_operation_id() -> str:
    """A short, non-secret correlation id for one logical operation or HTTP request."""
    return uuid.uuid4().hex[:12]


def log_event(event: dict[str, Any]) -> None:
    """Emits one structured JSON log line."""
    logger.info(json.dumps(event, default=str))


@contextmanager
def track_operation(operation: str, **fields: Any) -> Iterator[dict[str, Any]]:
    """Times a block of work and emits one structured log line describing it.

    Usage:
        with track_operation("process_asset", project_id=pid, asset_id=aid) as op:
            ...
            op["status"] = result.status.value  # override the "completed" default

    `fields` seed the log record (e.g. project_id, asset_id, provider) and
    the block may add more via the yielded dict before it exits. On an
    uncaught exception, status/error_type/error_message are filled in
    automatically and the exception is re-raised unchanged — this never
    swallows an error, it only ensures one is always logged for it.
    """
    record: dict[str, Any] = {
        "operation": operation,
        "operation_id": new_operation_id(),
        "status": "completed",
        **fields,
    }
    started = time.monotonic()
    try:
        yield record
    except Exception as exc:
        record["status"] = "failed"
        record["error_type"] = type(exc).__name__
        record["error_message"] = str(exc)[:300]
        raise
    finally:
        record["duration_ms"] = round((time.monotonic() - started) * 1000, 1)
        log_event(record)
