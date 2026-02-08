from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def client(tmp_path_factory: pytest.TempPathFactory):
    root = tmp_path_factory.mktemp("realmoi")
    os.environ["REALMOI_DB_PATH"] = str(root / "test.db")
    os.environ["REALMOI_JWT_SECRET"] = "test-secret"
    os.environ["REALMOI_ALLOW_SIGNUP"] = "1"
    os.environ["REALMOI_JOBS_ROOT"] = str(root / "jobs")
    os.environ["REALMOI_CODEX_AUTH_JSON_PATH"] = str(root / "secrets" / "auth.json")
    os.environ["REALMOI_ADMIN_USERNAME"] = "admin"
    os.environ["REALMOI_ADMIN_PASSWORD"] = "admin-password-123"
    os.environ["REALMOI_OPENAI_API_KEY"] = "sk-test"
    os.environ["REALMOI_OPENAI_BASE_URL"] = "https://example.com"

    # Import after env set so Settings reads the right values.
    from backend.app.main import app  # noqa: WPS433

    return TestClient(app)
