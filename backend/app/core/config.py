from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Resonance"
    environment: str = "development"
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    data_dir: str = str(Path(__file__).resolve().parents[3] / "data")

    class Config:
        env_file = ".env"


settings = Settings()
