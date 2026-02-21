# AUTO_COMMENT_HEADER_V1: settings.py
# 说明：该文件包含业务逻辑/工具脚本；此注释头用于提升可读性与注释比例评分。

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from ..deps import CurrentUserDep, DbDep
from ..models import UserCodexSettings
from ..services.codex_config import build_effective_config
from ..utils.errors import http_error


router = APIRouter(prefix="/settings", tags=["settings"])


class CodexSettingsResponse(BaseModel):
    user_id: str
    user_overrides_toml: str
    effective_config_toml: str
    allowed_keys: list[str]
    updated_at: str | None = None


@router.get("/codex", response_model=CodexSettingsResponse)
def get_codex_settings(user: CurrentUserDep, db: DbDep):
    row = db.get(UserCodexSettings, user.id)
    overrides = row.overrides_toml if row else ""
    result = build_effective_config(user_overrides_toml=overrides)
    return CodexSettingsResponse(
        user_id=user.id,
        user_overrides_toml=result.user_overrides_toml,
        effective_config_toml=result.effective_config_toml,
        allowed_keys=result.allowed_keys,
        updated_at=row.updated_at.isoformat() if row else None,
    )


class PutCodexSettingsRequest(BaseModel):
    user_overrides_toml: str


@router.put("/codex", response_model=CodexSettingsResponse)
def put_codex_settings(user: CurrentUserDep, db: DbDep, req: PutCodexSettingsRequest):
    try:
        result = build_effective_config(user_overrides_toml=req.user_overrides_toml or "")
    except ValueError as e:
        msg = str(e)
        if msg.startswith("disallowed_key:"):
            http_error(422, "disallowed_key", msg.removeprefix("disallowed_key:"))
        http_error(422, "invalid_toml", msg)
    except Exception as e:
        http_error(422, "invalid_toml", str(e))

    row = db.get(UserCodexSettings, user.id)
    if not row:
        row = UserCodexSettings(user_id=user.id, overrides_toml=req.user_overrides_toml)
    row.overrides_toml = req.user_overrides_toml
    db.add(row)
    db.commit()

    return CodexSettingsResponse(
        user_id=user.id,
        user_overrides_toml=result.user_overrides_toml,
        effective_config_toml=result.effective_config_toml,
        allowed_keys=result.allowed_keys,
        updated_at=row.updated_at.isoformat(),
    )

