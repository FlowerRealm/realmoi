from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time


def _write_job_and_state(*, jobs_root: Path, job_id: str, owner_user_id: str, model: str) -> Path:
    from backend.app.services.job_paths import get_job_paths  # noqa: WPS433
    from backend.app.services.job_state import now_iso, save_state  # noqa: WPS433

    paths = get_job_paths(jobs_root=jobs_root, job_id=job_id)
    paths.root.mkdir(parents=True, exist_ok=True)
    paths.input_dir.mkdir(parents=True, exist_ok=True)
    paths.output_dir.mkdir(parents=True, exist_ok=True)
    paths.logs_dir.mkdir(parents=True, exist_ok=True)

    job_obj = {
        "schema_version": "job.v1",
        "job_id": job_id,
        "owner_user_id": owner_user_id,
        "language": "cpp",
        "model": model,
        "problem": {"statement_md": "# A"},
        "seed": {"current_code_cpp": ""},
        "search_mode": "disabled",
        "reasoning_effort": "medium",
        "limits": {
            "time_limit_ms": 2000,
            "memory_limit_mb": 256,
            "cpus": 1,
            "pids_limit": 128,
            "max_output_bytes_per_test": 1_048_576,
            "max_terminal_log_bytes": 1_048_576,
        },
        "tests": {
            "dir": "tests",
            "present": False,
            "format": "auto",
            "compare": {"mode": "tokens"},
            "run_if_no_expected": True,
        },
    }
    paths.job_json.write_text(json.dumps(job_obj, ensure_ascii=False) + "\n", encoding="utf-8")

    state = {
        "schema_version": "state.v1",
        "job_id": job_id,
        "owner_user_id": owner_user_id,
        "status": "created",
        "created_at": now_iso(),
        "started_at": None,
        "finished_at": None,
        "expires_at": None,
        "model": model,
        "resource_limits": {
            "cpus": 1.0,
            "memory_limit_mb": 256,
            "pids_limit": 128,
            "max_terminal_log_bytes": 1_048_576,
        },
        "containers": {"generate": None, "test": None},
        "artifacts": {"main_cpp": False, "solution_json": False, "report_json": False},
        "error": None,
    }
    save_state(paths.state_json, state)
    return paths.root


def test_local_generate_and_test_success(client, monkeypatch, tmp_path):  # noqa: ARG001
    from backend.app.services import job_manager as job_manager_module  # noqa: WPS433
    from backend.app.services.job_paths import get_job_paths  # noqa: WPS433
    from backend.app.settings import SETTINGS  # noqa: WPS433

    monkeypatch.setattr(SETTINGS, "runner_executor", "local")
    monkeypatch.setattr(SETTINGS, "mock_mode", True)

    job_id = "job-local-success"
    _write_job_and_state(jobs_root=tmp_path, job_id=job_id, owner_user_id="u1", model="gpt-local")

    jm = job_manager_module.JobManager(jobs_root=tmp_path)
    paths = get_job_paths(jobs_root=tmp_path, job_id=job_id)

    jm._run_generate(paths=paths, owner_user_id="u1", attempt=1, prompt_mode="generate")
    jm._run_test(paths=paths, owner_user_id="u1", attempt=1)

    state = json.loads(paths.state_json.read_text(encoding="utf-8"))
    assert str(state["containers"]["generate"]["id"]).startswith("local-generate-pid-")
    assert str(state["containers"]["test"]["id"]).startswith("local-test-pid-")
    assert state["containers"]["generate"]["exit_code"] == 0
    assert state["containers"]["test"]["exit_code"] == 0
    assert (paths.output_dir / "main.cpp").exists()
    assert (paths.output_dir / "report.json").exists()


def test_reconcile_marks_running_local_jobs_failed(client, monkeypatch, tmp_path):  # noqa: ARG001
    from backend.app.services import job_manager as job_manager_module  # noqa: WPS433
    from backend.app.services.job_paths import get_job_paths  # noqa: WPS433
    from backend.app.services.job_state import load_state, save_state  # noqa: WPS433
    from backend.app.settings import SETTINGS  # noqa: WPS433

    monkeypatch.setattr(SETTINGS, "runner_executor", "local")
    monkeypatch.setattr(SETTINGS, "judge_mode", "embedded")
    monkeypatch.setattr(SETTINGS, "mock_mode", True)

    job_id = "job-local-reconcile"
    _write_job_and_state(jobs_root=tmp_path, job_id=job_id, owner_user_id="u1", model="gpt-local")
    paths = get_job_paths(jobs_root=tmp_path, job_id=job_id)
    state = load_state(paths.state_json)
    state["status"] = "running_generate"
    state["containers"]["generate"] = {"id": "local-generate-pid-999", "name": "runner_generate.py", "exit_code": None}
    save_state(paths.state_json, state)

    jm = job_manager_module.JobManager(jobs_root=tmp_path)
    jm.reconcile()

    state = load_state(paths.state_json)
    assert state["status"] == "failed"
    assert state["error"]["code"] == "local_process_missing"


def test_local_generate_raises_when_runner_returns_non_zero(client, monkeypatch, tmp_path):  # noqa: ARG001
    from backend.app.services import job_manager as job_manager_module  # noqa: WPS433
    from backend.app.services.job_paths import get_job_paths  # noqa: WPS433
    from backend.app.settings import SETTINGS  # noqa: WPS433

    monkeypatch.setattr(SETTINGS, "runner_executor", "local")
    monkeypatch.setattr(SETTINGS, "mock_mode", True)
    monkeypatch.setattr(SETTINGS, "runner_generate_script", "runner/app/runner_test.py")

    job_id = "job-local-generate-fail"
    _write_job_and_state(jobs_root=tmp_path, job_id=job_id, owner_user_id="u1", model="gpt-local")

    jm = job_manager_module.JobManager(jobs_root=tmp_path)
    paths = get_job_paths(jobs_root=tmp_path, job_id=job_id)

    try:
        jm._run_generate(paths=paths, owner_user_id="u1", attempt=1, prompt_mode="generate")
    except RuntimeError as e:
        assert str(e) == "generate_failed"
    else:
        raise AssertionError("expected generate_failed")


def test_start_job_queues_when_independent_mode(client, monkeypatch, tmp_path):  # noqa: ARG001
    from backend.app.services import job_manager as job_manager_module  # noqa: WPS433
    from backend.app.services.job_paths import get_job_paths  # noqa: WPS433
    from backend.app.services.job_state import load_state  # noqa: WPS433
    from backend.app.settings import SETTINGS  # noqa: WPS433

    monkeypatch.setattr(SETTINGS, "runner_executor", "local")
    monkeypatch.setattr(SETTINGS, "judge_mode", "independent")

    job_id = "job-queued-mode"
    _write_job_and_state(jobs_root=tmp_path, job_id=job_id, owner_user_id="u1", model="gpt-local")
    jm = job_manager_module.JobManager(jobs_root=tmp_path)

    state = jm.start_job(job_id=job_id, owner_user_id="u1")
    saved = load_state(get_job_paths(jobs_root=tmp_path, job_id=job_id).state_json)

    assert state["status"] == "queued"
    assert saved["status"] == "queued"
    assert jm._threads == {}


def test_independent_judge_claim_and_release_lock(client, monkeypatch, tmp_path):  # noqa: ARG001
    from backend.app.services import job_manager as job_manager_module  # noqa: WPS433
    from backend.app.services.job_paths import get_job_paths  # noqa: WPS433
    from backend.app.services.job_state import load_state, save_state  # noqa: WPS433
    from backend.app.settings import SETTINGS  # noqa: WPS433

    monkeypatch.setattr(SETTINGS, "runner_executor", "local")
    monkeypatch.setattr(SETTINGS, "judge_mode", "independent")

    job_id = "job-claim-once"
    _write_job_and_state(jobs_root=tmp_path, job_id=job_id, owner_user_id="u1", model="gpt-local")
    jm = job_manager_module.JobManager(jobs_root=tmp_path)
    jm.start_job(job_id=job_id, owner_user_id="u1")

    claimed = jm.claim_next_queued_job(machine_id="judge-a")
    assert claimed is not None
    assert claimed["job_id"] == job_id
    assert Path(claimed["lock_path"]).exists()
    assert str(claimed.get("claim_id") or "")

    def _fake_run_job_thread(*, job_id: str, owner_user_id: str) -> None:  # noqa: ARG001
        paths = get_job_paths(jobs_root=tmp_path, job_id=job_id)
        state = load_state(paths.state_json)
        state["status"] = "succeeded"
        save_state(paths.state_json, state)

    monkeypatch.setattr(jm, "_run_job_thread", _fake_run_job_thread)
    jm.run_claimed_job(job_id=claimed["job_id"], owner_user_id=claimed["owner_user_id"])
    assert jm.release_judge_claim(job_id=claimed["job_id"], claim_id=str(claimed["claim_id"])) is True

    assert not Path(claimed["lock_path"]).exists()
    state = load_state(get_job_paths(jobs_root=tmp_path, job_id=job_id).state_json)
    assert state["status"] == "succeeded"


def test_reconcile_keeps_running_local_jobs_in_independent_mode(client, monkeypatch, tmp_path):  # noqa: ARG001
    from backend.app.services import job_manager as job_manager_module  # noqa: WPS433
    from backend.app.services.job_paths import get_job_paths  # noqa: WPS433
    from backend.app.services.job_state import load_state, save_state  # noqa: WPS433
    from backend.app.settings import SETTINGS  # noqa: WPS433

    monkeypatch.setattr(SETTINGS, "runner_executor", "local")
    monkeypatch.setattr(SETTINGS, "judge_mode", "independent")
    monkeypatch.setattr(SETTINGS, "mock_mode", True)

    job_id = "job-local-reconcile-independent"
    _write_job_and_state(jobs_root=tmp_path, job_id=job_id, owner_user_id="u1", model="gpt-local")
    paths = get_job_paths(jobs_root=tmp_path, job_id=job_id)
    state = load_state(paths.state_json)
    state["status"] = "running_generate"
    state["containers"]["generate"] = {"id": "local-generate-pid-999", "name": "runner_generate.py", "exit_code": None}
    save_state(paths.state_json, state)

    jm = job_manager_module.JobManager(jobs_root=tmp_path)
    jm.reconcile()

    state = load_state(paths.state_json)
    assert state["status"] == "running_generate"


def test_cancel_job_stops_local_pid_from_state(client, monkeypatch, tmp_path):  # noqa: ARG001
    from backend.app.services import job_manager as job_manager_module  # noqa: WPS433
    from backend.app.services.job_paths import get_job_paths  # noqa: WPS433
    from backend.app.services.job_state import load_state, save_state  # noqa: WPS433
    from backend.app.settings import SETTINGS  # noqa: WPS433

    monkeypatch.setattr(SETTINGS, "runner_executor", "local")
    monkeypatch.setattr(SETTINGS, "judge_mode", "independent")

    proc = subprocess.Popen(  # noqa: S603
        [sys.executable, "-c", "import time; time.sleep(30)"],
        preexec_fn=os.setsid,
    )
    try:
        job_id = "job-cancel-by-state-pid"
        _write_job_and_state(jobs_root=tmp_path, job_id=job_id, owner_user_id="u1", model="gpt-local")
        paths = get_job_paths(jobs_root=tmp_path, job_id=job_id)
        state = load_state(paths.state_json)
        state["status"] = "running_generate"
        state["containers"]["generate"] = {
            "id": f"local-generate-pid-{proc.pid}",
            "name": "runner_generate.py",
            "exit_code": None,
        }
        save_state(paths.state_json, state)

        jm = job_manager_module.JobManager(jobs_root=tmp_path)
        new_state = jm.cancel_job(job_id=job_id)
        assert new_state["status"] == "cancelled"

        deadline = time.time() + 2.0
        while proc.poll() is None and time.time() < deadline:
            time.sleep(0.05)
        assert proc.poll() is not None
    finally:
        if proc.poll() is None:
            proc.kill()


def test_generate_bundle_provider_avoids_db_access(client, monkeypatch, tmp_path):  # noqa: ARG001
    from backend.app.services import job_manager as job_manager_module  # noqa: WPS433
    from backend.app.services.job_paths import get_job_paths  # noqa: WPS433
    from backend.app.settings import SETTINGS  # noqa: WPS433

    monkeypatch.setattr(SETTINGS, "runner_executor", "local")
    monkeypatch.setattr(SETTINGS, "mock_mode", True)

    job_id = "job-local-bundle-provider"
    _write_job_and_state(jobs_root=tmp_path, job_id=job_id, owner_user_id="u1", model="gpt-local")
    paths = get_job_paths(jobs_root=tmp_path, job_id=job_id)

    class _BoomSessionLocal:  # noqa: WPS431
        def __call__(self, *args, **kwargs):  # noqa: ARG002
            raise AssertionError("SessionLocal should not be used when provider is set")

    monkeypatch.setattr(job_manager_module, "SessionLocal", _BoomSessionLocal())

    cfg = job_manager_module.build_effective_config(user_overrides_toml="")
    bundle = job_manager_module.GenerateBundle(
        effective_config_toml=cfg.effective_config_toml,
        auth_json_bytes=b"{}\n",
        openai_base_url="https://example.com",
        mock_mode=True,
    )

    def _provider(**kwargs):  # noqa: ARG001
        return bundle

    def _usage_reporter(**kwargs):  # noqa: ARG001
        return

    jm = job_manager_module.JobManager(
        jobs_root=tmp_path,
        generate_bundle_provider=_provider,
        usage_reporter=_usage_reporter,
    )

    jm._run_generate(paths=paths, owner_user_id="u1", attempt=1, prompt_mode="generate")
    state = json.loads(paths.state_json.read_text(encoding="utf-8"))
    assert state["containers"]["generate"]["exit_code"] == 0
