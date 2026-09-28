from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Resonance"
    environment: str = "development"
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    data_dir: str = str(Path(__file__).resolve().parents[3] / "data")

    # AI provider selection. "mock" (default) requires no external credentials
    # and is what smoke tests / local development should run against.
    ai_provider: str = "mock"
    # Placeholder for a future real provider's API key. Never commit a real
    # value; set it in a local .env only.
    ai_api_key: str | None = None

    class Config:
        env_file = ".env"


settings = Settings()
