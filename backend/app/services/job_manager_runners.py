from __future__ import annotations

# Execution helpers used by JobManager.
#
# These helpers are kept in a separate module to:
# - reduce job_manager.py file size and per-function complexity
# - isolate runner execution concerns (docker/local) from orchestration

import pathlib
import typing

from . import docker_service, job_state, local_runner
from ..settings import SETTINGS
from .job_manager_plans import GenerateRunnerPlan, TestRunnerPlan
from .job_paths import JobPaths


def run_generate_docker(
    *,
    client: typing.Any,
    paths: JobPaths,
    owner_user_id: str,
    plan: GenerateRunnerPlan,
    state: dict[str, typing.Any],
) -> int:
    # Run generation in a Docker container and stream logs to terminal.log.
    if client is None:
        raise RuntimeError("docker_unavailable")

    from . import job_manager as job_manager_module  # noqa: WPS433

    container = job_manager_module.create_generate_container(
        client=client,
        job=docker_service.ContainerJob(
            job_id=paths.root.name,
            owner_user_id=owner_user_id,
            attempt=plan.attempt,
            job_dir=paths.root,
        ),
        resources=docker_service.ContainerResources(
            cpus=plan.limits.cpus,
            memory_mb=plan.limits.memory_mb,
            pids_limit=plan.limits.pids_limit,
        ),
        extra_env=plan.extra_env,
    )

    state.setdefault("containers", {})
    state["containers"]["generate"] = {
        "id": container.id,
        "name": container.name,
        "exit_code": None,
        "attempt": plan.attempt,
    }
    job_state.save_state(paths.state_json, state)

    job_manager_module.put_files(
        container,
        dest_dir="/codex_home",
        files={
            "config.toml": plan.effective_config_toml.encode("utf-8"),
            "auth.json": plan.auth_bytes,
        },
    )

    job_manager_module.start_log_collector(
        container=container,
        log_path=paths.terminal_log,
        max_bytes=plan.limits.max_terminal_log_bytes,
        redact_secrets=[plan.secret],
    )
    container.start()
    wait_result = container.wait()
    return int(wait_result.get("StatusCode") or 0)


def run_generate_local(
    *,
    paths: JobPaths,
    plan: GenerateRunnerPlan,
    state: dict[str, typing.Any],
    resolve_runner_path: typing.Callable[[str], pathlib.Path],
    on_started: typing.Callable[[typing.Any], None],
    on_finished: typing.Callable[[], None],
) -> int:
    # Run generation as a local subprocess and record pid into state.json.
    script_path = resolve_runner_path(SETTINGS.runner_generate_script)
    schema_path = resolve_runner_path(SETTINGS.runner_schema_path)
    codex_home = paths.root / ".codex_home"
    codex_home.mkdir(parents=True, exist_ok=True)
    (codex_home / "config.toml").write_text(plan.effective_config_toml, encoding="utf-8")
    (codex_home / "auth.json").write_bytes(plan.auth_bytes)

    state.setdefault("containers", {})
    state["containers"]["generate"] = {
        "id": f"local-generate-attempt-{plan.attempt}",
        "name": script_path.name,
        "exit_code": None,
        "attempt": plan.attempt,
    }
    job_state.save_state(paths.state_json, state)

    local_env = {
        **plan.extra_env,
        "CODEX_HOME": str(codex_home.resolve()),
        "REALMOI_JOB_DIR": str(paths.root.resolve()),
        "REALMOI_SCHEMA_PATH": str(schema_path.resolve()),
    }
    exit_code, pid = local_runner.run_local_runner(
        config=local_runner.LocalRunnerConfig(
            script_path=script_path.resolve(),
            env=local_env,
            log_path=paths.terminal_log,
            max_bytes=plan.limits.max_terminal_log_bytes,
            redact_secrets=[plan.secret],
            callbacks=local_runner.LocalRunnerCallbacks(on_started=on_started, on_finished=on_finished),
        )
    )
    state = job_state.load_state(paths.state_json)
    state["containers"]["generate"]["id"] = f"local-generate-pid-{pid}"
    job_state.save_state(paths.state_json, state)
    return int(exit_code)


def run_test_docker(
    *,
    client: typing.Any,
    paths: JobPaths,
    owner_user_id: str,
    plan: TestRunnerPlan,
    state: dict[str, typing.Any],
) -> int:
    # Run tests in a Docker container and stream logs to terminal.log.
    if client is None:
        raise RuntimeError("docker_unavailable")

    container = docker_service.create_test_container(
        client=client,
        job=docker_service.ContainerJob(
            job_id=paths.root.name,
            owner_user_id=owner_user_id,
            attempt=plan.attempt,
            job_dir=paths.root,
        ),
        resources=docker_service.ContainerResources(
            cpus=plan.limits.cpus,
            memory_mb=plan.limits.memory_mb,
            pids_limit=plan.limits.pids_limit,
        ),
        extra_env=plan.extra_env,
    )

    state.setdefault("containers", {})
    state["containers"]["test"] = {
        "id": container.id,
        "name": container.name,
        "exit_code": None,
        "attempt": plan.attempt,
    }
    job_state.save_state(paths.state_json, state)

    docker_service.start_log_collector(
        container=container,
        log_path=paths.terminal_log,
        max_bytes=plan.limits.max_terminal_log_bytes,
        redact_secrets=[],
    )
    container.start()
    wait_result = container.wait()
    return int(wait_result.get("StatusCode") or 0)


def run_test_local(
    *,
    paths: JobPaths,
    plan: TestRunnerPlan,
    state: dict[str, typing.Any],
    resolve_runner_path: typing.Callable[[str], pathlib.Path],
    on_started: typing.Callable[[typing.Any], None],
    on_finished: typing.Callable[[], None],
) -> int:
    # Run tests as a local subprocess and record pid into state.json.
    script_path = resolve_runner_path(SETTINGS.runner_test_script)
    state.setdefault("containers", {})
    state["containers"]["test"] = {
        "id": f"local-test-attempt-{plan.attempt}",
        "name": script_path.name,
        "exit_code": None,
        "attempt": plan.attempt,
    }
    job_state.save_state(paths.state_json, state)

    local_env = {
        **plan.extra_env,
        "REALMOI_JOB_DIR": str(paths.root.resolve()),
        "REALMOI_WORK_DIR": str((paths.root / ".tmp_work").resolve()),
    }
    exit_code, pid = local_runner.run_local_runner(
        config=local_runner.LocalRunnerConfig(
            script_path=script_path.resolve(),
            env=local_env,
            log_path=paths.terminal_log,
            max_bytes=plan.limits.max_terminal_log_bytes,
            redact_secrets=[],
            callbacks=local_runner.LocalRunnerCallbacks(on_started=on_started, on_finished=on_finished),
        )
    )
    state = job_state.load_state(paths.state_json)
    state["containers"]["test"]["id"] = f"local-test-pid-{pid}"
    job_state.save_state(paths.state_json, state)
    return int(exit_code)
