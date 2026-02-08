from __future__ import annotations

import io
import tarfile
import threading
from dataclasses import dataclass
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any, Iterable

import os
import tempfile
import shutil

import docker
from docker.models.containers import Container
from docker.types import Ulimit

from ..settings import SETTINGS


@dataclass(frozen=True)
class ContainerRef:
    id: str
    name: str


def docker_client() -> docker.DockerClient:
    return docker.from_env(timeout=SETTINGS.docker_api_timeout_seconds)


def _make_tar(files: dict[str, bytes]) -> bytes:
    uid = os.getuid()
    gid = os.getgid()
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        for name, data in files.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            # Must be readable by the container user (we run as host uid:gid for /job write access).
            info.mode = 0o644
            info.uid = uid
            info.gid = gid
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def put_files(container: Container, *, dest_dir: str, files: dict[str, bytes]) -> None:
    tar_data = _make_tar(files)
    container.put_archive(dest_dir, tar_data)


def copy_from_container(container: Container, *, src_path: str, dest_dir: Path) -> None:
    """
    Copy a file or directory from container to host.

    This uses docker get_archive, which returns a tar stream.
    """

    stream, _stat = container.get_archive(src_path)
    tmp_dir = Path(tempfile.mkdtemp(prefix="realmoi-docker-cp-"))
    try:
        buf = io.BytesIO()
        for chunk in stream:
            buf.write(chunk)
        buf.seek(0)
        with tarfile.open(fileobj=buf, mode="r:*") as tf:
            for member in tf.getmembers():
                name = (member.name or "").strip()
                if not name:
                    continue
                p = PurePosixPath(name)
                if p.is_absolute() or ".." in p.parts:
                    raise ValueError("tar_slip")
                if member.issym() or member.islnk():
                    raise ValueError("symlink_not_allowed")

                target = tmp_dir.joinpath(*p.parts)
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                if not member.isreg():
                    # Ignore other file types.
                    continue

                target.parent.mkdir(parents=True, exist_ok=True)
                src = tf.extractfile(member)
                if src is None:
                    continue
                with src, target.open("wb") as out:
                    shutil.copyfileobj(src, out)

        # Docker archives usually contain a single top-level directory for dir copies.
        children = list(tmp_dir.iterdir())
        if len(children) == 1 and children[0].is_dir():
            src_root = children[0]
        else:
            src_root = tmp_dir

        dest_dir.mkdir(parents=True, exist_ok=True)
        for child in src_root.iterdir():
            target = dest_dir / child.name
            if target.exists():
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
            shutil.move(str(child), str(target))
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def start_log_collector(
    *,
    container: Container,
    log_path: Path,
    max_bytes: int,
    redact_secrets: list[str],
) -> threading.Thread:
    log_path.parent.mkdir(parents=True, exist_ok=True)

    def _redact(data: bytes) -> bytes:
        s = data
        for secret in redact_secrets:
            if secret:
                s = s.replace(secret.encode("utf-8"), b"***")
        return s

    def _run() -> None:
        written = 0
        with log_path.open("ab") as f:
            try:
                for chunk in container.logs(stream=True, follow=True):
                    if not isinstance(chunk, (bytes, bytearray)):
                        continue
                    chunk = _redact(bytes(chunk))
                    if written >= max_bytes:
                        continue
                    remaining = max_bytes - written
                    chunk = chunk[:remaining]
                    f.write(chunk)
                    f.flush()
                    written += len(chunk)
            except Exception:
                # Best effort.
                return

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t


def create_generate_container(
    *,
    client: docker.DockerClient,
    job_id: str,
    owner_user_id: str,
    attempt: int,
    job_dir: Path,
    cpus: float,
    memory_mb: int,
    pids_limit: int,
    extra_env: dict[str, str] | None = None,
) -> Container:
    name = f"realmoi_{job_id}_generate_a{attempt}"
    job_dir_abs = str(job_dir.resolve())
    user = f"{os.getuid()}:{os.getgid()}"
    env = {
        "MODE": "generate",
        "OPENAI_BASE_URL": SETTINGS.openai_base_url,
    }
    if extra_env:
        env.update(extra_env)
    return client.containers.create(
        image=SETTINGS.runner_image,
        name=name,
        environment=env,
        user=user,
        volumes={job_dir_abs: {"bind": "/job", "mode": "rw"}},
        tmpfs={
            # Need `exec` so compiled binaries can run from /tmp (runner_test and user programs).
            "/tmp": "rw,size=512m,exec",
        },
        nano_cpus=int(cpus * 1_000_000_000),
        mem_limit=f"{memory_mb}m",
        memswap_limit=f"{memory_mb}m",
        pids_limit=pids_limit,
        cap_drop=["ALL"],
        security_opt=["no-new-privileges"],
        ulimits=[Ulimit(name="nofile", soft=1024, hard=1024)],
        labels={
            "realmoi.job_id": job_id,
            "realmoi.owner_user_id": owner_user_id,
            "realmoi.stage": "generate",
            "realmoi.attempt": str(attempt),
        },
        detach=True,
    )


def create_test_container(
    *,
    client: docker.DockerClient,
    job_id: str,
    owner_user_id: str,
    attempt: int,
    job_dir: Path,
    cpus: float,
    memory_mb: int,
    pids_limit: int,
    extra_env: dict[str, str] | None = None,
) -> Container:
    name = f"realmoi_{job_id}_test_a{attempt}"
    job_dir_abs = str(job_dir.resolve())
    output_dir_abs = str((job_dir / "output").resolve())
    user = f"{os.getuid()}:{os.getgid()}"
    env = {"MODE": "test"}
    if extra_env:
        env.update(extra_env)
    return client.containers.create(
        image=SETTINGS.runner_image,
        name=name,
        environment=env,
        user=user,
        volumes={
            job_dir_abs: {"bind": "/job", "mode": "ro"},
            output_dir_abs: {"bind": "/job/output", "mode": "rw"},
        },
        network_mode="none",
        read_only=True,
        tmpfs={
            # Need `exec` so compiled binaries can run from /tmp.
            "/tmp": "rw,size=256m,exec",
        },
        nano_cpus=int(cpus * 1_000_000_000),
        mem_limit=f"{memory_mb}m",
        memswap_limit=f"{memory_mb}m",
        pids_limit=pids_limit,
        cap_drop=["ALL"],
        security_opt=["no-new-privileges"],
        ulimits=[Ulimit(name="nofile", soft=1024, hard=1024)],
        labels={
            "realmoi.job_id": job_id,
            "realmoi.owner_user_id": owner_user_id,
            "realmoi.stage": "test",
            "realmoi.attempt": str(attempt),
        },
        detach=True,
    )
