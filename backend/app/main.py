import time

from fastapi import FastAPI, Request

from app.api import (
    assets,
    health,
    intelligence,
    overview,
    processing_results,
    projects,
    questionnaires,
    readiness,
    reports,
    workflow,
)
from app.core.config import settings
from app.core.observability import log_event, new_operation_id

app = FastAPI(title=settings.app_name)

app.include_router(health.router)
app.include_router(readiness.router)
app.include_router(projects.router)
app.include_router(assets.router)
app.include_router(processing_results.router)
app.include_router(intelligence.router)
app.include_router(questionnaires.router)
app.include_router(reports.router)
app.include_router(overview.router)
app.include_router(workflow.router)


@app.middleware("http")
async def request_correlation_and_logging(request: Request, call_next):
    """Assigns a short correlation id to every request, echoes it back via
    `X-Request-ID`, and emits one structured log line per request (method,
    path, status code, duration) — never request/response bodies, which
    may contain uploaded file content or generated analysis text."""
    request_id = new_operation_id()
    started = time.monotonic()
    response = await call_next(request)
    duration_ms = round((time.monotonic() - started) * 1000, 1)
    response.headers["X-Request-ID"] = request_id
    log_event(
        {
            "operation": "http_request",
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        }
    )
    return response
