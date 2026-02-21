from __future__ import annotations

# Jobs API router.
#
# 说明：
# - /jobs POST: 创建一个新的 job（上传 tests.zip 可选）
# - /jobs/{id}/start: 启动（embedded judge 或排队给 independent judge）
# - /jobs/{id}/cancel: 取消
# - /jobs/{id}/artifacts/{name}: 下载 artifacts
# - /jobs/{id}/usage: 聚合 usage_records（仅用于页面展示）
#
# 这个文件偏“胶水层”：主要做输入解析 + 访问控制 + 文件 IO + 调用 JobManager。

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..deps import CurrentUserDep, DbDep
from ..services.job_manager import JobManager
from ..services.job_paths import get_job_paths
from ..services.job_state import now_iso, save_state
from ..settings import SETTINGS
from ..utils.errors import http_error
from ..utils.fs import read_json, write_json


router = APIRouter(prefix="/jobs", tags=["jobs"])
route_get = router.get
route_post = router.post


def get_job_manager() -> JobManager:
    from ..services.singletons import JOB_MANAGER  # noqa: WPS433

    if JOB_MANAGER is None:
        raise RuntimeError("job_manager_not_ready")
    return JOB_MANAGER


def list_upstream_model_ids(*, channel: str, db: DbDep | None = None) -> set[str]:
    """List enabled upstream model ids (test-patchable wrapper)."""

    from ..services.upstream_models import list_upstream_model_ids as list_upstream_model_ids_impl  # noqa: WPS433

    return set(list_upstream_model_ids_impl(channel=channel, db=db))


class CreateJobResponse(BaseModel):
    job_id: str
    status: str
    created_at: str


# -----------------------------
# Create job: 表单模型（Form fields）
# -----------------------------
class CreateJobForm(BaseModel):
    model: str
    upstream_channel: str | None = None
    statement_md: str
    current_code_cpp: str = ""
    tests_format: Literal["auto", "in_out_pairs", "manifest"] = "auto"
    compare_mode: Literal["tokens", "trim_ws", "exact"] = "tokens"
    run_if_no_expected: bool = True
    search_mode: Literal["disabled", "cached", "live"] = SETTINGS.default_search_mode
    reasoning_effort: Literal["low", "medium", "high", "xhigh"] = "medium"
    time_limit_ms: int | None = None
    memory_limit_mb: int | None = None


class CreateJobCoreForm(BaseModel):
    model: str
    upstream_channel: str | None = None
    statement_md: str
    current_code_cpp: str = ""


class CreateJobFlagsForm(BaseModel):
    tests_format: Literal["auto", "in_out_pairs", "manifest"] = "auto"
    compare_mode: Literal["tokens", "trim_ws", "exact"] = "tokens"
    run_if_no_expected: bool = True
    search_mode: Literal["disabled", "cached", "live"] = SETTINGS.default_search_mode
    reasoning_effort: Literal["low", "medium", "high", "xhigh"] = "medium"


class CreateJobLimitsForm(BaseModel):
    time_limit_ms: int | None = None
    memory_limit_mb: int | None = None


def parse_create_job_core_form(
    model: str = Form(...),
    upstream_channel: str | None = Form(None),
    statement_md: str = Form(...),
    current_code_cpp: str = Form(""),
) -> CreateJobCoreForm:
    return CreateJobCoreForm(
        model=model,
        upstream_channel=upstream_channel,
        statement_md=statement_md,
        current_code_cpp=current_code_cpp,
    )


def parse_create_job_flags_form(
    tests_format: Literal["auto", "in_out_pairs", "manifest"] = Form("auto"),
    compare_mode: Literal["tokens", "trim_ws", "exact"] = Form("tokens"),
    run_if_no_expected: bool = Form(True),
    search_mode: Literal["disabled", "cached", "live"] = Form(SETTINGS.default_search_mode),
    reasoning_effort: Literal["low", "medium", "high", "xhigh"] = Form("medium"),
) -> CreateJobFlagsForm:
    return CreateJobFlagsForm(
        tests_format=tests_format,
        compare_mode=compare_mode,
        run_if_no_expected=run_if_no_expected,
        search_mode=search_mode,
        reasoning_effort=reasoning_effort,
    )


def parse_create_job_limits_form(
    time_limit_ms: int | None = Form(None),
    memory_limit_mb: int | None = Form(None),
) -> CreateJobLimitsForm:
    return CreateJobLimitsForm(time_limit_ms=time_limit_ms, memory_limit_mb=memory_limit_mb)


def parse_create_job_form(
    core: CreateJobCoreForm = Depends(parse_create_job_core_form),
    flags: CreateJobFlagsForm = Depends(parse_create_job_flags_form),
    limits: CreateJobLimitsForm = Depends(parse_create_job_limits_form),
) -> CreateJobForm:
    return CreateJobForm(
        model=core.model,
        upstream_channel=core.upstream_channel,
        statement_md=core.statement_md,
        current_code_cpp=core.current_code_cpp,
        tests_format=flags.tests_format,
        compare_mode=flags.compare_mode,
        run_if_no_expected=flags.run_if_no_expected,
        search_mode=flags.search_mode,
        reasoning_effort=flags.reasoning_effort,
        time_limit_ms=limits.time_limit_ms,
        memory_limit_mb=limits.memory_limit_mb,
    )

# -----------------------------
# 模型/上游通道校验（把复杂逻辑拆成小函数）
# -----------------------------

def pricing_is_valid(pricing: ModelPricing | None) -> bool:
    if pricing is None:
        return False
    if not pricing.is_active:
        return False
    return None not in (
        pricing.input_microusd_per_1m_tokens,
        pricing.cached_input_microusd_per_1m_tokens,
        pricing.output_microusd_per_1m_tokens,
        pricing.cached_output_microusd_per_1m_tokens,
    )


def resolve_upstream_channel(*, upstream_channel: str | None, pricing: ModelPricing | None) -> str:
    resolved = str(upstream_channel or "").strip()
    if not resolved and pricing is not None:
        resolved = str(pricing.upstream_channel or "").strip()
    return resolved


def validate_upstream_channel_available(*, db: DbDep, resolved_upstream_channel: str) -> None:
    from ..services.upstream_channels import resolve_upstream_target  # noqa: WPS433

    try:
        resolve_upstream_target(resolved_upstream_channel, db=db)
    except ValueError:
        http_error(422, "invalid_model", "Model channel unavailable")


def validate_model_enabled_on_channel(*, db: DbDep, resolved_upstream_channel: str, model: str) -> None:
    from ..services.upstream_models import UpstreamModelsError  # noqa: WPS433

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


def resolve_and_validate_model_channel(*, db: DbDep, model: str, upstream_channel: str | None) -> str:
    from ..models import ModelPricing  # noqa: WPS433

    pricing: ModelPricing | None = db.get(ModelPricing, model)
    has_valid_pricing = pricing_is_valid(pricing)
    resolved_upstream_channel = resolve_upstream_channel(upstream_channel=upstream_channel, pricing=pricing)

    if not has_valid_pricing:
        if not resolved_upstream_channel:
            http_error(422, "invalid_model", "Model not available")
        validate_upstream_channel_available(db=db, resolved_upstream_channel=resolved_upstream_channel)

    if resolved_upstream_channel:
        validate_model_enabled_on_channel(db=db, resolved_upstream_channel=resolved_upstream_channel, model=model)

    return resolved_upstream_channel


def clamp_limits(*, time_limit_ms: int | None, memory_limit_mb: int | None) -> tuple[int, int]:
    clamped_time_limit_ms = int(time_limit_ms or SETTINGS.default_time_limit_ms)
    clamped_time_limit_ms = max(1, min(clamped_time_limit_ms, SETTINGS.max_time_limit_ms))
    clamped_memory_limit_mb = int(memory_limit_mb or SETTINGS.default_memory_mb)
    clamped_memory_limit_mb = max(64, min(clamped_memory_limit_mb, SETTINGS.max_memory_mb))
    return clamped_time_limit_ms, clamped_memory_limit_mb


def extract_tests_zip_if_present(*, paths: Any, tests_zip: UploadFile | None) -> bool:
    from ..services.zip_safe import InvalidZip, ZipLimits, extract_zip_safe  # noqa: WPS433

    # 按需接收上传的 tests.zip 并做 zip-slip 防护解压。
    if tests_zip is None:
        return False

    tmp_zip = paths.root / "_tmp_tests.zip"
    try:
        uploaded = tests_zip.file.read()
        written = tmp_zip.write_bytes(uploaded)
        if written != len(uploaded):
            http_error(400, "invalid_tests_zip", "Cannot persist uploaded zip")
    except Exception:
        http_error(400, "invalid_tests_zip", "Cannot read uploaded zip")
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
        return True
    except InvalidZip as e:
        http_error(422, "invalid_tests_zip", str(e))
    finally:
        if tmp_zip.exists():
            tmp_zip.unlink(missing_ok=True)
    return False


def load_job_state_for_user(*, user: CurrentUserDep, job_id: str) -> tuple[Any, dict[str, Any]]:
    # 统一做 jobs/{id} 的访问控制：非 owner 的 job 对普通用户表现为 404。
    paths = get_job_paths(jobs_root=Path(SETTINGS.jobs_root), job_id=job_id)
    if not paths.state_json.exists():
        http_error(404, "not_found", "Job not found")
    st = read_json(paths.state_json)
    if user.role != "admin" and st.get("owner_user_id") != user.id:
        http_error(404, "not_found", "Job not found")
    return paths, st


@dataclass(frozen=True)
class CreateJobContext:
    job_id: str
    owner_user_id: str
    model: str
    upstream_channel: str
    statement_md: str
    current_code_cpp: str
    tests_present: bool
    tests_format: str
    compare_mode: str
    run_if_no_expected: bool
    search_mode: str
    reasoning_effort: str
    time_limit_ms: int | None
    memory_limit_mb: int | None


def build_job_obj(
    ctx: CreateJobContext,
) -> dict[str, Any]:
    return {
        "schema_version": "job.v1",
        "job_id": ctx.job_id,
        "owner_user_id": ctx.owner_user_id,
        "language": "cpp",
        "model": ctx.model,
        "upstream_channel": ctx.upstream_channel,
        "problem": {"statement_md": ctx.statement_md},
        "seed": {"current_code_cpp": ctx.current_code_cpp or ""},
        "search_mode": ctx.search_mode,
        "reasoning_effort": ctx.reasoning_effort,
        "limits": {
            "time_limit_ms": ctx.time_limit_ms,
            "memory_limit_mb": ctx.memory_limit_mb,
            "cpus": SETTINGS.default_cpus,
            "pids_limit": SETTINGS.default_pids,
            "max_output_bytes_per_test": SETTINGS.default_max_output_bytes_per_test,
            "max_terminal_log_bytes": SETTINGS.default_max_terminal_log_bytes,
        },
        "compile": {"cpp_std": "c++20"},
        "tests": {
            "dir": "tests",
            "present": ctx.tests_present,
            "format": ctx.tests_format,
            "compare": {"mode": ctx.compare_mode},
            "run_if_no_expected": bool(ctx.run_if_no_expected),
        },
    }


def build_state_obj(
    ctx: CreateJobContext,
) -> dict[str, Any]:
    return {
        "schema_version": "state.v1",
        "job_id": ctx.job_id,
        "owner_user_id": ctx.owner_user_id,
        "status": "created",
        "created_at": now_iso(),
        "started_at": None,
        "finished_at": None,
        "expires_at": None,
        "model": ctx.model,
        "upstream_channel": ctx.upstream_channel,
        "search_mode": ctx.search_mode,
        "reasoning_effort": ctx.reasoning_effort,
        "limits": {"time_limit_ms": ctx.time_limit_ms, "memory_limit_mb": ctx.memory_limit_mb},
        "resource_limits": {
            "cpus": SETTINGS.default_cpus,
            "memory_limit_mb": ctx.memory_limit_mb,
            "pids_limit": SETTINGS.default_pids,
            "max_output_bytes_per_test": SETTINGS.default_max_output_bytes_per_test,
            "max_terminal_log_bytes": SETTINGS.default_max_terminal_log_bytes,
        },
        "containers": {"generate": None, "test": None},
        "artifacts": {"main_cpp": False, "solution_json": False, "report_json": False},
        "error": None,
    }


@route_post("", response_model=CreateJobResponse)
def create_job(
    user: CurrentUserDep,
    db: DbDep,
    form: CreateJobForm = Depends(parse_create_job_form),
    tests_zip: UploadFile | None = File(None),
):
    # 创建 job（落盘 job.json/state.json + 可选解压 tests.zip）。
    model = form.model
    statement_md = form.statement_md
    current_code_cpp = form.current_code_cpp
    tests_format = form.tests_format
    compare_mode = form.compare_mode
    run_if_no_expected = form.run_if_no_expected
    search_mode = form.search_mode
    reasoning_effort = form.reasoning_effort

    resolved_upstream_channel = resolve_and_validate_model_channel(db=db, model=model, upstream_channel=form.upstream_channel)
    time_limit_ms, memory_limit_mb = clamp_limits(time_limit_ms=form.time_limit_ms, memory_limit_mb=form.memory_limit_mb)

    job_id = uuid.uuid4().hex
    jobs_root = Path(SETTINGS.jobs_root)
    paths = get_job_paths(jobs_root=jobs_root, job_id=job_id)

    paths.input_dir.mkdir(parents=True, exist_ok=True)
    paths.output_dir.mkdir(parents=True, exist_ok=True)
    paths.logs_dir.mkdir(parents=True, exist_ok=True)

    tests_present = extract_tests_zip_if_present(paths=paths, tests_zip=tests_zip)

    ctx = CreateJobContext(
        job_id=job_id,
        owner_user_id=user.id,
        model=model,
        upstream_channel=resolved_upstream_channel,
        statement_md=statement_md,
        current_code_cpp=current_code_cpp,
        tests_present=tests_present,
        tests_format=tests_format,
        compare_mode=compare_mode,
        run_if_no_expected=run_if_no_expected,
        search_mode=search_mode,
        reasoning_effort=reasoning_effort,
        time_limit_ms=time_limit_ms,
        memory_limit_mb=memory_limit_mb,
    )
    job_obj = build_job_obj(ctx)
    write_json(paths.job_json, job_obj)

    state_obj = build_state_obj(ctx)
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


def iter_job_state_files(*, jobs_root: Path):
    """Yield `(job_dir, state.json)` pairs from `jobs_root` best-effort."""
    for p in jobs_root.iterdir():
        if not p.is_dir():
            continue
        state_path = p / "state.json"
        if not state_path.exists():
            continue
        yield p, state_path


def read_job_state_best_effort(*, state_path: Path) -> dict[str, Any] | None:
    try:
        st = read_json(state_path)
    except Exception:
        return None
    return st if isinstance(st, dict) else None


def should_include_job_for_user(*, user: CurrentUserDep, st_owner: str, owner_user_id: str | None) -> bool:
    if user.role != "admin" and st_owner != user.id:
        return False
    if owner_user_id and st_owner != owner_user_id:
        return False
    return True


def build_job_list_item(*, job_dir: Path, st: dict[str, Any], st_owner: str) -> JobListItem:
    return JobListItem(
        job_id=str(st.get("job_id") or job_dir.name),
        owner_user_id=st_owner,
        status=str(st.get("status") or ""),
        created_at=str(st.get("created_at") or ""),
        finished_at=st.get("finished_at"),
        expires_at=st.get("expires_at"),
    )


@route_get("", response_model=JobListResponse)
def list_jobs(user: CurrentUserDep, owner_user_id: str | None = None):
    # list_jobs 是轻量实现：直接遍历 jobs_root 下的 state.json。
    jobs_root = Path(SETTINGS.jobs_root)
    items: list[JobListItem] = []
    for job_dir, state_path in iter_job_state_files(jobs_root=jobs_root):
        st = read_job_state_best_effort(state_path=state_path)
        if st is None:
            continue
        st_owner = str(st.get("owner_user_id") or "")
        if not should_include_job_for_user(user=user, st_owner=st_owner, owner_user_id=owner_user_id):
            continue
        items.append(build_job_list_item(job_dir=job_dir, st=st, st_owner=st_owner))
    items.sort(key=lambda x: x.created_at, reverse=True)
    return JobListResponse(items=items, total=len(items))


@route_get("/{job_id}")
def get_job(user: CurrentUserDep, job_id: str):
    _paths, st = load_job_state_for_user(user=user, job_id=job_id)
    return st


@route_post("/{job_id}/start")
def start_job(user: CurrentUserDep, job_id: str, jm: JobManager = Depends(get_job_manager)):
    # start_job：embedded judge 会启动线程；independent judge 仅进入 queued。
    _paths, st = load_job_state_for_user(user=user, job_id=job_id)
    owner_id = str(st.get("owner_user_id") or "")
    try:
        new_state = jm.start_job(job_id=job_id, owner_user_id=owner_id)
    except RuntimeError as e:
        if str(e) == "already_finished":
            http_error(409, "already_finished", "Job already finished")
        raise
    job_id_value = str(job_id)
    status = str(new_state.get("status") or "")
    return {"job_id": job_id_value, "status": status}


@route_post("/{job_id}/cancel")
def cancel_job(user: CurrentUserDep, job_id: str, jm: JobManager = Depends(get_job_manager)):
    # cancel_job：best-effort 停止 runner 并标记 state.json。
    _paths, _st = load_job_state_for_user(user=user, job_id=job_id)
    new_state = jm.cancel_job(job_id=job_id)
    job_id_value = str(job_id)
    status = str(new_state.get("status") or "")
    return {"job_id": job_id_value, "status": status}


@route_get("/{job_id}/artifacts/{name}")
def get_artifact(user: CurrentUserDep, job_id: str, name: str):
    # artifacts 仅允许 3 个固定文件名，避免任意路径读取。
    if name not in ("main.cpp", "solution.json", "report.json"):
        http_error(404, "not_found", "Artifact not found")
    paths, _st = load_job_state_for_user(user=user, job_id=job_id)
    file_path = paths.output_dir / name
    if not file_path.exists():
        http_error(404, "not_found", "Artifact not found")
    media = "application/json" if name.endswith(".json") else "text/plain"
    return FileResponse(file_path, media_type=media, filename=name)


@route_get("/{job_id}/usage")
def job_usage(user: CurrentUserDep, db: DbDep, job_id: str):
    from sqlalchemy import select  # noqa: WPS433

    from ..models import UsageRecord  # noqa: WPS433
    from ..services.pricing import microusd_to_amount_str  # noqa: WPS433

    # usage 是页面展示用的聚合视图：汇总 tokens + cost。
    _paths, st = load_job_state_for_user(user=user, job_id=job_id)

    rows = db.scalars(select(UsageRecord).where(UsageRecord.job_id == job_id)).all()
    record_ids = [r.id for r in rows]
    owner_user_id = st.get("owner_user_id")
    model = st.get("model")
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
    return {"job_id": job_id, "owner_user_id": owner_user_id, "model": model, "usage": usage, "cost": cost, "records": record_ids}
