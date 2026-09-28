from fastapi import FastAPI

from app.api import (
    assets,
    health,
    intelligence,
    overview,
    processing_results,
    projects,
    questionnaires,
    reports,
    workflow,
)
from app.core.config import settings

app = FastAPI(title=settings.app_name)

app.include_router(health.router)
app.include_router(projects.router)
app.include_router(assets.router)
app.include_router(processing_results.router)
app.include_router(intelligence.router)
app.include_router(questionnaires.router)
app.include_router(reports.router)
app.include_router(overview.router)
app.include_router(workflow.router)
