from __future__ import annotations

import json
from pathlib import Path


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
