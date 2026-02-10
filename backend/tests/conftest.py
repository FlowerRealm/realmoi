from __future__ import annotations

import os
from pathlib import Path
import shutil
import tempfile
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select


def _env_flag_is_true(name: str, default: bool = True) -> bool:
    """
    Parse boolean-like environment variable.

    Args:
        name: Environment variable name.
        default: Default value when env is missing.

    Returns:
        Parsed boolean value.
    """

    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() not in {"0", "false", "no", "off"}


def _seed_from_real_data(*, target_root: Path) -> None:
    """
    Seed isolated test data from real project data snapshot.

    Args:
        target_root: Isolated temporary root for current pytest session.

    Returns:
        None.
    """

    seed_db = Path(os.environ.get("REALMOI_TEST_SEED_DB_PATH", "data/realmoi.db"))
    seed_jobs = Path(os.environ.get("REALMOI_TEST_SEED_JOBS_ROOT", "jobs"))

    target_db = target_root / "test.db"
    target_jobs = target_root / "jobs"

    if seed_db.exists() and seed_db.is_file():
        target_db.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(seed_db, target_db)

    if seed_jobs.exists() and seed_jobs.is_dir():
        shutil.copytree(seed_jobs, target_jobs, dirs_exist_ok=True)


def _init_test_env() -> None:
    """
    Initialize isolated test env before importing backend modules.

    This must run at module import time, because backend settings/database
    are created during module import and read env vars only once.
    """

    root = Path(tempfile.mkdtemp(prefix="realmoi-pytest-"))
    inherit_real_data = _env_flag_is_true("REALMOI_TEST_INHERIT_REAL_DATA", default=True)
    if inherit_real_data:
        _seed_from_real_data(target_root=root)

    os.environ["REALMOI_DB_PATH"] = str(root / "test.db")
    os.environ.setdefault("REALMOI_JWT_SECRET", "test-secret")
    os.environ.setdefault("REALMOI_ALLOW_SIGNUP", "1")
    os.environ["REALMOI_JOBS_ROOT"] = str(root / "jobs")
    os.environ["REALMOI_CODEX_AUTH_JSON_PATH"] = str(root / "secrets" / "auth.json")
    os.environ.setdefault("REALMOI_ADMIN_USERNAME", "admin")
    os.environ.setdefault("REALMOI_ADMIN_PASSWORD", "admin-password-123")
    os.environ.setdefault("REALMOI_OPENAI_API_KEY", "sk-test")
    os.environ.setdefault("REALMOI_OPENAI_BASE_URL", "https://example.com")
    os.environ.setdefault("REALMOI_JUDGE_MCP_TOKEN", "test-judge-token")


_init_test_env()


def pytest_sessionstart(session: pytest.Session) -> None:
    """
    Print explicit test lifecycle start status.

    Args:
        session: Current pytest session.

    Returns:
        None.
    """

    started_at = datetime.now(tz=timezone.utc).isoformat(timespec="seconds")
    print(f"[realmoi-test] 状态=进行中 started_at={started_at}", flush=True)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """
    Print explicit test lifecycle finish status.

    Args:
        session: Current pytest session.
        exitstatus: Pytest exit status code.

    Returns:
        None.
    """

    finished_at = datetime.now(tz=timezone.utc).isoformat(timespec="seconds")
    result = "成功" if exitstatus == 0 else "失败"
    print(f"[realmoi-test] 状态=已结束 result={result} exit_code={exitstatus} finished_at={finished_at}", flush=True)


def _ensure_test_admin_user() -> None:
    """
    Ensure predictable admin credentials in isolated test database.

    Returns:
        None.
    """

    from backend.app.auth import hash_password  # noqa: WPS433
    from backend.app.db import SessionLocal  # noqa: WPS433
    from backend.app.models import User  # noqa: WPS433

    username = str(os.environ.get("REALMOI_ADMIN_USERNAME") or "admin").strip()
    password = str(os.environ.get("REALMOI_ADMIN_PASSWORD") or "admin-password-123")

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == username))
        if user is None:
            user = User(
                username=username,
                password_hash=hash_password(password),
                role="admin",
                is_disabled=False,
            )
            db.add(user)
        else:
            user.password_hash = hash_password(password)
            user.role = "admin"
            user.is_disabled = False
        db.commit()


@pytest.fixture(scope="session")
def client():
    from backend.app.main import app  # noqa: WPS433

    _ensure_test_admin_user()
    return TestClient(app)
