from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import UpstreamChannel
from ..settings import SETTINGS

# 上游通道解析与合并逻辑。
#
# 数据来源：
# - env: `SETTINGS.upstream_channels_json`（用于快速配置/CI/开发）
# - db: `UpstreamChannel` 表（用于后台管理持久化）
#
# 合并规则：db 覆盖 env（同名 channel 以 db 为准）。
# 该模块只做解析与校验，不做实际请求。


@dataclass(frozen=True)
class UpstreamTarget:
    channel: str
    base_url: str
    api_key: str
    models_path: str


@dataclass(frozen=True)
class UpstreamChannelConfig:
    channel: str
    display_name: str
    base_url: str
    api_key: str
    models_path: str
    is_enabled: bool
    source: str  # env | db


def normalize_models_path(path: str) -> str:
    normalized = path.strip()
    if not normalized:
        normalized = SETTINGS.upstream_models_path
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    return normalized


def parse_env_channels() -> dict[str, UpstreamChannelConfig]:
    raw = (SETTINGS.upstream_channels_json or "").strip()
    if not raw:
        return {}

    try:
        obj = json.loads(raw)
    except Exception as e:
        raise ValueError("invalid_upstream_channels_json") from e

    if not isinstance(obj, dict):
        raise ValueError("invalid_upstream_channels_json")

    default_base = str(SETTINGS.openai_base_url or "").strip()
    default_key = str(SETTINGS.openai_api_key or "").strip()
    default_models_path = normalize_models_path(SETTINGS.upstream_models_path)

    channels: dict[str, UpstreamChannelConfig] = {}
    for key, value in obj.items():
        name = str(key).strip()
        if not name or not isinstance(value, dict):
            raise ValueError("invalid_upstream_channels_json")

        base_url = str(value.get("base_url") or default_base).strip()
        api_key = str(value.get("api_key") or default_key).strip()
        display_name = str(value.get("display_name") or name).strip() or name
        models_path = normalize_models_path(str(value.get("models_path") or default_models_path))
        is_enabled = bool(value.get("is_enabled", True))

        channels[name] = UpstreamChannelConfig(
            channel=name,
            display_name=display_name,
            base_url=base_url,
            api_key=api_key,
            models_path=models_path,
            is_enabled=is_enabled,
            source="env",
        )
    return channels


def load_db_channels(db: Session | None) -> dict[str, UpstreamChannelConfig]:
    if db is None:
        return {}
    rows = db.scalars(select(UpstreamChannel).order_by(UpstreamChannel.channel.asc())).all()
    result: dict[str, UpstreamChannelConfig] = {}
    for row in rows:
        channel = (row.channel or "").strip()
        if not channel:
            continue
        result[channel] = UpstreamChannelConfig(
            channel=channel,
            display_name=(row.display_name or "").strip() or channel,
            base_url=(row.base_url or "").strip(),
            api_key=(row.api_key or "").strip(),
            models_path=normalize_models_path(str(row.models_path or "")),
            is_enabled=bool(row.is_enabled),
            source="db",
        )
    return result


def merged_named_channels(*, db: Session | None = None) -> dict[str, UpstreamChannelConfig]:
    merged = parse_env_channels()
    merged.update(load_db_channels(db))
    return merged


def list_upstream_channels(*, db: Session | None = None, include_disabled: bool = True) -> list[UpstreamChannelConfig]:
    merged = merged_named_channels(db=db)
    items = sorted(merged.values(), key=lambda x: x.channel)
    if include_disabled:
        return items
    return [x for x in items if x.is_enabled]


def resolve_upstream_target(channel: str | None = None, *, db: Session | None = None) -> UpstreamTarget:
    channel_name = str(channel or "").strip()
    if not channel_name:
        api_key = str(SETTINGS.openai_api_key or "").strip()
        if not api_key:
            raise ValueError("missing_upstream_api_key")
        base_url = str(SETTINGS.openai_base_url or "").strip()
        if not base_url:
            raise ValueError("missing_upstream_base_url")
        return UpstreamTarget(
            channel="",
            base_url=base_url,
            api_key=api_key,
            models_path=normalize_models_path(SETTINGS.upstream_models_path),
        )

    merged = merged_named_channels(db=db)
    if channel_name not in merged:
        raise ValueError(f"unknown_upstream_channel:{channel_name}")
    item = merged[channel_name]
    if not item.is_enabled:
        raise ValueError(f"disabled_upstream_channel:{channel_name}")
    if not item.api_key:
        raise ValueError(f"missing_upstream_api_key:{channel_name}")
    if not item.base_url:
        raise ValueError(f"missing_upstream_base_url:{channel_name}")

    return UpstreamTarget(
        channel=item.channel,
        base_url=item.base_url,
        api_key=item.api_key,
        models_path=item.models_path,
    )
