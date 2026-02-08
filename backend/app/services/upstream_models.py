from __future__ import annotations

import time
from typing import Any

import httpx
from sqlalchemy.orm import Session

from .upstream_channels import resolve_upstream_target


class UpstreamModelsError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


_models_cache: dict[str, dict[str, Any]] = {}
_CACHE_TTL_SECONDS = 60


def _build_models_url(*, base_url: str, models_path: str) -> str:
    base = base_url.rstrip("/")
    path = models_path
    if base.endswith("/v1") and path.startswith("/v1/"):
        path = path[len("/v1") :]
    return base + path


def _map_target_error(error: ValueError) -> UpstreamModelsError:
    msg = str(error)
    if msg.startswith("unknown_upstream_channel:"):
        return UpstreamModelsError("unknown_upstream_channel", msg.removeprefix("unknown_upstream_channel:"))
    if msg.startswith("disabled_upstream_channel:"):
        return UpstreamModelsError("disabled_upstream_channel", msg.removeprefix("disabled_upstream_channel:"))
    if msg.startswith("missing_upstream_api_key"):
        return UpstreamModelsError("missing_upstream_api_key", msg)
    if msg.startswith("missing_upstream_base_url"):
        return UpstreamModelsError("missing_upstream_base_url", msg)
    return UpstreamModelsError("invalid_upstream_target", msg)


def fetch_upstream_models_payload(
    *,
    channel: str | None,
    db: Session | None = None,
    force_refresh: bool = False,
) -> dict[str, Any]:
    try:
        target = resolve_upstream_target(channel, db=db)
    except ValueError as e:
        raise _map_target_error(e) from e

    cache_key = target.channel or "__default__"
    now = time.time()
    cached = _models_cache.get(cache_key)
    if not force_refresh and cached and now - float(cached.get("ts") or 0.0) < _CACHE_TTL_SECONDS:
        payload = cached.get("data")
        if isinstance(payload, dict):
            return payload

    url = _build_models_url(base_url=target.base_url, models_path=target.models_path)
    try:
        resp = httpx.get(
            url,
            headers={"Authorization": f"Bearer {target.api_key}"},
            timeout=20,
            trust_env=False,
        )
    except Exception as e:
        raise UpstreamModelsError("upstream_unavailable", f"{type(e).__name__}: {e}") from e

    if resp.status_code in (401, 403):
        raise UpstreamModelsError("upstream_unauthorized", "Upstream unauthorized")
    if resp.status_code >= 500:
        raise UpstreamModelsError("upstream_unavailable", f"Upstream HTTP {resp.status_code}")
    if resp.status_code >= 400:
        raise UpstreamModelsError("upstream_bad_response", f"Upstream HTTP {resp.status_code}")

    try:
        data = resp.json()
    except Exception as e:
        raise UpstreamModelsError("upstream_bad_response", f"Invalid JSON: {e}") from e

    if not isinstance(data, dict):
        raise UpstreamModelsError("upstream_bad_response", "Invalid payload shape")

    _models_cache[cache_key] = {"ts": now, "data": data}
    return data


def list_upstream_model_ids(
    *,
    channel: str | None,
    db: Session | None = None,
    force_refresh: bool = False,
) -> set[str]:
    payload = fetch_upstream_models_payload(channel=channel, db=db, force_refresh=force_refresh)
    rows = payload.get("data")
    if not isinstance(rows, list):
        return set()

    result: set[str] = set()
    for item in rows:
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("id") or "").strip()
        if model_id:
            result.add(model_id)
    return result

