from fastapi import FastAPI

from app.api import assets, health, intelligence, processing_results, projects
from app.core.config import settings

app = FastAPI(title=settings.app_name)

app.include_router(health.router)
app.include_router(projects.router)
app.include_router(assets.router)
app.include_router(processing_results.router)
app.include_router(intelligence.router)
