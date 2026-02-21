from __future__ import annotations

# Job lifecycle orchestration.
#
# This module coordinates generation + testing jobs and updates the on-disk
# `state.json` that the UI reads. There are two execution dimensions:
#
# - Runner executor: local subprocesses or Docker containers.
# - Judge mode:
#   - embedded: backend runs generate/test immediately when a job is started
#   - independent: external judge workers claim queued jobs via a lock file
#
# The implementation is intentionally best-effort: state updates should not
# crash the backend, and cancellation should attempt to stop external processes.

import collections.abc
import os
import pathlib
import signal
import subprocess
import threading
import typing
from dataclasses import dataclass

from .. import db as db_module, models as models_module
from ..services import (
    codex_config,
    docker_service,
    job_paths,
    job_state,
    upstream_channels,
    usage_records,
)
from ..settings import SETTINGS
from . import job_manager_runners
from . import job_manager_utils
from . import job_manager_claims
from . import job_manager_execution
from . import job_manager_reconcile
from .job_manager_plans import (
    GenerateBundle,
    GenerateBundleProvider,
    GenerateRunnerPlan,
    ResourceLimits,
    TestRunnerPlan,
    UsageReporter,
)

def docker_client() -> typing.Any:
    """Return a Docker client instance.

    This thin wrapper exists to keep test monkeypatch hooks stable while the
    implementation lives in docker_service.
    """

    return docker_service.docker_client()


def create_generate_container(**kwargs: typing.Any) -> typing.Any:
    """Create the generate container via docker_service (test-patchable)."""

    return docker_service.create_generate_container(**kwargs)


def put_files(container: typing.Any, *, dest_dir: str, files: dict[str, bytes]) -> None:
    """Copy files into the container via docker_service (test-patchable)."""

    docker_service.put_files(container, dest_dir=dest_dir, files=files)


def start_log_collector(**kwargs: typing.Any) -> None:
    """Start log collection via docker_service (test-patchable)."""

    docker_service.start_log_collector(**kwargs)


@dataclass(frozen=True)
class GenerateBundleRequest:
    owner_user_id: str
    state: dict[str, typing.Any]
    attempt: int
    prompt_mode: str


@dataclass(frozen=True)
class GeneratePlanRequest:
    paths: job_paths.JobPaths
    owner_user_id: str
    attempt: int
    prompt_mode: str
    state: dict[str, typing.Any]


class JobManager:
    # Manage job state and run generation/testing through the configured executor.
    def __init__(
        self,
        *,
        jobs_root: pathlib.Path,
        generate_bundle_provider: GenerateBundleProvider | None = None,
        usage_reporter: UsageReporter | None = None,
    ):
        self._jobs_root = jobs_root
        executor = str(SETTINGS.runner_executor or "local").strip().lower()
        self._runner_executor = executor if executor in {"local", "docker"} else "local"
        mode = str(SETTINGS.judge_mode or "embedded").strip().lower()
        self._judge_mode = mode if mode in {"embedded", "independent"} else "embedded"
        self._judge_lock_stale_seconds = max(30, int(SETTINGS.judge_lock_stale_seconds or 120))
        if self._runner_executor == "docker":
            self._client = docker_client()
        else:
            self._client = None
        self._generate_bundle_provider = generate_bundle_provider
        self._usage_reporter = usage_reporter
        self._lock = threading.Lock()
        self._threads: dict[str, threading.Thread] = {}
        self._local_procs: dict[str, dict[str, subprocess.Popen[bytes]]] = {}

    def reconcile(self) -> None:
        reconcile_kwargs = {
            "jobs_root": self._jobs_root,
            "runner_executor": self._runner_executor,
            "judge_mode": self._judge_mode,
            "docker_client": self._client,
        }
        job_manager_reconcile.reconcile_jobs(**reconcile_kwargs)

    def start_job(self, *, job_id: str, owner_user_id: str) -> dict[str, typing.Any]:
        # Start a job.
        #
        # In independent judge mode, "start" only enqueues; the judge worker will
        # claim + run it later.

        paths = job_paths.get_job_paths(jobs_root=self._jobs_root, job_id=job_id)
        if not paths.state_json.exists():
            raise FileNotFoundError(job_id)

        with self._lock:
            state = job_state.load_state(paths.state_json)
            status = state.get("status")
            if status in ("queued", "running_generate", "running_test"):
                return state
            if status in ("succeeded", "failed", "cancelled"):
                raise RuntimeError("already_finished")

            state["status"] = "queued" if self._judge_mode == "independent" else "running_generate"
            state["started_at"] = state.get("started_at") or job_state.now_iso()
            state["error"] = None
            job_state.save_state(paths.state_json, state)

            if self._judge_mode == "independent":
                return state

            t = threading.Thread(
                target=self.run_job_thread,
                kwargs={"job_id": job_id, "owner_user_id": owner_user_id},
                daemon=True,
            )
            self._threads[job_id] = t
            t.start()
            return state

    def claim_next_queued_job(self, *, machine_id: str) -> dict[str, str] | None:
        claim_kwargs = {
            "jobs_root": self._jobs_root,
            "machine_id": machine_id,
            "stale_seconds": self._judge_lock_stale_seconds,
        }
        claimed = job_manager_claims.claim_next_queued_job(**claim_kwargs)
        return claimed

    def run_claimed_job(self, *, job_id: str, owner_user_id: str) -> None:
        # Run claimed job inline.

        self.run_job_thread(job_id=job_id, owner_user_id=owner_user_id)

    def release_judge_claim(self, *, job_id: str, claim_id: str) -> bool:
        return job_manager_claims.release_judge_claim(
            jobs_root=self._jobs_root,
            job_id=job_id,
            claim_id=claim_id,
        )

    def cancel_job(self, *, job_id: str) -> dict[str, typing.Any]:
        # Cancel a job and attempt to stop its runner process/container.

        paths = job_paths.get_job_paths(jobs_root=self._jobs_root, job_id=job_id)
        if not paths.state_json.exists():
            raise FileNotFoundError(job_id)

        with self._lock:
            state = job_state.load_state(paths.state_json)
            status = state.get("status")
            if status in ("cancelled", "succeeded", "failed"):
                return state

            self.stop_job_execution(job_id=job_id, state=state)
            self.mark_state_cancelled(state=state)
            job_state.save_state(paths.state_json, state)
            return state

    def mark_state_cancelled(self, *, state: dict[str, typing.Any]) -> None:
        state["status"] = "cancelled"
        state["finished_at"] = job_state.now_iso()
        state["expires_at"] = job_state.iso_after_days(7)
        state["error"] = {"code": "cancelled", "message": "Cancelled"}

    def stop_job_execution(self, *, job_id: str, state: dict[str, typing.Any]) -> None:
        if self._runner_executor == "docker":
            self.stop_docker_stage_containers(state=state)
            return

        stage_procs = self._local_procs.pop(job_id, {})
        for proc in stage_procs.values():
            local_runner.stop_process_tree(proc)
        if not stage_procs:
            self.stop_local_pid_from_state(state=state)

    def stop_docker_stage_containers(self, *, state: dict[str, typing.Any]) -> None:
        for stage in ("generate", "test"):
            cinfo = (state.get("containers") or {}).get(stage) or {}
            cid = cinfo.get("id")
            if not cid or self._client is None:
                continue
            try:
                c = self._client.containers.get(cid)
                c.stop(timeout=3)
            except Exception as exc:
                # Best-effort cancellation.
                _ = exc

    def try_claim_job(self, *, job_id: str, machine_id: str) -> dict[str, str] | None:
        return job_manager_claims.try_claim_job(
            jobs_root=self._jobs_root,
            job_id=job_id,
            machine_id=machine_id,
            stale_seconds=self._judge_lock_stale_seconds,
        )

    def parse_local_pid(self, *, stage: str, container_id: str) -> int | None:
        prefix = f"local-{stage}-pid-"
        if not container_id.startswith(prefix):
            return None
        pid_str = container_id.removeprefix(prefix)
        if not pid_str.isdigit():
            return None
        pid = int(pid_str)
        return pid if pid > 0 else None

    def stop_local_pid_from_state(self, *, state: dict[str, typing.Any]) -> None:
        # Stop a local runner process recorded in state.json, if present.

        # Attempt to stop any local runner process recorded into state.json after a restart.
        containers = state.get("containers") or {}
        for stage in ("generate", "test"):
            cinfo = containers.get(stage) or {}
            raw_id = str(cinfo.get("id") or "")
            pid = self.parse_local_pid(stage=stage, container_id=raw_id)
            if pid is None:
                continue
            try:
                # Prefer process-group kill; fallback to direct pid.
                os.killpg(os.getpgid(pid), signal.SIGTERM)
            except Exception as exc:
                _ = exc
                try:
                    os.kill(pid, signal.SIGTERM)
                except Exception as exc2:
                    _ = exc2
                    continue

    def project_root(self) -> pathlib.Path:
        # Resolve repository root from this module location.

        return pathlib.Path(__file__).resolve().parents[3]

    def resolve_runner_path(self, configured_path: str) -> pathlib.Path:
        # Resolve a configured runner script path (absolute or repo-relative).

        path = pathlib.Path(configured_path)
        if path.is_absolute():
            return path
        return self.project_root() / path

    def remember_local_process(self, *, job_id: str, stage: str, process: subprocess.Popen[bytes]) -> None:
        with self._lock:
            stage_map = self._local_procs.setdefault(job_id, {})
            stage_map[stage] = process

    def forget_local_process(self, *, job_id: str, stage: str) -> None:
        with self._lock:
            stage_map = self._local_procs.get(job_id) or {}
            stage_map.pop(stage, None)
            if not stage_map:
                self._local_procs.pop(job_id, None)

    def run_job_thread(self, *, job_id: str, owner_user_id: str) -> None:
        job_manager_execution.run_job_attempts(
            manager=self,
            jobs_root=self._jobs_root,
            job_id=job_id,
            owner_user_id=owner_user_id,
        )

    def get_generate_bundle(
        self,
        *,
        paths: job_paths.JobPaths,
        req: GenerateBundleRequest,
    ) -> GenerateBundle:
        # Resolve generation bundle either from injected provider or database.

        if self._generate_bundle_provider is not None:
            return self._generate_bundle_provider(
                job_id=paths.root.name,
                owner_user_id=req.owner_user_id,
                state=typing.cast(dict[str, typing.Any], req.state),
                attempt=req.attempt,
                prompt_mode=req.prompt_mode,
            )
        return job_manager_utils.prepare_generate_bundle_from_db(
            owner_user_id=req.owner_user_id,
            state=typing.cast(dict[str, typing.Any], req.state),
        )

    def run_generate_docker(
        self,
        *,
        paths: job_paths.JobPaths,
        owner_user_id: str,
        plan: GenerateRunnerPlan,
        state: dict[str, typing.Any],
    ) -> int:
        return job_manager_runners.run_generate_docker(
            client=self._client,
            paths=paths,
            owner_user_id=owner_user_id,
            plan=plan,
            state=state,
        )

    def run_generate_local(
        self,
        *,
        paths: job_paths.JobPaths,
        plan: GenerateRunnerPlan,
        state: dict[str, typing.Any],
    ) -> int:
        return job_manager_runners.run_generate_local(
            paths=paths,
            plan=plan,
            state=state,
            resolve_runner_path=self.resolve_runner_path,
            on_started=lambda proc: self.remember_local_process(job_id=paths.root.name, stage="generate", process=proc),
            on_finished=lambda: self.forget_local_process(job_id=paths.root.name, stage="generate"),
        )

    def run_test_docker(
        self,
        *,
        paths: job_paths.JobPaths,
        owner_user_id: str,
        plan: TestRunnerPlan,
        state: dict[str, typing.Any],
    ) -> int:
        run_kwargs = {
            "client": self._client,
            "paths": paths,
            "owner_user_id": owner_user_id,
            "plan": plan,
            "state": state,
        }
        return job_manager_runners.run_test_docker(**run_kwargs)

    def run_test_local(
        self,
        *,
        paths: job_paths.JobPaths,
        plan: TestRunnerPlan,
        state: dict[str, typing.Any],
    ) -> int:
        on_started = lambda proc: self.remember_local_process(job_id=paths.root.name, stage="test", process=proc)
        on_finished = lambda: self.forget_local_process(job_id=paths.root.name, stage="test")
        run_kwargs = {
            "paths": paths,
            "plan": plan,
            "state": state,
            "resolve_runner_path": self.resolve_runner_path,
            "on_started": on_started,
            "on_finished": on_finished,
        }
        return job_manager_runners.run_test_local(**run_kwargs)

    def set_job_status(self, *, paths: job_paths.JobPaths, status: str) -> dict[str, typing.Any]:
        """Persist job status to state.json and return the latest state dict."""

        state = job_state.load_state(paths.state_json)
        state["status"] = status
        job_state.save_state(paths.state_json, state)
        return typing.cast(dict[str, typing.Any], state)

    def save_stage_exit_code(self, *, paths: job_paths.JobPaths, stage: str, exit_code: int) -> None:
        """Update state.json with runner exit_code for a stage (generate/test)."""

        state = job_state.load_state(paths.state_json)
        state["containers"][stage]["exit_code"] = exit_code
        job_state.save_state(paths.state_json, state)

    def build_generate_plan(self, *, req: GeneratePlanRequest) -> GenerateRunnerPlan:
        limits = job_manager_utils.read_resource_limits(state=req.state)
        bundle = self.get_generate_bundle(
            paths=req.paths,
            req=GenerateBundleRequest(
                owner_user_id=req.owner_user_id,
                state=typing.cast(dict[str, typing.Any], req.state),
                attempt=req.attempt,
                prompt_mode=req.prompt_mode,
            ),
        )

        upstream_base_url = str(bundle.openai_base_url or "")
        auth_bytes = bundle.auth_json_bytes
        secret = job_manager_utils.parse_openai_api_key(auth_json_bytes=auth_bytes)
        effective_config_toml = bundle.effective_config_toml

        extra_env = {
            "ATTEMPT": str(req.attempt),
            "PROMPT_MODE": req.prompt_mode,
            "OPENAI_BASE_URL": upstream_base_url,
            "REALMOI_CODEX_TRANSPORT": str(SETTINGS.runner_codex_transport or "appserver"),
        }
        if SETTINGS.mock_mode or bundle.mock_mode:
            extra_env["MOCK_MODE"] = "1"

        return GenerateRunnerPlan(
            attempt=req.attempt,
            prompt_mode=req.prompt_mode,
            extra_env=extra_env,
            effective_config_toml=effective_config_toml,
            auth_bytes=auth_bytes,
            secret=secret,
            limits=limits,
        )

    def run_generate_plan(
        self,
        *,
        paths: job_paths.JobPaths,
        owner_user_id: str,
        plan: GenerateRunnerPlan,
        state: dict[str, typing.Any],
    ) -> int:
        if self._runner_executor == "docker":
            # Docker runner: start a container and collect terminal logs into `terminal.log`.
            return self.run_generate_docker(
                paths=paths,
                owner_user_id=owner_user_id,
                plan=plan,
                state=typing.cast(dict[str, typing.Any], state),
            )

        # Local runner: run the script directly and record the pid into state.json for cancellation.
        return self.run_generate_local(
            paths=paths,
            plan=plan,
            state=typing.cast(dict[str, typing.Any], state),
        )

    def run_generate(self, *, paths: job_paths.JobPaths, owner_user_id: str, attempt: int, prompt_mode: str) -> None:
        # Run the generation stage and update state.json with progress.

        state = self.set_job_status(paths=paths, status="running_generate")
        plan = self.build_generate_plan(
            req=GeneratePlanRequest(
                paths=paths,
                owner_user_id=owner_user_id,
                attempt=attempt,
                prompt_mode=prompt_mode,
                state=state,
            )
        )
        exit_code = self.run_generate_plan(
            paths=paths,
            owner_user_id=owner_user_id,
            plan=plan,
            state=state,
        )
        self.save_stage_exit_code(paths=paths, stage="generate", exit_code=exit_code)
        if exit_code != 0:
            raise RuntimeError("generate_failed")

        job_manager_utils.scan_for_secret(paths=paths, secret=plan.secret)
        if self._usage_reporter is not None:
            self._usage_reporter(
                job_id=paths.root.name,
                owner_user_id=owner_user_id,
                attempt=attempt,
                job_dir=paths.root,
            )
        else:
            usage_records.ingest_usage_record(
                job_id=paths.root.name,
                owner_user_id=owner_user_id,
                attempt=attempt,
                job_dir=paths.root,
            )

    def _run_generate(self, *, paths: job_paths.JobPaths, owner_user_id: str, attempt: int, prompt_mode: str) -> None:
        # Backwards-compatible alias for older tests.
        self.run_generate(paths=paths, owner_user_id=owner_user_id, attempt=attempt, prompt_mode=prompt_mode)

    def run_test(self, *, paths: job_paths.JobPaths, owner_user_id: str, attempt: int) -> None:
        # Run the test stage and persist report.json to output/ if present.

        state = job_state.load_state(paths.state_json)
        state["status"] = "running_test"
        job_state.save_state(paths.state_json, state)

        limits = job_manager_utils.read_resource_limits(state=state)
        plan = TestRunnerPlan(
            attempt=attempt,
            extra_env={"ATTEMPT": str(attempt)},
            limits=limits,
        )

        if self._runner_executor == "docker":
            # Docker runner: tests run in a separate container that mounts the job dir.
            exit_code = self.run_test_docker(
                paths=paths,
                owner_user_id=owner_user_id,
                plan=plan,
                state=typing.cast(dict[str, typing.Any], state),
            )
        else:
            # Local runner: execute the test script directly inside the backend environment.
            exit_code = self.run_test_local(
                paths=paths,
                plan=plan,
                state=typing.cast(dict[str, typing.Any], state),
            )

        state = job_state.load_state(paths.state_json)
        state["containers"]["test"]["exit_code"] = exit_code
        job_state.save_state(paths.state_json, state)

        attempt_dir = paths.output_dir / "artifacts" / f"attempt_{attempt}" / "test_output"
        report_src = attempt_dir / "report.json"
        if report_src.exists():
            (paths.output_dir / "report.json").write_bytes(report_src.read_bytes())

        if exit_code != 0:
            return

    def finalize_success(self, *, paths: job_paths.JobPaths) -> None:
        # Mark job as succeeded and update artifact flags.

        state = job_state.load_state(paths.state_json)
        state["status"] = "succeeded"
        state["finished_at"] = job_state.now_iso()
        state["expires_at"] = job_state.iso_after_days(7)
        artifacts = state.get("artifacts") or {}
        artifacts["main_cpp"] = (paths.output_dir / "main.cpp").exists()
        artifacts["solution_json"] = (paths.output_dir / "solution.json").exists()
        artifacts["report_json"] = (paths.output_dir / "report.json").exists()
        state["artifacts"] = artifacts
        state["error"] = None
        job_state.save_state(paths.state_json, state)
