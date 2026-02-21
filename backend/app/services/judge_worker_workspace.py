from __future__ import annotations

import base64
import binascii
import json
import shutil
from pathlib import Path

from .job_paths import get_job_paths
from .judge_mcp_client import McpJudgeClient, McpJudgeClientError
from .judge_worker_common import log_warn, structured_content


def safe_rmtree(path: Path) -> None:
    try:
        shutil.rmtree(path)
    except FileNotFoundError:
        return
    except OSError as exc:
        log_warn(key="workspace_rmtree", message=f"remove workspace failed path={path}: {exc}")


def init_job_workspace(*, work_root: Path, job_id: str):
    # Create a clean local workspace directory for a claimed job.
    paths = get_job_paths(jobs_root=work_root, job_id=job_id)
    if paths.root.exists():
        safe_rmtree(paths.root)
    paths.input_dir.mkdir(parents=True, exist_ok=True)
    paths.output_dir.mkdir(parents=True, exist_ok=True)
    paths.logs_dir.mkdir(parents=True, exist_ok=True)
    return paths


def normalize_rel_path(raw: str) -> list[str] | None:
    rel = str(raw or "").strip().replace("\\", "/")
    if not rel:
        return None
    parts = [p for p in rel.split("/") if p]
    if any(p in {".", ".."} for p in parts):
        return None
    return parts


def download_one_file(
    *,
    client: McpJudgeClient,
    job_id: str,
    claim_id: str,
    rel: str,
    target: Path,
) -> None:
    offset = 0
    with target.open("wb") as out:
        while True:
            chunk_result = client.call_tool(
                name="judge.input.read_chunk",
                arguments={
                    "job_id": job_id,
                    "claim_id": claim_id,
                    "path": rel,
                    "offset": offset,
                    "max_bytes": 1024 * 1024,
                },
            )
            chunk_payload = structured_content(chunk_result)
            chunk_b64 = str(chunk_payload.get("chunk_b64") or "")
            try:
                chunk = base64.b64decode(chunk_b64.encode("ascii"))
            except (binascii.Error, ValueError, UnicodeEncodeError) as exc:
                log_warn(key="input_chunk_decode", message=f"input chunk decode failed path={rel}: {exc}")
                chunk = b""
            out.write(chunk)
            offset = int(chunk_payload.get("next_offset") or (offset + len(chunk)))
            if chunk_payload.get("eof") or not chunk:
                break


def download_job_input(*, client: McpJudgeClient, job_id: str, claim_id: str, dest_root: Path) -> None:
    # Download all job input files into local workspace root.
    dest_root.mkdir(parents=True, exist_ok=True)

    result = client.call_tool(
        name="judge.input.list",
        arguments={"job_id": job_id, "claim_id": claim_id},
    )
    items = structured_content(result).get("items") or []
    if not isinstance(items, list):
        return

    for item in items:
        if not isinstance(item, dict):
            continue
        rel = str(item.get("path") or "")
        parts = normalize_rel_path(rel)
        if parts is None:
            continue
        rel_norm = "/".join(parts)
        target = dest_root.joinpath(*parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        download_one_file(client=client, job_id=job_id, claim_id=claim_id, rel=rel_norm, target=target)


def write_initial_state(*, client: McpJudgeClient, job_id: str, claim_id: str, owner_user_id: str, state_path: Path) -> None:
    # Seed local state.json from backend (best-effort).
    try:
        state_result = client.call_tool(
            name="judge.job.get_state",
            arguments={"job_id": job_id, "claim_id": claim_id},
        )
        state_payload = structured_content(state_result)
        state_path.write_text(
            json.dumps(state_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except McpJudgeClientError as exc:
        log_warn(key="seed_state", message=f"seed local state from backend failed job_id={job_id}: {exc}")

    if state_path.exists():
        return
    state_path.write_text(
        json.dumps({"job_id": job_id, "owner_user_id": owner_user_id, "status": "queued"}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
