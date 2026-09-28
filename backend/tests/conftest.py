import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A TestClient backed by a throwaway data directory per test — never
    touches the real `data/` directory, and each test starts empty."""
    monkeypatch.setattr(settings, "data_dir", str(tmp_path / "data"))
    return TestClient(app)


@pytest.fixture
def project(client):
    resp = client.post("/projects", json={"name": "Test Project", "description": ""})
    assert resp.status_code == 200
    return resp.json()
