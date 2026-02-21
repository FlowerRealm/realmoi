from __future__ import annotations

# Independent judge worker implementation.
#
# This module contains the operational logic used by `backend/app/judge_daemon.py`:
# - claim queued jobs over MCP WebSocket tools
# - sync terminal/state logs while a job runs
# - upload final artifacts and release claim locks
#
# It is intentionally split out so the daemon entrypoint stays small and the
# orchestration code can be reasoned about and tested in isolation.

import base64
import binascii
import json
import time
from pathlib import Path
from typing import Any

from ..settings import SETTINGS
from .job_manager import JobManager
from .job_manager_plans import GenerateBundle
from .judge_mcp_client import McpJudgeClient, McpJudgeClientError, resolve_mcp_ws_urls
from .judge_worker_artifacts import cleanup_workspace, read_artifacts, sync_final_state, upload_artifacts
from .judge_worker_common import log_warn, resolve_machine_id, resolve_work_root, structured_content
from .judge_worker_sync import McpJobContext, SyncPaths, start_sync_threads, stop_threads
from .judge_worker_workspace import download_job_input, init_job_workspace, write_initial_state

def prepare_generate_bundle(*, client: McpJudgeClient, job_id: str, claim_id: str) -> GenerateBundle:
    # Ask backend to produce effective Codex config and auth bytes for a job.
    result = client.call_tool(
        name="judge.prepare_generate",
        arguments={"job_id": job_id, "claim_id": claim_id},
    )
    payload = structured_content(result)
    config_toml = str(payload.get("effective_config_toml") or "")
    auth_b64 = str(payload.get("auth_json_b64") or "")
    base_url = str(payload.get("openai_base_url") or "")
    mock_mode = bool(payload.get("mock_mode") is True)

    if not config_toml:
        raise McpJudgeClientError("prepare_generate_missing_config")
    if not base_url:
        raise McpJudgeClientError("prepare_generate_missing_base_url")

    try:
        auth_bytes = base64.b64decode(auth_b64.encode("ascii")) if auth_b64 else b"{}\n"
    except (binascii.Error, ValueError, UnicodeEncodeError) as e:
        raise McpJudgeClientError(f"prepare_generate_invalid_auth:{e}") from e

    return GenerateBundle(
        effective_config_toml=config_toml,
        auth_json_bytes=auth_bytes,
        openai_base_url=base_url,
        mock_mode=mock_mode,
    )


class McpGenerateBundleProvider:
    def __init__(self, *, client: McpJudgeClient, claim_id: str):
        self._client = client
        self._claim_id = claim_id

    def __call__(  # noqa: D401
        self,
        *,
        job_id: str,
        owner_user_id: str,  # noqa: ARG002
        state: dict[str, Any],  # noqa: ARG002
        attempt: int,  # noqa: ARG002
        prompt_mode: str,  # noqa: ARG002
    ) -> GenerateBundle:
        return prepare_generate_bundle(client=self._client, job_id=job_id, claim_id=self._claim_id)


class McpUsageReporter:
    def __init__(self, *, client: McpJudgeClient, claim_id: str):
        self._client = client
        self._claim_id = claim_id

    def __call__(self, *, job_id: str, owner_user_id: str, attempt: int, job_dir: Path) -> None:  # noqa: ARG002
        usage_path = job_dir / "output" / "artifacts" / f"attempt_{attempt}" / "usage.json"
        if not usage_path.exists():
            return
        try:
            usage_obj = json.loads(usage_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            log_warn(key="usage_read", message=f"read usage.json failed job_id={job_id}: {e}")
            return
        if not isinstance(usage_obj, dict):
            return
        try:
            self._client.call_tool(
                name="judge.usage.ingest",
                arguments={
                    "job_id": job_id,
                    "claim_id": self._claim_id,
                    "attempt": attempt,
                    "usage": usage_obj,
                },
            )
        except McpJudgeClientError as e:
            log_warn(key="usage_ingest", message=f"ingest usage failed job_id={job_id}: {e}")
            return


def claim_next_job(*, client: McpJudgeClient, machine_id: str) -> tuple[str, str, str] | None:
    # Claim one queued job via backend MCP tool.
    result = client.call_tool(name="judge.claim_next", arguments={"machine_id": machine_id})
    payload = result.get("structuredContent") or {}
    if not isinstance(payload, dict) or not payload.get("claimed"):
        return None

    job_id = str(payload.get("job_id") or "")
    owner_user_id = str(payload.get("owner_user_id") or "")
    claim_id = str(payload.get("claim_id") or "")
    if not job_id or not owner_user_id or not claim_id:
        return None
    return job_id, owner_user_id, claim_id


def run_claimed_job(*, client: McpJudgeClient, work_root: Path, job_id: str, owner_user_id: str, claim_id: str) -> None:
    # Execute one claimed job end-to-end in local workspace.
    manager = JobManager(
        jobs_root=work_root,
        generate_bundle_provider=McpGenerateBundleProvider(client=client, claim_id=claim_id),
        usage_reporter=McpUsageReporter(client=client, claim_id=claim_id),
    )
    paths = init_job_workspace(work_root=work_root, job_id=job_id)

    download_job_input(client=client, job_id=job_id, claim_id=claim_id, dest_root=paths.input_dir)
    write_initial_state(client=client, job_id=job_id, claim_id=claim_id, owner_user_id=owner_user_id, state_path=paths.state_json)

    ctx = McpJobContext(client=client, job_id=job_id, claim_id=claim_id)
    stop, threads = start_sync_threads(
        ctx=ctx,
        manager=manager,
        paths=SyncPaths(
            terminal_log=paths.terminal_log,
            agent_status_jsonl=paths.agent_status_jsonl,
            state_json=paths.state_json,
        ),
    )
    try:
        manager.run_claimed_job(job_id=job_id, owner_user_id=owner_user_id)
    finally:
        stop_threads(stop=stop, threads=threads)

    sync_final_state(client=client, job_id=job_id, claim_id=claim_id, state_path=paths.state_json)
    main_cpp, solution_json, report_json = read_artifacts(output_dir=paths.output_dir)
    upload_artifacts(
        client=client,
        job_id=job_id,
        claim_id=claim_id,
        main_cpp=main_cpp,
        solution_json=solution_json,
        report_json=report_json,
    )
    cleanup_workspace(root=paths.root)


def run_daemon() -> int:
    # Run judge worker loop forever (or until fatal configuration error).
    machine_id = resolve_machine_id()
    interval = max(100, int(SETTINGS.judge_poll_interval_ms or 1000)) / 1000.0
    token = str(SETTINGS.judge_mcp_token or "").strip()
    ws_urls = resolve_mcp_ws_urls(
        token=token,
        api_base_url=str(SETTINGS.judge_api_base_url or ""),
        fallback_bases=["http://backend:8000/api", "http://127.0.0.1:8000/api"],
    )
    mcp_client = McpJudgeClient(ws_urls=ws_urls, warn=log_warn) if ws_urls else None
    work_root = resolve_work_root()
    work_root.mkdir(parents=True, exist_ok=True)

    print(
        f"[judge] machine_id={machine_id} mode={SETTINGS.judge_mode} executor={SETTINGS.runner_executor} poll={interval:.3f}s",
        flush=True,
    )
    if SETTINGS.judge_mode != "independent":
        print("[judge] warning: REALMOI_JUDGE_MODE is not independent", flush=True)
    if mcp_client is None:
        print("[judge] error: REALMOI_JUDGE_MCP_TOKEN missing; cannot claim jobs via MCP", flush=True)
        return 2

    while True:
        try:
            claimed = claim_next_job(client=mcp_client, machine_id=machine_id)
        except McpJudgeClientError as e:
            print(f"[judge] mcp error: {e}", flush=True)
            time.sleep(interval)
            continue

        if not claimed:
            time.sleep(interval)
            continue

        job_id, owner_user_id, claim_id = claimed

        print(f"[judge] claimed job_id={job_id}", flush=True)
        try:
            run_claimed_job(
                client=mcp_client,
                work_root=work_root,
                job_id=job_id,
                owner_user_id=owner_user_id,
                claim_id=claim_id,
            )
        finally:
            try:
                mcp_client.call_tool(name="judge.release_claim", arguments={"job_id": job_id, "claim_id": claim_id})
            except McpJudgeClientError as e:
                print(f"[judge] release claim failed job_id={job_id}: {e}", flush=True)
