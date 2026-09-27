from fastapi import FastAPI

from app.api import health, projects
from app.core.config import settings

app = FastAPI(title=settings.app_name)

app.include_router(health.router)
app.include_router(projects.router)
