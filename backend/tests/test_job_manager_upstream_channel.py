from __future__ import annotations

import json
from pathlib import Path


class _FakeContainer:
    def __init__(self):
        self.id = "fake-container-id"
        self.name = "fake-container-name"
        self.started = False

    def start(self):
        self.started = True

    def wait(self):
        return {"StatusCode": 0}


def test_run_generate_routes_upstream_by_model_channel(client, monkeypatch, tmp_path):
    from backend.app.db import SessionLocal  # noqa: WPS433
    from backend.app.models import ModelPricing, UpstreamChannel  # noqa: WPS433
    from backend.app.services import job_manager as job_manager_module  # noqa: WPS433
    from backend.app.services.job_paths import get_job_paths  # noqa: WPS433
    from backend.app.services.job_state import now_iso, save_state  # noqa: WPS433
    from backend.app.settings import SETTINGS  # noqa: WPS433

    model = "model-route-channel"
    monkeypatch.setattr(SETTINGS, "runner_executor", "docker")
    with SessionLocal() as db:
        row = db.get(ModelPricing, model)
        if not row:
            row = ModelPricing(model=model)
        row.upstream_channel = "openai-cn"
        row.currency = "USD"
        row.is_active = True
        row.input_microusd_per_1m_tokens = 1
        row.cached_input_microusd_per_1m_tokens = 1
        row.output_microusd_per_1m_tokens = 1
        row.cached_output_microusd_per_1m_tokens = 1
        db.add(row)
        channel = db.get(UpstreamChannel, "openai-cn")
        if not channel:
            channel = UpstreamChannel(channel="openai-cn")
        channel.display_name = "openai-cn"
        channel.base_url = "https://cn.example.com/v1"
        channel.api_key = "sk-cn"
        channel.models_path = "/v1/models"
        channel.is_enabled = True
        db.add(channel)
        db.commit()

    monkeypatch.setattr(SETTINGS, "upstream_channels_json", "")

    captured: dict[str, object] = {}
    fake_container = _FakeContainer()

    def _fake_create_generate_container(**kwargs):
        captured["extra_env"] = kwargs["extra_env"]
        return fake_container

    def _fake_put_files(container, *, dest_dir: str, files: dict[str, bytes]):
        captured["dest_dir"] = dest_dir
        captured["auth_json"] = files["auth.json"]
        captured["config_toml"] = files["config.toml"]

    monkeypatch.setattr(job_manager_module, "docker_client", lambda: object())
    monkeypatch.setattr(job_manager_module, "create_generate_container", _fake_create_generate_container)
    monkeypatch.setattr(job_manager_module, "put_files", _fake_put_files)
    monkeypatch.setattr(job_manager_module, "start_log_collector", lambda **kwargs: None)

    jm = job_manager_module.JobManager(jobs_root=tmp_path)
    paths = get_job_paths(jobs_root=tmp_path, job_id="job-upstream-channel")
    paths.root.mkdir(parents=True, exist_ok=True)
    paths.output_dir.mkdir(parents=True, exist_ok=True)
    state = {
        "schema_version": "state.v1",
        "job_id": "job-upstream-channel",
        "owner_user_id": "u1",
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
            "max_terminal_log_bytes": 1024 * 1024,
        },
        "containers": {"generate": None, "test": None},
        "artifacts": {"main_cpp": False, "solution_json": False, "report_json": False},
        "error": None,
    }
    save_state(paths.state_json, state)

    jm._run_generate(paths=paths, owner_user_id="u1", attempt=1, prompt_mode="generate")

    extra_env = captured["extra_env"]
    assert isinstance(extra_env, dict)
    assert extra_env["OPENAI_BASE_URL"] == "https://cn.example.com/v1"
    assert captured["dest_dir"] == "/codex_home"
    auth_obj = json.loads(captured["auth_json"].decode("utf-8"))
    assert auth_obj["OPENAI_API_KEY"] == "sk-cn"
    assert isinstance(captured["config_toml"], (bytes, bytearray))

    new_state = json.loads(Path(paths.state_json).read_text(encoding="utf-8"))
    assert new_state["containers"]["generate"]["id"] == "fake-container-id"
    assert new_state["containers"]["generate"]["exit_code"] == 0
