from __future__ import annotations

# Admin upstream router (channels/models).

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import select

from ..deps import AdminUserDep, DbDep
from ..models import ModelPricing, UpstreamChannel
from ..services.upstream_channels import list_upstream_channels
from ..services.upstream_models import UpstreamModelsError, fetch_upstream_models_payload
from ..settings import SETTINGS
from ..utils.errors import http_error
from .admin_common import commit_db


router = APIRouter()
route_get = router.get
route_put = router.put
route_delete = router.delete


class UpstreamChannelItem(BaseModel):
    channel: str
    display_name: str
    base_url: str
    api_key_masked: str
    has_api_key: bool
    models_path: str
    is_default: bool
    is_enabled: bool
    source: str


def mask_api_key(value: str) -> str:
    s = value.strip()
    if not s:
        return ""
    if len(s) <= 8:
        return "*" * len(s)
    return f"{s[:4]}...{s[-4:]}"


@route_get("/upstream/channels", response_model=list[UpstreamChannelItem])
def upstream_channels(_: AdminUserDep, db: DbDep):
    items: list[UpstreamChannelItem] = []
    try:
        channels = list_upstream_channels(db=db, include_disabled=True)
    except ValueError as exc:
        http_error(500, "server_misconfigured", str(exc))
    for channel in channels:
        items.append(
            UpstreamChannelItem(
                channel=channel.channel,
                display_name=channel.display_name,
                base_url=channel.base_url,
                api_key_masked=mask_api_key(channel.api_key),
                has_api_key=bool(channel.api_key.strip()),
                models_path=channel.models_path,
                is_default=False,
                is_enabled=channel.is_enabled,
                source=channel.source,
            )
        )
    return items


class UpsertUpstreamChannelRequest(BaseModel):
    display_name: str | None = None
    base_url: str
    api_key: str | None = None
    models_path: str = "/v1/models"
    is_enabled: bool = True


def normalize_models_path(path: str) -> str:
    p = path.strip()
    if not p:
        p = SETTINGS.upstream_models_path
    if not p.startswith("/"):
        p = f"/{p}"
    return p


@route_put("/upstream/channels/{channel}")
def upsert_upstream_channel(_: AdminUserDep, db: DbDep, channel: str, req: UpsertUpstreamChannelRequest):
    channel_key = channel.strip()
    if not channel_key:
        http_error(422, "invalid_request", "Invalid channel")
    if channel_key.lower() == "default":
        http_error(422, "invalid_request", "Channel name 'default' is reserved")

    base_url = req.base_url.strip()
    if not base_url:
        http_error(422, "invalid_request", "Missing base_url")

    db_get = db.get
    row = db_get(UpstreamChannel, channel_key)
    api_key_value = req.api_key.strip() if req.api_key is not None else None
    if row is None and (api_key_value is None or not api_key_value):
        http_error(422, "invalid_request", "Missing api_key")

    if row is None:
        row = UpstreamChannel(channel=channel_key)

    row.display_name = (req.display_name or "").strip() or channel_key
    row.base_url = base_url
    if api_key_value:
        row.api_key = api_key_value
    elif not row.api_key:
        http_error(422, "invalid_request", "Missing api_key")
    row.models_path = normalize_models_path(req.models_path)
    row.is_enabled = bool(req.is_enabled)

    db.add(row)
    commit_db(db)
    return {"ok": True}


@route_delete("/upstream/channels/{channel}")
def delete_upstream_channel(_: AdminUserDep, db: DbDep, channel: str):
    channel_key = channel.strip()
    if not channel_key:
        http_error(422, "invalid_request", "Invalid channel")
    if channel_key.lower() == "default":
        http_error(422, "invalid_request", "Channel name 'default' is reserved")

    db_get = db.get
    row = db_get(UpstreamChannel, channel_key)
    if row is None:
        http_error(404, "not_found", "Upstream channel not found")

    bound_models = db.scalars(select(ModelPricing).where(ModelPricing.upstream_channel == channel_key)).all()
    used_count = len(bound_models)
    if used_count > 0:
        for model_pricing in bound_models:
            model_pricing.upstream_channel = ""

    db_delete = db.delete
    db_delete(row)
    commit_db(db)
    return {"ok": True, "detached_models": used_count}


@route_get("/upstream/models")
def upstream_models(_: AdminUserDep, db: DbDep, channel: str | None = Query(default=None, max_length=64)):
    try:
        return fetch_upstream_models_payload(channel=channel, db=db)
    except UpstreamModelsError as exc:
        if exc.code == "unknown_upstream_channel":
            http_error(422, "invalid_request", f"Unknown upstream channel: {exc.message}")
        if exc.code == "disabled_upstream_channel":
            http_error(422, "invalid_request", f"Disabled upstream channel: {exc.message}")
        if exc.code == "missing_upstream_api_key":
            http_error(401, "upstream_unauthorized", "Missing upstream API key")
        if exc.code == "upstream_unauthorized":
            http_error(401, "upstream_unauthorized", "Upstream unauthorized")
        if exc.code == "upstream_bad_response":
            http_error(502, "upstream_bad_response", exc.message)
        if exc.code == "upstream_unavailable":
            http_error(503, "upstream_unavailable", f"Upstream unavailable: {exc.message}")
        http_error(500, "server_misconfigured", exc.message)
