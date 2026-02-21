from __future__ import annotations

# JobManager utilities.
#
# Keep small helpers in a separate module so job_manager.py stays focused on
# orchestration (state transitions, thread lifecycle, and runner selection).

import json
import pathlib
import typing

from .. import db as db_module, models as models_module
from ..services import codex_config, upstream_channels
from ..settings import SETTINGS
from . import job_paths
from .job_manager_plans import GenerateBundle, ResourceLimits


def append_terminal(paths: job_paths.JobPaths, text: str) -> None:
    # Append to terminal log best-effort (UI streaming).
    try:
        paths.terminal_log.parent.mkdir(parents=True, exist_ok=True)
        with paths.terminal_log.open("ab") as file_handle:
            file_handle.write(text.encode("utf-8"))
    except OSError:
        return


def parse_openai_api_key(*, auth_json_bytes: bytes) -> str:
    # Extract OPENAI_API_KEY from Codex auth.json content.
    try:
        obj = json.loads(auth_json_bytes.decode("utf-8", errors="ignore"))
    except ValueError:
        return ""
    if not isinstance(obj, dict):
        return ""
    return str(obj.get("OPENAI_API_KEY") or "")


def prepare_generate_bundle_from_db(*, owner_user_id: str, state: dict[str, typing.Any]) -> GenerateBundle:
    # Build effective config + upstream auth for a generation attempt.
    target = None

    with db_module.SessionLocal() as db:
        row = db.get(models_module.UserCodexSettings, owner_user_id)
        overrides = row.overrides_toml if row else ""
        model = str(state.get("model") or "")
        model_pricing = db.get(models_module.ModelPricing, model) if model else None

        upstream_channel = str(state.get("upstream_channel") or "").strip()
        if not upstream_channel:
            upstream_channel = (model_pricing.upstream_channel if model_pricing else "") or ""

        if not SETTINGS.mock_mode:
            try:
                target = upstream_channels.resolve_upstream_target(upstream_channel, db=db)
            except ValueError as e:
                raise RuntimeError(f"upstream_config_error:{e}") from e

    cfg = codex_config.build_effective_config(user_overrides_toml=overrides)

    if SETTINGS.mock_mode:
        upstream_base_url = str(SETTINGS.openai_base_url or "")
        auth_bytes = b"{}\n"
        mock_mode = True
    else:
        if target is None:
            raise RuntimeError("upstream_config_error:missing_target")
        upstream_base_url = target.base_url
        secret = target.api_key
        auth_bytes = (json.dumps({"OPENAI_API_KEY": secret}, ensure_ascii=False) + "\n").encode("utf-8")
        mock_mode = False

    return GenerateBundle(
        effective_config_toml=cfg.effective_config_toml,
        auth_json_bytes=auth_bytes,
        openai_base_url=upstream_base_url,
        mock_mode=mock_mode,
    )


def read_resource_limits(*, state: dict[str, typing.Any]) -> ResourceLimits:
    # Read resource limits for runner execution.
    resource_limits = state.get("resource_limits") or {}
    cpus = float(resource_limits.get("cpus") or SETTINGS.default_cpus)
    memory_mb = int(resource_limits.get("memory_limit_mb") or SETTINGS.default_memory_mb)
    pids_limit = int(resource_limits.get("pids_limit") or SETTINGS.default_pids)
    max_terminal = int(resource_limits.get("max_terminal_log_bytes") or SETTINGS.default_max_terminal_log_bytes)
    return ResourceLimits(
        cpus=cpus,
        memory_mb=memory_mb,
        pids_limit=pids_limit,
        max_terminal_log_bytes=max_terminal,
    )


def scan_for_secret(*, paths: job_paths.JobPaths, secret: str) -> None:
    # Detect + redact accidental secret leakage in generated output.
    if not secret:
        return
    for file_path in (
        paths.output_dir / "main.cpp",
        paths.output_dir / "solution.json",
        paths.output_dir / "report.json",
    ):
        if not file_path.exists():
            continue
        data = file_path.read_text(encoding="utf-8", errors="ignore")
        if secret in data:
            file_path.write_text(data.replace(secret, "***"), encoding="utf-8")
            raise RuntimeError("secret_leak_detected")
