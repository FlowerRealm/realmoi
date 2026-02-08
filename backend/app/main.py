from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import and_, func, select

from .auth import hash_password
from .db import init_db
from .exceptions import install_exception_handlers
from .models import User
from .routers import admin, auth, billing, jobs, models, settings
from .services.job_manager import JobManager
from .settings import SETTINGS


def _bootstrap_admin() -> None:
    if not SETTINGS.admin_username or not SETTINGS.admin_password:
        return
    from .db import SessionLocal  # noqa: WPS433

    with SessionLocal() as db:
        active_admins = db.scalar(
            select(func.count()).select_from(User).where(and_(User.role == "admin", User.is_disabled == False))  # noqa: E712
        )
        if (active_admins or 0) > 0:
            return

        admin_user = User(
            username=SETTINGS.admin_username.strip(),
            password_hash=hash_password(SETTINGS.admin_password),
            role="admin",
            is_disabled=False,
        )
        db.add(admin_user)
        db.commit()


def _sync_auth_json() -> None:
    if not SETTINGS.openai_api_key:
        return
    auth_path = Path(SETTINGS.codex_auth_json_path)
    auth_path.parent.mkdir(parents=True, exist_ok=True)
    auth_path.write_text(
        json.dumps({"OPENAI_API_KEY": SETTINGS.openai_api_key}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def create_app() -> FastAPI:
    SETTINGS.ensure_dirs()
    init_db()
    _bootstrap_admin()
    _sync_auth_json()

    app = FastAPI(title="realmoi", version="0.1.0")
    install_exception_handlers(app)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth.router, prefix="/api")
    app.include_router(admin.router, prefix="/api")
    app.include_router(models.router, prefix="/api")
    app.include_router(settings.router, prefix="/api")
    app.include_router(jobs.router, prefix="/api")
    app.include_router(billing.router, prefix="/api")

    return app


app = create_app()


# Singletons
from .services import singletons  # noqa: WPS433,E402

JOB_MANAGER = JobManager(jobs_root=Path(SETTINGS.jobs_root))
singletons.JOB_MANAGER = JOB_MANAGER
JOB_MANAGER.reconcile()

