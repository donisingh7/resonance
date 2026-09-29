from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Resonance"
    environment: str = "development"
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    data_dir: str = str(Path(__file__).resolve().parents[3] / "data")

    # AI provider selection: "mock" (default, no external credentials needed)
    # or "openai" (requires the openai_* settings below).
    ai_provider: str = "mock"

    # OpenAI provider configuration (P1.2). Only required when
    # ai_provider="openai"; OpenAIProvider.__init__ validates these are set
    # and raises a clear configuration error otherwise. Never has a
    # hardcoded model default here — model names must come from .env since
    # model availability changes over time. Never commit a real API key;
    # set it in a local .env only.
    openai_api_key: str | None = None
    openai_text_model: str | None = None
    openai_transcribe_model: str | None = None

    # Upload size guardrail, enforced at the API boundary in api/projects.py.
    # 25 MB is a reasonable local-development default for TXT/PDF/image/
    # short audio-video fixtures; raise it in .env for larger real files.
    max_upload_size_mb: int = 25

    class Config:
        env_file = ".env"


settings = Settings()
