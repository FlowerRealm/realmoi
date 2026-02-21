#
# Independent judge claim/lock helpers.
#
from __future__ import annotations

"""独立 judge 模式：队列领取与锁文件管理。

该模块将 `JobManager` 中与 `judge.lock` 相关的文件锁逻辑拆出，避免核心调度代码被锁细节淹没。
行为保持为 best-effort：读取失败会放弃当前候选并继续扫描，不应导致 worker 崩溃。
"""

import json
import os
import pathlib
import secrets
import time

from ..services import job_paths, job_state


def claim_next_queued_job(*, jobs_root: pathlib.Path, machine_id: str, stale_seconds: int) -> dict[str, str] | None:
    """从 `jobs_root` 扫描并尝试领取一个 queued job。"""

    candidates: list[tuple[str, str]] = []
    for p in jobs_root.iterdir():
        if not p.is_dir():
            continue
        state_path = p / "state.json"
        if not state_path.exists():
            continue
        try:
            state = job_state.load_state(state_path)
        except Exception:
            continue
        if state.get("status") != "queued":
            continue
        created_at = str(state.get("created_at") or "")
        candidates.append((created_at, p.name))

    for _created_at, job_id in sorted(candidates):
        payload = try_claim_job(
            jobs_root=jobs_root,
            job_id=job_id,
            machine_id=machine_id,
            stale_seconds=stale_seconds,
        )
        if payload is not None:
            return payload
    return None


def release_judge_claim(*, jobs_root: pathlib.Path, job_id: str, claim_id: str) -> bool:
    """释放 `judge.lock`（用于 backend MCP 工具 `judge.release_claim`）。"""

    paths = job_paths.get_job_paths(jobs_root=jobs_root, job_id=job_id)
    lock_path = paths.logs_dir / "judge.lock"
    if not lock_path.exists():
        return True

    try:
        obj = json.loads(lock_path.read_text(encoding="utf-8"))
    except Exception:
        lock_path.unlink(missing_ok=True)
        return True

    if str(obj.get("claim_id") or "") != str(claim_id or ""):
        return False

    lock_path.unlink(missing_ok=True)
    return True


def try_claim_job(
    *,
    jobs_root: pathlib.Path,
    job_id: str,
    machine_id: str,
    stale_seconds: int,
) -> dict[str, str] | None:
    """尝试通过原子锁文件领取一个 queued job；成功时返回 payload。"""

    paths = job_paths.get_job_paths(jobs_root=jobs_root, job_id=job_id)
    if not paths.state_json.exists():
        return None

    lock_path = paths.logs_dir / "judge.lock"
    try_break_stale_lock(lock_path=lock_path, stale_seconds=stale_seconds)
    claim_id = secrets.token_hex(16)
    if not acquire_lock(lock_path=lock_path, machine_id=machine_id, claim_id=claim_id):
        return None

    try:
        state = job_state.load_state(paths.state_json)
    except Exception:
        lock_path.unlink(missing_ok=True)
        return None

    if state.get("status") != "queued":
        lock_path.unlink(missing_ok=True)
        return None

    owner_user_id = str(state.get("owner_user_id") or "")
    if not owner_user_id:
        state["status"] = "failed"
        state["finished_at"] = job_state.now_iso()
        state["expires_at"] = job_state.iso_after_days(7)
        state["error"] = {"code": "invalid_state", "message": "Missing owner_user_id"}
        job_state.save_state(paths.state_json, state)
        lock_path.unlink(missing_ok=True)
        return None

    judge = state.get("judge") or {}
    judge["machine_id"] = machine_id
    judge["claimed_at"] = job_state.now_iso()
    judge["claim_id"] = claim_id
    state["judge"] = judge
    job_state.save_state(paths.state_json, state)
    return {
        "job_id": job_id,
        "owner_user_id": owner_user_id,
        "lock_path": str(lock_path.resolve()),
        "claim_id": claim_id,
    }


def acquire_lock(*, lock_path: pathlib.Path, machine_id: str, claim_id: str) -> bool:
    """原子创建锁文件；成功返回 True。"""

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        file_descriptor = os.open(str(lock_path), flags, 0o644)
    except FileExistsError:
        return False
    except OSError:
        return False
    with os.fdopen(file_descriptor, "w", encoding="utf-8") as file_handle:
        file_handle.write(
            json.dumps(
                {"machine_id": machine_id, "claim_id": claim_id, "claimed_at": job_state.now_iso()},
                ensure_ascii=False,
            )
        )
        file_handle.write("\n")
    return True


def try_break_stale_lock(*, lock_path: pathlib.Path, stale_seconds: int) -> None:
    """锁超过 `stale_seconds` 时删除（worker 崩溃时的清理）。"""

    if not lock_path.exists():
        return
    try:
        age = time.time() - lock_path.stat().st_mtime
    except OSError:
        return
    if age >= float(stale_seconds):
        lock_path.unlink(missing_ok=True)
