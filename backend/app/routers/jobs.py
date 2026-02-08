from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select

from ..deps import CurrentUserDep, DbDep
from ..models import ModelPricing, UsageRecord
from ..services.job_manager import JobManager
from ..services.job_paths import get_job_paths
from ..services.job_state import iso_after_days, now_iso, save_state
from ..services.pricing import microusd_to_amount_str
from ..services.sse import tail_file_sse, tail_jsonl_sse
from ..services.upstream_models import UpstreamModelsError, list_upstream_model_ids
from ..services.upstream_channels import resolve_upstream_target
from ..services.zip_safe import InvalidZip, ZipLimits, extract_zip_safe
from ..settings import SETTINGS
from ..utils.errors import http_error
from ..utils.fs import read_json, write_json


router = APIRouter(prefix="/jobs", tags=["jobs"])


def get_job_manager() -> JobManager:
    from ..services.singletons import JOB_MANAGER  # noqa: WPS433

    if JOB_MANAGER is None:
        raise RuntimeError("job_manager_not_ready")
    return JOB_MANAGER


class CreateJobResponse(BaseModel):
    job_id: str
    status: str
    created_at: str


@router.post("", response_model=CreateJobResponse)
def create_job(
    user: CurrentUserDep,
    db: DbDep,
    model: str = Form(...),
    upstream_channel: str | None = Form(None),
    statement_md: str = Form(...),
    current_code_cpp: str = Form(""),
    tests_zip: UploadFile | None = File(None),
    tests_format: Literal["auto", "in_out_pairs", "manifest"] = Form("auto"),
    compare_mode: Literal["tokens", "trim_ws", "exact"] = Form("tokens"),
    run_if_no_expected: bool = Form(True),
    search_mode: Literal["disabled", "cached", "live"] = Form(SETTINGS.default_search_mode),
    reasoning_effort: Literal["low", "medium", "high", "xhigh"] = Form("medium"),
    time_limit_ms: int | None = Form(None),
    memory_limit_mb: int | None = Form(None),
):
    pricing: ModelPricing | None = db.get(ModelPricing, model)
    has_valid_pricing = bool(
        pricing
        and pricing.is_active
        and None
        not in (
            pricing.input_microusd_per_1m_tokens,
            pricing.cached_input_microusd_per_1m_tokens,
            pricing.output_microusd_per_1m_tokens,
            pricing.cached_output_microusd_per_1m_tokens,
        )
    )
    resolved_upstream_channel = str(upstream_channel or "").strip()
    if not resolved_upstream_channel and pricing:
        resolved_upstream_channel = str(pricing.upstream_channel or "").strip()

    if not has_valid_pricing:
        if not resolved_upstream_channel:
            http_error(422, "invalid_model", "Model not available")
        try:
            resolve_upstream_target(resolved_upstream_channel, db=db)
        except ValueError:
            http_error(422, "invalid_model", "Model channel unavailable")

    if resolved_upstream_channel:
        try:
            upstream_model_ids = list_upstream_model_ids(channel=resolved_upstream_channel, db=db)
        except UpstreamModelsError as e:
            if e.code in ("unknown_upstream_channel", "disabled_upstream_channel"):
                http_error(422, "invalid_model", "Model channel unavailable")
            if e.code in ("missing_upstream_api_key", "upstream_unauthorized"):
                http_error(401, "upstream_unauthorized", "Upstream unauthorized")
            if e.code == "upstream_bad_response":
                http_error(502, "upstream_bad_response", "Upstream model list invalid")
            if e.code == "upstream_unavailable":
                http_error(503, "upstream_unavailable", "Upstream unavailable")
            http_error(500, "server_misconfigured", e.message)
        if model not in upstream_model_ids:
            http_error(422, "invalid_model", "Model not enabled on upstream channel")

    # Clamp limits.
    time_limit_ms = int(time_limit_ms or SETTINGS.default_time_limit_ms)
    time_limit_ms = max(1, min(time_limit_ms, SETTINGS.max_time_limit_ms))
    memory_limit_mb = int(memory_limit_mb or SETTINGS.default_memory_mb)
    memory_limit_mb = max(64, min(memory_limit_mb, SETTINGS.max_memory_mb))

    job_id = uuid.uuid4().hex
    jobs_root = Path(SETTINGS.jobs_root)
    paths = get_job_paths(jobs_root=jobs_root, job_id=job_id)

    paths.input_dir.mkdir(parents=True, exist_ok=True)
    paths.output_dir.mkdir(parents=True, exist_ok=True)
    paths.logs_dir.mkdir(parents=True, exist_ok=True)

    tests_present = False
    if tests_zip is not None:
        tmp_zip = paths.root / "_tmp_tests.zip"
        tmp_zip.write_bytes(tests_zip.file.read())
        try:
            extract_zip_safe(
                tmp_zip,
                paths.tests_dir,
                ZipLimits(
                    max_files=SETTINGS.tests_max_files,
                    max_uncompressed_bytes=SETTINGS.tests_max_uncompressed_bytes,
                    max_single_file_bytes=SETTINGS.tests_max_single_file_bytes,
                    max_depth=SETTINGS.tests_max_depth,
                ),
            )
            tests_present = True
        except InvalidZip as e:
            http_error(422, "invalid_tests_zip", str(e))
        finally:
            if tmp_zip.exists():
                tmp_zip.unlink(missing_ok=True)

    job_obj: dict[str, Any] = {
        "schema_version": "job.v1",
        "job_id": job_id,
        "owner_user_id": user.id,
        "language": "cpp",
        "model": model,
        "upstream_channel": resolved_upstream_channel,
        "problem": {"statement_md": statement_md},
        "seed": {"current_code_cpp": current_code_cpp or ""},
        "search_mode": search_mode,
        "reasoning_effort": reasoning_effort,
        "limits": {
            "time_limit_ms": time_limit_ms,
            "memory_limit_mb": memory_limit_mb,
            "cpus": SETTINGS.default_cpus,
            "pids_limit": SETTINGS.default_pids,
            "max_output_bytes_per_test": SETTINGS.default_max_output_bytes_per_test,
            "max_terminal_log_bytes": SETTINGS.default_max_terminal_log_bytes,
        },
        "compile": {"cpp_std": "c++20"},
        "tests": {
            "dir": "tests",
            "present": tests_present,
            "format": tests_format,
            "compare": {"mode": compare_mode},
            "run_if_no_expected": bool(run_if_no_expected),
        },
    }
    write_json(paths.job_json, job_obj)

    state_obj: dict[str, Any] = {
        "schema_version": "state.v1",
        "job_id": job_id,
        "owner_user_id": user.id,
        "status": "created",
        "created_at": now_iso(),
        "started_at": None,
        "finished_at": None,
        "expires_at": None,
        "model": model,
        "upstream_channel": resolved_upstream_channel,
        "search_mode": search_mode,
        "reasoning_effort": reasoning_effort,
        "limits": {"time_limit_ms": time_limit_ms, "memory_limit_mb": memory_limit_mb},
        "resource_limits": {
            "cpus": SETTINGS.default_cpus,
            "memory_limit_mb": memory_limit_mb,
            "pids_limit": SETTINGS.default_pids,
            "max_output_bytes_per_test": SETTINGS.default_max_output_bytes_per_test,
            "max_terminal_log_bytes": SETTINGS.default_max_terminal_log_bytes,
        },
        "containers": {"generate": None, "test": None},
        "artifacts": {"main_cpp": False, "solution_json": False, "report_json": False},
        "error": None,
    }
    save_state(paths.state_json, state_obj)

    return CreateJobResponse(job_id=job_id, status="created", created_at=state_obj["created_at"])


class JobListItem(BaseModel):
    job_id: str
    owner_user_id: str
    status: str
    created_at: str
    finished_at: str | None = None
    expires_at: str | None = None


class JobListResponse(BaseModel):
    items: list[JobListItem]
    total: int


@router.get("", response_model=JobListResponse)
def list_jobs(user: CurrentUserDep, owner_user_id: str | None = None):
    jobs_root = Path(SETTINGS.jobs_root)
    items: list[JobListItem] = []
    for p in jobs_root.iterdir():
        if not p.is_dir():
            continue
        state_path = p / "state.json"
        if not state_path.exists():
            continue
        try:
            st = read_json(state_path)
        except Exception:
            continue

        st_owner = str(st.get("owner_user_id") or "")
        if user.role != "admin" and st_owner != user.id:
            continue
        if owner_user_id and st_owner != owner_user_id:
            continue

        items.append(
            JobListItem(
                job_id=str(st.get("job_id") or p.name),
                owner_user_id=st_owner,
                status=str(st.get("status") or ""),
                created_at=str(st.get("created_at") or ""),
                finished_at=st.get("finished_at"),
                expires_at=st.get("expires_at"),
            )
        )
    items.sort(key=lambda x: x.created_at, reverse=True)
    return JobListResponse(items=items, total=len(items))


@router.get("/{job_id}")
def get_job(user: CurrentUserDep, job_id: str):
    paths = get_job_paths(jobs_root=Path(SETTINGS.jobs_root), job_id=job_id)
    if not paths.state_json.exists():
        http_error(404, "not_found", "Job not found")
    st = read_json(paths.state_json)
    if user.role != "admin" and st.get("owner_user_id") != user.id:
        http_error(404, "not_found", "Job not found")
    return st


@router.post("/{job_id}/start")
def start_job(user: CurrentUserDep, job_id: str, jm: JobManager = Depends(get_job_manager)):
    paths = get_job_paths(jobs_root=Path(SETTINGS.jobs_root), job_id=job_id)
    if not paths.state_json.exists():
        http_error(404, "not_found", "Job not found")
    st = read_json(paths.state_json)
    if user.role != "admin" and st.get("owner_user_id") != user.id:
        http_error(404, "not_found", "Job not found")
    try:
        new_state = jm.start_job(job_id=job_id, owner_user_id=str(st.get("owner_user_id") or ""))
    except RuntimeError as e:
        if str(e) == "already_finished":
            http_error(409, "already_finished", "Job already finished")
        raise
    return {"job_id": job_id, "status": new_state.get("status")}


@router.post("/{job_id}/cancel")
def cancel_job(user: CurrentUserDep, job_id: str, jm: JobManager = Depends(get_job_manager)):
    paths = get_job_paths(jobs_root=Path(SETTINGS.jobs_root), job_id=job_id)
    if not paths.state_json.exists():
        http_error(404, "not_found", "Job not found")
    st = read_json(paths.state_json)
    if user.role != "admin" and st.get("owner_user_id") != user.id:
        http_error(404, "not_found", "Job not found")
    new_state = jm.cancel_job(job_id=job_id)
    return {"job_id": job_id, "status": new_state.get("status")}


@router.get("/{job_id}/artifacts/{name}")
def get_artifact(user: CurrentUserDep, job_id: str, name: str):
    if name not in ("main.cpp", "solution.json", "report.json"):
        http_error(404, "not_found", "Artifact not found")
    paths = get_job_paths(jobs_root=Path(SETTINGS.jobs_root), job_id=job_id)
    if not paths.state_json.exists():
        http_error(404, "not_found", "Job not found")
    st = read_json(paths.state_json)
    if user.role != "admin" and st.get("owner_user_id") != user.id:
        http_error(404, "not_found", "Job not found")
    file_path = paths.output_dir / name
    if not file_path.exists():
        http_error(404, "not_found", "Artifact not found")
    media = "application/json" if name.endswith(".json") else "text/plain"
    return FileResponse(file_path, media_type=media, filename=name)


@router.get("/{job_id}/terminal.sse")
def terminal_sse(user: CurrentUserDep, job_id: str, offset: int = 0):
    paths = get_job_paths(jobs_root=Path(SETTINGS.jobs_root), job_id=job_id)
    if not paths.state_json.exists():
        http_error(404, "not_found", "Job not found")
    st = read_json(paths.state_json)
    if user.role != "admin" and st.get("owner_user_id") != user.id:
        http_error(404, "not_found", "Job not found")
    generator = tail_file_sse(path=paths.terminal_log, offset=max(0, offset), event="terminal")
    return StreamingResponse(generator, media_type="text/event-stream")


@router.get("/{job_id}/agent_status.sse")
def agent_status_sse(user: CurrentUserDep, job_id: str, offset: int = 0):
    paths = get_job_paths(jobs_root=Path(SETTINGS.jobs_root), job_id=job_id)
    if not paths.state_json.exists():
        http_error(404, "not_found", "Job not found")
    st = read_json(paths.state_json)
    if user.role != "admin" and st.get("owner_user_id") != user.id:
        http_error(404, "not_found", "Job not found")
    generator = tail_jsonl_sse(path=paths.agent_status_jsonl, offset=max(0, offset), event="agent_status")
    return StreamingResponse(generator, media_type="text/event-stream")


@router.get("/{job_id}/usage")
def job_usage(user: CurrentUserDep, db: DbDep, job_id: str):
    paths = get_job_paths(jobs_root=Path(SETTINGS.jobs_root), job_id=job_id)
    if not paths.state_json.exists():
        http_error(404, "not_found", "Job not found")
    st = read_json(paths.state_json)
    if user.role != "admin" and st.get("owner_user_id") != user.id:
        http_error(404, "not_found", "Job not found")

    rows = db.scalars(select(UsageRecord).where(UsageRecord.job_id == job_id)).all()
    usage = {
        "input_tokens": sum(r.input_tokens for r in rows),
        "cached_input_tokens": sum(r.cached_input_tokens for r in rows),
        "output_tokens": sum(r.output_tokens for r in rows),
        "cached_output_tokens": sum(r.cached_output_tokens for r in rows),
    }
    cost_microusd = sum(r.cost_microusd or 0 for r in rows) if any(r.cost_microusd is not None for r in rows) else None
    cost = None
    if cost_microusd is not None:
        cost = {"currency": "USD", "cost_microusd": cost_microusd, "amount": microusd_to_amount_str(cost_microusd)}
    return {"job_id": job_id, "owner_user_id": st.get("owner_user_id"), "model": st.get("model"), "usage": usage, "cost": cost, "records": [r.id for r in rows]}
