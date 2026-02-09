from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="REALMOI_", extra="ignore")

    # Dev / Testing
    mock_mode: bool = False

    # Paths
    db_path: str = "data/realmoi.db"
    jobs_root: str = "jobs"
    codex_auth_json_path: str = "data/secrets/codex/auth.json"

    # Upstream
    openai_base_url: str = "https://api.openai.com"
    openai_api_key: str | None = None
    upstream_models_path: str = "/v1/models"
    # Optional multi-channel upstream settings in JSON.
    # Example:
    # {"openai-cn":{"base_url":"https://api.openai.com/v1","api_key":"sk-xxx","models_path":"/v1/models"}}
    upstream_channels_json: str = ""

    # Auth
    jwt_secret: str = Field(default="dev-secret-change-me")
    jwt_ttl_seconds: int = 86400
    allow_signup: bool = True
    admin_username: str | None = None
    admin_password: str | None = None

    # Runner / Docker
    runner_executor: Literal["local", "docker"] = "local"
    runner_image: str = "realmoi/realmoi-runner:latest"
    runner_generate_script: str = "runner/app/runner_generate.py"
    runner_test_script: str = "runner/app/runner_test.py"
    runner_schema_path: str = "runner/schemas/codex_output_schema.json"
    runner_codex_transport: Literal["appserver", "exec", "auto"] = "appserver"
    docker_api_timeout_seconds: int = 120
    judge_mode: Literal["embedded", "independent"] = "embedded"
    judge_machine_id: str = ""
    judge_poll_interval_ms: int = 1000
    judge_lock_stale_seconds: int = 120
    judge_api_base_url: str = ""
    judge_self_test_timeout_seconds: int = 90

    # Resource limits (server clamps user input to these)
    max_cpus: float = 2.0
    max_memory_mb: int = 2048
    max_pids: int = 512
    default_cpus: float = 1.0
    default_memory_mb: int = 1024
    default_pids: int = 256

    default_time_limit_ms: int = 2000
    max_time_limit_ms: int = 15000

    # Output limits
    default_max_output_bytes_per_test: int = 1_048_576  # 1MB
    max_max_output_bytes_per_test: int = 8_388_608  # 8MB
    default_max_terminal_log_bytes: int = 5_242_880  # 5MB
    max_max_terminal_log_bytes: int = 52_428_800  # 50MB

    # tests.zip safety
    tests_max_files: int = 2000
    tests_max_uncompressed_bytes: int = 512 * 1024 * 1024  # 512MB
    tests_max_single_file_bytes: int = 64 * 1024 * 1024  # 64MB
    tests_max_depth: int = 8

    # Search
    default_search_mode: Literal["disabled", "cached", "live"] = "cached"

    # Retries
    quality_max_retries: int = 2  # total attempts = 1 + quality_max_retries

    # Codex user settings
    codex_user_allowed_keys: tuple[str, ...] = (
        "model_reasoning_effort",
        "model_reasoning_summary",
        "model_verbosity",
        "hide_agent_reasoning",
        "show_raw_agent_reasoning",
    )

    def ensure_dirs(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        Path(self.jobs_root).mkdir(parents=True, exist_ok=True)
        Path(self.codex_auth_json_path).parent.mkdir(parents=True, exist_ok=True)


SETTINGS = Settings()
