from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path
from typing import Any

from ..db import SessionLocal
from ..models import ModelPricing, UserCodexSettings
from ..services.codex_config import build_effective_config
from ..services.docker_service import create_generate_container, create_test_container, docker_client, put_files, start_log_collector
from ..services.job_paths import JobPaths, get_job_paths
from ..services.job_state import iso_after_days, load_state, now_iso, save_state
from ..services.local_runner import run_local_runner, stop_process_tree
from ..services.upstream_channels import resolve_upstream_target
from ..services.usage_records import ingest_usage_record
from ..settings import SETTINGS


class JobManager:
    def __init__(self, *, jobs_root: Path):
        self._jobs_root = jobs_root
        executor = str(SETTINGS.runner_executor or "local").strip().lower()
        self._runner_executor = executor if executor in {"local", "docker"} else "local"
        self._client = docker_client() if self._runner_executor == "docker" else None
        self._lock = threading.Lock()
        self._threads: dict[str, threading.Thread] = {}
        self._local_procs: dict[str, dict[str, subprocess.Popen[bytes]]] = {}

    def reconcile(self) -> None:
        for p in self._jobs_root.iterdir():
            if not p.is_dir():
                continue
            state_path = p / "state.json"
            if not state_path.exists():
                continue
            try:
                state = load_state(state_path)
            except Exception:
                continue
            if state.get("status") not in ("running_generate", "running_test"):
                continue
            stage = "generate" if state.get("status") == "running_generate" else "test"
            if self._runner_executor != "docker":
                state["status"] = "failed"
                state["finished_at"] = now_iso()
                state["expires_at"] = iso_after_days(7)
                state["error"] = {
                    "code": "local_process_missing",
                    "message": f"Local {stage} process missing after restart",
                }
                save_state(state_path, state)
                continue

            if self._client is None:
                state["status"] = "failed"
                state["finished_at"] = now_iso()
                state["expires_at"] = iso_after_days(7)
                state["error"] = {"code": "docker_unavailable", "message": "Docker executor unavailable"}
                save_state(state_path, state)
                continue

            cinfo = (state.get("containers") or {}).get(stage) or {}
            cid = cinfo.get("id")
            if not cid:
                continue
            try:
                container = self._client.containers.get(cid)
            except Exception:
                state["status"] = "failed"
                state["finished_at"] = now_iso()
                state["expires_at"] = iso_after_days(7)
                state["error"] = {"code": "container_missing", "message": "Container missing"}
                save_state(state_path, state)
                continue
            container.reload()
            if container.status == "exited":
                exit_code = int(container.attrs.get("State", {}).get("ExitCode") or 0)
                cinfo["exit_code"] = exit_code
                (state.setdefault("containers", {}))[stage] = cinfo
                if exit_code != 0:
                    state["status"] = "failed"
                    state["finished_at"] = now_iso()
                    state["expires_at"] = iso_after_days(7)
                    state["error"] = {"code": f"{stage}_failed", "message": "Container exited"}
                save_state(state_path, state)

    def start_job(self, *, job_id: str, owner_user_id: str) -> dict[str, Any]:
        paths = get_job_paths(jobs_root=self._jobs_root, job_id=job_id)
        if not paths.state_json.exists():
            raise FileNotFoundError(job_id)

        with self._lock:
            state = load_state(paths.state_json)
            status = state.get("status")
            if status in ("running_generate", "running_test"):
                return state
            if status in ("succeeded", "failed", "cancelled"):
                raise RuntimeError("already_finished")

            state["status"] = "running_generate"
            state["started_at"] = state.get("started_at") or now_iso()
            save_state(paths.state_json, state)

            t = threading.Thread(
                target=self._run_job_thread,
                kwargs={"job_id": job_id, "owner_user_id": owner_user_id},
                daemon=True,
            )
            self._threads[job_id] = t
            t.start()
            return state

    def cancel_job(self, *, job_id: str) -> dict[str, Any]:
        paths = get_job_paths(jobs_root=self._jobs_root, job_id=job_id)
        if not paths.state_json.exists():
            raise FileNotFoundError(job_id)

        with self._lock:
            state = load_state(paths.state_json)
            status = state.get("status")
            if status in ("cancelled", "succeeded", "failed"):
                return state

            if self._runner_executor == "docker":
                for stage in ("generate", "test"):
                    cinfo = (state.get("containers") or {}).get(stage) or {}
                    cid = cinfo.get("id")
                    if not cid or self._client is None:
                        continue
                    try:
                        c = self._client.containers.get(cid)
                        c.stop(timeout=3)
                    except Exception:
                        pass
            else:
                stage_procs = self._local_procs.pop(job_id, {})
                for proc in stage_procs.values():
                    stop_process_tree(proc)

            state["status"] = "cancelled"
            state["finished_at"] = now_iso()
            state["expires_at"] = iso_after_days(7)
            state["error"] = {"code": "cancelled", "message": "Cancelled"}
            save_state(paths.state_json, state)
            return state

    def _project_root(self) -> Path:
        return Path(__file__).resolve().parents[3]

    def _resolve_runner_path(self, configured_path: str) -> Path:
        path = Path(configured_path)
        if path.is_absolute():
            return path
        return self._project_root() / path

    def _remember_local_process(self, *, job_id: str, stage: str, process: subprocess.Popen[bytes]) -> None:
        with self._lock:
            stage_map = self._local_procs.setdefault(job_id, {})
            stage_map[stage] = process

    def _forget_local_process(self, *, job_id: str, stage: str) -> None:
        with self._lock:
            stage_map = self._local_procs.get(job_id) or {}
            stage_map.pop(stage, None)
            if not stage_map:
                self._local_procs.pop(job_id, None)

    def _run_job_thread(self, *, job_id: str, owner_user_id: str) -> None:
        paths = get_job_paths(jobs_root=self._jobs_root, job_id=job_id)
        attempts_total = 1 + max(0, int(SETTINGS.quality_max_retries))

        try:
            for attempt in range(1, attempts_total + 1):
                # Cancel check
                if load_state(paths.state_json).get("status") == "cancelled":
                    return

                prompt_mode = "generate" if attempt == 1 else "repair"
                self._run_generate(paths=paths, owner_user_id=owner_user_id, attempt=attempt, prompt_mode=prompt_mode)
                self._run_test(paths=paths, owner_user_id=owner_user_id, attempt=attempt)

                report_path = paths.output_dir / "report.json"
                if report_path.exists():
                    try:
                        report = json.loads(report_path.read_text(encoding="utf-8"))
                        if report.get("status") == "succeeded":
                            self._finalize_success(paths=paths)
                            return
                    except Exception:
                        pass

                if attempt < attempts_total:
                    self._append_terminal(paths, f"[backend] attempt {attempt} failed, retrying (repair)...\n")
                    continue

                raise RuntimeError("quality_retries_exhausted")
        except Exception as e:
            state = load_state(paths.state_json)
            if state.get("status") == "cancelled":
                return
            state["status"] = "failed"
            state["finished_at"] = now_iso()
            state["expires_at"] = iso_after_days(7)
            state["error"] = {"code": "failed", "message": str(e)}
            save_state(paths.state_json, state)

    def _append_terminal(self, paths: JobPaths, text: str) -> None:
        try:
            paths.terminal_log.parent.mkdir(parents=True, exist_ok=True)
            with paths.terminal_log.open("ab") as f:
                f.write(text.encode("utf-8"))
        except Exception:
            return

    def _run_generate(self, *, paths: JobPaths, owner_user_id: str, attempt: int, prompt_mode: str) -> None:
        state = load_state(paths.state_json)
        state["status"] = "running_generate"
        save_state(paths.state_json, state)

        rl = state.get("resource_limits") or {}
        cpus = float(rl.get("cpus") or SETTINGS.default_cpus)
        memory_mb = int(rl.get("memory_limit_mb") or SETTINGS.default_memory_mb)
        pids_limit = int(rl.get("pids_limit") or SETTINGS.default_pids)

        max_terminal = int(
            (state.get("resource_limits") or {}).get("max_terminal_log_bytes") or SETTINGS.default_max_terminal_log_bytes
        )

        target = None
        # Build effective config using latest user overrides and channel config.
        with SessionLocal() as db:
            row = db.get(UserCodexSettings, owner_user_id)
            overrides = row.overrides_toml if row else ""
            model = str(state.get("model") or "")
            model_pricing = db.get(ModelPricing, model) if model else None
            upstream_channel = str(state.get("upstream_channel") or "").strip()
            if not upstream_channel:
                upstream_channel = (model_pricing.upstream_channel if model_pricing else "") or ""
            if not SETTINGS.mock_mode:
                try:
                    target = resolve_upstream_target(upstream_channel, db=db)
                except ValueError as e:
                    raise RuntimeError(f"upstream_config_error:{e}") from e
        cfg = build_effective_config(user_overrides_toml=overrides)

        if SETTINGS.mock_mode:
            upstream_base_url = SETTINGS.openai_base_url
            auth_bytes = b"{}\n"
            secret = ""
        else:
            if target is None:
                raise RuntimeError("upstream_config_error:missing_target")
            upstream_base_url = target.base_url
            secret = target.api_key
            auth_bytes = (json.dumps({"OPENAI_API_KEY": secret}, ensure_ascii=False) + "\n").encode("utf-8")

        extra_env = {
            "ATTEMPT": str(attempt),
            "PROMPT_MODE": prompt_mode,
            "OPENAI_BASE_URL": upstream_base_url,
        }
        if SETTINGS.mock_mode:
            extra_env["MOCK_MODE"] = "1"

        state.setdefault("containers", {})
        if self._runner_executor == "docker":
            if self._client is None:
                raise RuntimeError("docker_unavailable")
            container = create_generate_container(
                client=self._client,
                job_id=paths.root.name,
                owner_user_id=owner_user_id,
                attempt=attempt,
                job_dir=paths.root,
                cpus=cpus,
                memory_mb=memory_mb,
                pids_limit=pids_limit,
                extra_env=extra_env,
            )

            state["containers"]["generate"] = {
                "id": container.id,
                "name": container.name,
                "exit_code": None,
                "attempt": attempt,
            }
            save_state(paths.state_json, state)

            put_files(
                container,
                dest_dir="/codex_home",
                files={"config.toml": cfg.effective_config_toml.encode("utf-8"), "auth.json": auth_bytes},
            )

            start_log_collector(
                container=container,
                log_path=paths.terminal_log,
                max_bytes=max_terminal,
                redact_secrets=[secret],
            )
            container.start()
            res = container.wait()
            exit_code = int(res.get("StatusCode") or 0)
        else:
            script_path = self._resolve_runner_path(SETTINGS.runner_generate_script)
            schema_path = self._resolve_runner_path(SETTINGS.runner_schema_path)
            test_script_hint = self._resolve_runner_path(SETTINGS.runner_test_script)
            codex_home = paths.root / ".codex_home"
            codex_home.mkdir(parents=True, exist_ok=True)
            (codex_home / "config.toml").write_text(cfg.effective_config_toml, encoding="utf-8")
            (codex_home / "auth.json").write_bytes(auth_bytes)

            state["containers"]["generate"] = {
                "id": f"local-generate-attempt-{attempt}",
                "name": script_path.name,
                "exit_code": None,
                "attempt": attempt,
            }
            save_state(paths.state_json, state)

            local_env = {
                **extra_env,
                "CODEX_HOME": str(codex_home.resolve()),
                "REALMOI_JOB_DIR": str(paths.root.resolve()),
                "REALMOI_SCHEMA_PATH": str(schema_path.resolve()),
                "REALMOI_TEST_SCRIPT_HINT": str(test_script_hint.resolve()),
            }
            exit_code, pid = run_local_runner(
                script_path=script_path.resolve(),
                env=local_env,
                log_path=paths.terminal_log,
                max_bytes=max_terminal,
                redact_secrets=[secret],
                on_started=lambda proc: self._remember_local_process(
                    job_id=paths.root.name,
                    stage="generate",
                    process=proc,
                ),
                on_finished=lambda: self._forget_local_process(
                    job_id=paths.root.name,
                    stage="generate",
                ),
            )
            state = load_state(paths.state_json)
            state["containers"]["generate"]["id"] = f"local-generate-pid-{pid}"
            save_state(paths.state_json, state)

        state = load_state(paths.state_json)
        state["containers"]["generate"]["exit_code"] = exit_code
        save_state(paths.state_json, state)
        if exit_code != 0:
            raise RuntimeError("generate_failed")

        self._scan_for_secret(paths=paths, secret=secret)
        ingest_usage_record(job_id=paths.root.name, owner_user_id=owner_user_id, attempt=attempt, job_dir=paths.root)

    def _run_test(self, *, paths: JobPaths, owner_user_id: str, attempt: int) -> None:
        state = load_state(paths.state_json)
        state["status"] = "running_test"
        save_state(paths.state_json, state)

        rl = state.get("resource_limits") or {}
        cpus = float(rl.get("cpus") or SETTINGS.default_cpus)
        memory_mb = int(rl.get("memory_limit_mb") or SETTINGS.default_memory_mb)
        pids_limit = int(rl.get("pids_limit") or SETTINGS.default_pids)
        max_terminal = int(rl.get("max_terminal_log_bytes") or SETTINGS.default_max_terminal_log_bytes)

        state.setdefault("containers", {})
        if self._runner_executor == "docker":
            if self._client is None:
                raise RuntimeError("docker_unavailable")
            container = create_test_container(
                client=self._client,
                job_id=paths.root.name,
                owner_user_id=owner_user_id,
                attempt=attempt,
                job_dir=paths.root,
                cpus=cpus,
                memory_mb=memory_mb,
                pids_limit=pids_limit,
                extra_env={
                    "ATTEMPT": str(attempt),
                },
            )

            state["containers"]["test"] = {
                "id": container.id,
                "name": container.name,
                "exit_code": None,
                "attempt": attempt,
            }
            save_state(paths.state_json, state)

            start_log_collector(
                container=container,
                log_path=paths.terminal_log,
                max_bytes=max_terminal,
                redact_secrets=[],
            )
            container.start()
            res = container.wait()
            exit_code = int(res.get("StatusCode") or 0)
        else:
            script_path = self._resolve_runner_path(SETTINGS.runner_test_script)
            state["containers"]["test"] = {
                "id": f"local-test-attempt-{attempt}",
                "name": script_path.name,
                "exit_code": None,
                "attempt": attempt,
            }
            save_state(paths.state_json, state)

            local_env = {
                "ATTEMPT": str(attempt),
                "REALMOI_JOB_DIR": str(paths.root.resolve()),
                "REALMOI_WORK_DIR": str((paths.root / ".tmp_work").resolve()),
            }
            exit_code, pid = run_local_runner(
                script_path=script_path.resolve(),
                env=local_env,
                log_path=paths.terminal_log,
                max_bytes=max_terminal,
                redact_secrets=[],
                on_started=lambda proc: self._remember_local_process(
                    job_id=paths.root.name,
                    stage="test",
                    process=proc,
                ),
                on_finished=lambda: self._forget_local_process(
                    job_id=paths.root.name,
                    stage="test",
                ),
            )
            state = load_state(paths.state_json)
            state["containers"]["test"]["id"] = f"local-test-pid-{pid}"
            save_state(paths.state_json, state)

        state = load_state(paths.state_json)
        state["containers"]["test"]["exit_code"] = exit_code
        save_state(paths.state_json, state)

        attempt_dir = paths.output_dir / "artifacts" / f"attempt_{attempt}" / "test_output"
        report_src = attempt_dir / "report.json"
        if report_src.exists():
            (paths.output_dir / "report.json").write_bytes(report_src.read_bytes())

        if exit_code != 0:
            return

    def _finalize_success(self, *, paths: JobPaths) -> None:
        state = load_state(paths.state_json)
        state["status"] = "succeeded"
        state["finished_at"] = now_iso()
        state["expires_at"] = iso_after_days(7)
        artifacts = state.get("artifacts") or {}
        artifacts["main_cpp"] = (paths.output_dir / "main.cpp").exists()
        artifacts["solution_json"] = (paths.output_dir / "solution.json").exists()
        artifacts["report_json"] = (paths.output_dir / "report.json").exists()
        state["artifacts"] = artifacts
        state["error"] = None
        save_state(paths.state_json, state)

    def _scan_for_secret(self, *, paths: JobPaths, secret: str) -> None:
        if not secret:
            return
        for file_path in (paths.output_dir / "main.cpp", paths.output_dir / "solution.json", paths.output_dir / "report.json"):
            if not file_path.exists():
                continue
            data = file_path.read_text(encoding="utf-8", errors="ignore")
            if secret in data:
                file_path.write_text(data.replace(secret, "***"), encoding="utf-8")
                raise RuntimeError("secret_leak_detected")
