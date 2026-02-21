from __future__ import annotations

# Shared plan/value objects for JobManager + judge workers.
#
# Keeping these dataclasses in a dedicated module reduces the size/complexity of
# job_manager.py and makes it easier to reuse types without circular imports.

import collections.abc
import dataclasses


@dataclasses.dataclass(frozen=True)
class GenerateBundle:
    # Inputs required to invoke the generate runner.
    effective_config_toml: str
    auth_json_bytes: bytes
    openai_base_url: str
    mock_mode: bool = False


GenerateBundleProvider = collections.abc.Callable[..., GenerateBundle]
UsageReporter = collections.abc.Callable[..., None]


@dataclasses.dataclass(frozen=True)
class ResourceLimits:
    # Resource limits for runner execution.
    cpus: float
    memory_mb: int
    pids_limit: int
    max_terminal_log_bytes: int


@dataclasses.dataclass(frozen=True)
class GenerateRunnerPlan:
    # Resolved inputs for a generation attempt.
    attempt: int
    prompt_mode: str
    extra_env: dict[str, str]
    effective_config_toml: str
    auth_bytes: bytes
    secret: str
    limits: ResourceLimits


@dataclasses.dataclass(frozen=True)
class TestRunnerPlan:
    # Resolved inputs for a test attempt.
    attempt: int
    extra_env: dict[str, str]
    limits: ResourceLimits

