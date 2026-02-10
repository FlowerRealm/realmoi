from __future__ import annotations

import json
import os
import socket
import base64
import shutil
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .services.job_manager import GenerateBundle, JobManager
from .services.job_paths import get_job_paths
from .settings import SETTINGS

try:
    from websockets.sync.client import connect  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    connect = None  # type: ignore[assignment]


def _resolve_machine_id() -> str:
    value = str(SETTINGS.judge_machine_id or "").strip()
    if value:
        return value
    return f"{socket.gethostname()}-{os.getpid()}"


def _resolve_work_root() -> Path:
    """Resolve local job workspace root for judge worker."""

    raw = str(SETTINGS.judge_work_root or "").strip()
    if raw:
        return Path(raw)
    if SETTINGS.runner_executor == "docker":
        return Path(SETTINGS.jobs_root) / ".judge-work"
    return Path("/tmp/realmoi-judge-work")


def _structured(result: dict[str, Any]) -> dict[str, Any]:
    payload = result.get("structuredContent") or {}
    return payload if isinstance(payload, dict) else {}


def _prepare_generate_bundle(*, client: McpJudgeClient, job_id: str, claim_id: str) -> GenerateBundle:
    result = client.call_tool(
        name="judge.prepare_generate",
        arguments={"job_id": job_id, "claim_id": claim_id},
    )
    payload = _structured(result)
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
    except Exception as e:  # noqa: BLE001
        raise McpJudgeClientError(f"prepare_generate_invalid_auth:{e}") from e

    return GenerateBundle(
        effective_config_toml=config_toml,
        auth_json_bytes=auth_bytes,
        openai_base_url=base_url,
        mock_mode=mock_mode,
    )


def _download_job_input(*, client: McpJudgeClient, job_id: str, claim_id: str, dest_root: Path) -> None:
    dest_root.mkdir(parents=True, exist_ok=True)

    result = client.call_tool(
        name="judge.input.list",
        arguments={"job_id": job_id, "claim_id": claim_id},
    )
    items = _structured(result).get("items") or []
    if not isinstance(items, list):
        return

    for item in items:
        if not isinstance(item, dict):
            continue
        rel = str(item.get("path") or "").strip().replace("\\", "/")
        if not rel:
            continue
        parts = [p for p in rel.split("/") if p]
        if any(p in {".", ".."} for p in parts):
            continue
        target = dest_root.joinpath(*parts)
        target.parent.mkdir(parents=True, exist_ok=True)

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
                chunk_payload = _structured(chunk_result)
                chunk_b64 = str(chunk_payload.get("chunk_b64") or "")
                try:
                    chunk = base64.b64decode(chunk_b64.encode("ascii"))
                except Exception:
                    chunk = b""
                out.write(chunk)
                offset = int(chunk_payload.get("next_offset") or (offset + len(chunk)))
                if chunk_payload.get("eof") or not chunk:
                    break


def _sync_append_loop(
    *,
    stop: threading.Event,
    client: McpJudgeClient,
    job_id: str,
    claim_id: str,
    local_path: Path,
    tool_name: str,
    poll_interval: float,
) -> None:
    local_offset = 0
    remote_offset = 0

    while not stop.is_set():
        if not local_path.exists():
            time.sleep(poll_interval)
            continue

        try:
            with local_path.open("rb") as fp:
                fp.seek(max(0, local_offset))
                chunk = fp.read(64 * 1024)
        except Exception:
            time.sleep(poll_interval)
            continue

        if not chunk:
            time.sleep(poll_interval)
            continue

        try:
            result = client.call_tool(
                name=tool_name,
                arguments={
                    "job_id": job_id,
                    "claim_id": claim_id,
                    "offset": remote_offset,
                    "chunk_b64": base64.b64encode(chunk).decode("ascii"),
                },
            )
        except Exception:
            time.sleep(max(0.2, poll_interval))
            continue

        payload = _structured(result)
        if payload.get("ok") is True:
            written_bytes = int(payload.get("written_bytes") or len(chunk))
            next_offset = int(payload.get("next_offset") or (remote_offset + written_bytes))
            remote_offset = next_offset
            local_offset += len(chunk)
            continue

        if payload.get("code") == "offset_mismatch":
            current = int(payload.get("current_offset") or 0)
            remote_offset = current
            local_offset = max(local_offset, current)
            continue

        time.sleep(max(0.2, poll_interval))


def _sync_state_loop(
    *,
    stop: threading.Event,
    client: McpJudgeClient,
    job_id: str,
    claim_id: str,
    local_state_path: Path,
    poll_interval: float,
) -> None:
    last_sig: tuple[str, str, str] | None = None

    while not stop.is_set():
        if not local_state_path.exists():
            time.sleep(poll_interval)
            continue

        try:
            state = json.loads(local_state_path.read_text(encoding="utf-8"))
        except Exception:
            time.sleep(poll_interval)
            continue
        if not isinstance(state, dict):
            time.sleep(poll_interval)
            continue

        containers = state.get("containers") if isinstance(state.get("containers"), dict) else {}
        generate_info = containers.get("generate") if isinstance(containers.get("generate"), dict) else {}
        test_info = containers.get("test") if isinstance(containers.get("test"), dict) else {}
        sig = (
            str(state.get("status") or ""),
            str(generate_info.get("exit_code") or ""),
            str(test_info.get("exit_code") or ""),
        )
        if sig == last_sig:
            time.sleep(poll_interval)
            continue

        try:
            client.call_tool(
                name="judge.job.patch_state",
                arguments={"job_id": job_id, "claim_id": claim_id, "patch": state},
            )
            last_sig = sig
        except Exception:
            time.sleep(max(0.2, poll_interval))


def _cancel_poll_loop(
    *,
    stop: threading.Event,
    client: McpJudgeClient,
    manager: JobManager,
    job_id: str,
    claim_id: str,
    poll_interval: float,
) -> None:
    while not stop.is_set():
        try:
            result = client.call_tool(
                name="judge.job.get_state",
                arguments={"job_id": job_id, "claim_id": claim_id},
            )
        except Exception:
            time.sleep(max(0.5, poll_interval))
            continue

        state = _structured(result)
        if str(state.get("status") or "") == "cancelled":
            try:
                manager.cancel_job(job_id=job_id)
            except Exception:
                pass
            return

        time.sleep(poll_interval)


class McpJudgeClientError(RuntimeError):
    pass


class McpJudgeClient:
    def __init__(self, *, ws_urls: list[str]):
        self._ws_urls = ws_urls
        self._ws = None
        self._next_id = 0
        self._connected_url = ""
        self._lock = threading.RLock()

    def _ensure_connected(self) -> None:
        if self._ws is not None:
            return
        if connect is None:
            raise McpJudgeClientError("websockets_not_installed")

        last_exc: Exception | None = None
        for url in self._ws_urls:
            try:
                self._ws = connect(url, open_timeout=2)  # type: ignore[misc]
                self._connected_url = url
                self._next_id = 0
                self._request("initialize", {})
                print(f"[judge] mcp connected url={url}", flush=True)
                return
            except Exception as e:  # noqa: BLE001
                last_exc = e
                self._ws = None
                self._connected_url = ""
                continue

        raise McpJudgeClientError(f"mcp_connect_failed:{last_exc}")

    def close(self) -> None:
        if self._ws is None:
            return
        try:
            self._ws.close()
        except Exception:
            pass
        self._ws = None
        self._connected_url = ""

    def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._ensure_connected()
            if self._ws is None:
                raise McpJudgeClientError("mcp_disconnected")

            self._next_id += 1
            msg_id = self._next_id
            payload = {"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params}
            try:
                self._ws.send(json.dumps(payload, ensure_ascii=False))
            except Exception as e:  # noqa: BLE001
                self.close()
                raise McpJudgeClientError(f"mcp_send_failed:{e}") from e

            while True:
                try:
                    raw = self._ws.recv()
                except Exception as e:  # noqa: BLE001
                    self.close()
                    raise McpJudgeClientError(f"mcp_recv_failed:{e}") from e
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue
                if msg.get("id") != msg_id:
                    continue
                if "error" in msg:
                    raise McpJudgeClientError(f"mcp_error:{msg.get('error')}")
                result = msg.get("result")
                if not isinstance(result, dict):
                    return {}
                return result

    def call_tool(self, *, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self._request("tools/call", {"name": name, "arguments": arguments})


def _normalize_api_base(value: str) -> str:
    base = str(value or "").strip().rstrip("/")
    if not base:
        return ""
    if base.endswith("/api"):
        return base
    return f"{base}/api"


def _to_ws_base(api_base_url: str) -> str:
    if api_base_url.startswith("https://"):
        return "wss://" + api_base_url.removeprefix("https://")
    if api_base_url.startswith("http://"):
        return "ws://" + api_base_url.removeprefix("http://")
    if api_base_url.startswith("ws://") or api_base_url.startswith("wss://"):
        return api_base_url
    return "ws://" + api_base_url


def _resolve_mcp_ws_urls() -> list[str]:
    token = str(SETTINGS.judge_mcp_token or "").strip()
    if not token:
        return []

    bases: list[str] = []
    configured = _normalize_api_base(str(SETTINGS.judge_api_base_url or ""))
    if configured:
        bases.append(configured)
    bases.extend(["http://backend:8000/api", "http://127.0.0.1:8000/api"])

    seen: set[str] = set()
    urls: list[str] = []
    for base in bases:
        base = _normalize_api_base(base)
        if not base or base in seen:
            continue
        seen.add(base)
        ws_base = _to_ws_base(base).rstrip("/")
        urls.append(f"{ws_base}/mcp/ws?token={quote(token)}")
    return urls


def main() -> int:
    machine_id = _resolve_machine_id()
    interval = max(100, int(SETTINGS.judge_poll_interval_ms or 1000)) / 1000.0
    ws_urls = _resolve_mcp_ws_urls()
    mcp_client = McpJudgeClient(ws_urls=ws_urls) if ws_urls else None
    work_root = _resolve_work_root()
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
            result = mcp_client.call_tool(name="judge.claim_next", arguments={"machine_id": machine_id})
        except McpJudgeClientError as e:
            print(f"[judge] mcp error: {e}", flush=True)
            time.sleep(interval)
            continue

        payload = result.get("structuredContent") or {}
        if not isinstance(payload, dict) or not payload.get("claimed"):
            time.sleep(interval)
            continue

        job_id = str(payload.get("job_id") or "")
        owner_user_id = str(payload.get("owner_user_id") or "")
        claim_id = str(payload.get("claim_id") or "")
        if not job_id or not owner_user_id or not claim_id:
            time.sleep(interval)
            continue

        print(f"[judge] claimed job_id={job_id}", flush=True)
        try:
            def _generate_bundle_provider(  # noqa: WPS430
                *,
                job_id: str,
                owner_user_id: str,  # noqa: ARG001
                state: dict[str, Any],  # noqa: ARG001
                attempt: int,  # noqa: ARG001
                prompt_mode: str,  # noqa: ARG001
            ) -> GenerateBundle:
                return _prepare_generate_bundle(client=mcp_client, job_id=job_id, claim_id=claim_id)

            def _usage_reporter(  # noqa: WPS430
                *,
                job_id: str,
                owner_user_id: str,  # noqa: ARG001
                attempt: int,
                job_dir: Path,
            ) -> None:
                usage_path = job_dir / "output" / "artifacts" / f"attempt_{attempt}" / "usage.json"
                if not usage_path.exists():
                    return
                try:
                    usage_obj = json.loads(usage_path.read_text(encoding="utf-8"))
                except Exception:
                    return
                if not isinstance(usage_obj, dict):
                    return
                try:
                    mcp_client.call_tool(
                        name="judge.usage.ingest",
                        arguments={
                            "job_id": job_id,
                            "claim_id": claim_id,
                            "attempt": attempt,
                            "usage": usage_obj,
                        },
                    )
                except Exception:
                    return

            manager = JobManager(
                jobs_root=work_root,
                generate_bundle_provider=_generate_bundle_provider,
                usage_reporter=_usage_reporter,
            )
            paths = get_job_paths(jobs_root=work_root, job_id=job_id)
            if paths.root.exists():
                shutil.rmtree(paths.root, ignore_errors=True)
            paths.input_dir.mkdir(parents=True, exist_ok=True)
            paths.output_dir.mkdir(parents=True, exist_ok=True)
            paths.logs_dir.mkdir(parents=True, exist_ok=True)

            # Download input/ and state.json from backend via MCP.
            _download_job_input(client=mcp_client, job_id=job_id, claim_id=claim_id, dest_root=paths.input_dir)
            try:
                state_result = mcp_client.call_tool(
                    name="judge.job.get_state",
                    arguments={"job_id": job_id, "claim_id": claim_id},
                )
                state_payload = _structured(state_result)
                paths.state_json.write_text(
                    json.dumps(state_payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
            except Exception:
                pass
            if not paths.state_json.exists():
                paths.state_json.write_text(
                    json.dumps({"job_id": job_id, "owner_user_id": owner_user_id, "status": "queued"}, ensure_ascii=False, indent=2)
                    + "\n",
                    encoding="utf-8",
                )

            stop = threading.Event()
            threads = [
                threading.Thread(
                    target=_sync_append_loop,
                    kwargs={
                        "stop": stop,
                        "client": mcp_client,
                        "job_id": job_id,
                        "claim_id": claim_id,
                        "local_path": paths.terminal_log,
                        "tool_name": "judge.job.append_terminal",
                        "poll_interval": 0.05,
                    },
                    daemon=True,
                ),
                threading.Thread(
                    target=_sync_append_loop,
                    kwargs={
                        "stop": stop,
                        "client": mcp_client,
                        "job_id": job_id,
                        "claim_id": claim_id,
                        "local_path": paths.agent_status_jsonl,
                        "tool_name": "judge.job.append_agent_status",
                        "poll_interval": 0.05,
                    },
                    daemon=True,
                ),
                threading.Thread(
                    target=_sync_state_loop,
                    kwargs={
                        "stop": stop,
                        "client": mcp_client,
                        "job_id": job_id,
                        "claim_id": claim_id,
                        "local_state_path": paths.state_json,
                        "poll_interval": 0.2,
                    },
                    daemon=True,
                ),
                threading.Thread(
                    target=_cancel_poll_loop,
                    kwargs={
                        "stop": stop,
                        "client": mcp_client,
                        "manager": manager,
                        "job_id": job_id,
                        "claim_id": claim_id,
                        "poll_interval": 0.5,
                    },
                    daemon=True,
                ),
            ]
            for t in threads:
                t.start()

            try:
                manager.run_claimed_job(job_id=job_id, owner_user_id=owner_user_id)
            finally:
                stop.set()
                for t in threads:
                    try:
                        t.join(timeout=1.0)
                    except Exception:
                        pass

            # Final state sync + artifacts upload.
            try:
                local_state = json.loads(paths.state_json.read_text(encoding="utf-8"))
                if isinstance(local_state, dict):
                    mcp_client.call_tool(
                        name="judge.job.patch_state",
                        arguments={"job_id": job_id, "claim_id": claim_id, "patch": local_state},
                    )
            except Exception:
                pass

            main_cpp = ""
            solution_json = None
            report_json = None
            try:
                main_path = paths.output_dir / "main.cpp"
                if main_path.exists():
                    main_cpp = main_path.read_text(encoding="utf-8", errors="replace")
                sol_path = paths.output_dir / "solution.json"
                if sol_path.exists():
                    solution_json = json.loads(sol_path.read_text(encoding="utf-8"))
                rep_path = paths.output_dir / "report.json"
                if rep_path.exists():
                    report_json = json.loads(rep_path.read_text(encoding="utf-8"))
            except Exception:
                pass

            try:
                mcp_client.call_tool(
                    name="judge.job.put_artifacts",
                    arguments={
                        "job_id": job_id,
                        "claim_id": claim_id,
                        "main_cpp": main_cpp,
                        "solution_json": solution_json if isinstance(solution_json, dict) else {},
                        "report_json": report_json if isinstance(report_json, dict) else {},
                    },
                )
            except Exception:
                pass

            shutil.rmtree(paths.root, ignore_errors=True)
        finally:
            try:
                mcp_client.call_tool(name="judge.release_claim", arguments={"job_id": job_id, "claim_id": claim_id})
            except Exception as e:  # noqa: BLE001
                print(f"[judge] release claim failed job_id={job_id}: {e}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
