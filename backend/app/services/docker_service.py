from __future__ import annotations

# AUTO_COMMENT_HEADER_V1: docker_service.py
# 说明：
# - 该模块封装 Docker SDK 调用，用于在容器内运行 generate/test 流程。
# - copy_from_container 使用 get_archive(tar stream) → 本地安全解包（防 tar slip / 链接逃逸）。
# - 所有容器默认以 host uid:gid 运行，以保证对 bind-mounted /job 的写权限。

import io
import os
import shutil
import tarfile
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any, Iterable

import docker
from docker.models.containers import Container
from docker.types import Ulimit

from ..settings import SETTINGS


@dataclass(frozen=True)
class ContainerRef:
    id: str
    name: str


@dataclass(frozen=True)
class ContainerJob:
    job_id: str
    owner_user_id: str
    attempt: int
    job_dir: Path


@dataclass(frozen=True)
class ContainerResources:
    cpus: float
    memory_mb: int
    pids_limit: int


_IMAGE_PULL_LOCK = threading.Lock()
_READY_IMAGES: set[str] = set()


# Docker SDK helper: keep client creation centralized for consistent timeouts.
def docker_client() -> docker.DockerClient:
    return docker.from_env(timeout=SETTINGS.docker_api_timeout_seconds)


def ensure_image_ready(*, client: docker.DockerClient, image: str) -> None:
    # Pull-once per backend process; runners call this on-demand.
    if image in _READY_IMAGES:
        return

    with _IMAGE_PULL_LOCK:
        if image in _READY_IMAGES:
            return
        try:
            existing_image = client.images.get(image)
        except docker.errors.ImageNotFound:
            client.images.pull(image)
        _READY_IMAGES.add(image)


def make_tar_bytes(files: dict[str, bytes]) -> bytes:
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
    tar_data = make_tar_bytes(files)
    container.put_archive(dest_dir, tar_data)

# Docker "get_archive" returns a tar stream; we read it into bytes so we can validate and extract safely.
def read_archive_stream(stream: Iterable[bytes]) -> bytes:
    """
    Read a docker archive stream into a single bytes buffer.

    Args:
        stream: Iterable of bytes chunks returned by docker SDK.

    Returns:
        Concatenated archive bytes.
    """

    buf = io.BytesIO()
    for chunk in stream:
        written_bytes = buf.write(chunk)
        if written_bytes <= 0:
            continue
    return buf.getvalue()


def validate_tar_member(member: tarfile.TarInfo) -> PurePosixPath | None:
    name = (member.name or "").strip()
    if not name:
        return None

    p = PurePosixPath(name)
    # Guard against tar slip (absolute paths / parent traversal).
    if p.is_absolute() or ".." in p.parts:
        raise ValueError("tar_slip")
    # Reject links to avoid escaping the extraction root.
    if member.issym() or member.islnk():
        raise ValueError("symlink_not_allowed")
    return p


def extract_tar_regular_file(tf: tarfile.TarFile, *, member: tarfile.TarInfo, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    src = tf.extractfile(member)
    if src is None:
        return
    with src, target.open("wb") as out:
        shutil.copyfileobj(src, out)


def safe_extract_tar_bytes(*, tar_bytes: bytes, dest_dir: Path) -> None:
    """
    Safely extract tar bytes into a destination directory.

    This rejects absolute paths, parent traversal (tar slip), and any symlink/hardlink.

    Args:
        tar_bytes: Tar archive bytes.
        dest_dir: Target directory for extraction.

    Returns:
        None.
    """

    buf = io.BytesIO(tar_bytes)
    buf.seek(0)
    with tarfile.open(fileobj=buf, mode="r:*") as tf:
        for member in tf.getmembers():
            p = validate_tar_member(member)
            if p is None:
                continue

            target = dest_dir.joinpath(*p.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isreg():
                # Ignore other file types.
                continue
            extract_tar_regular_file(tf, member=member, target=target)


def select_archive_root(extracted_dir: Path) -> Path:
    """
    Pick the effective root of an extracted docker archive.

    Docker archives usually contain a single top-level directory for directory copies.

    Args:
        extracted_dir: Directory that contains extracted tar members.

    Returns:
        Directory to be treated as the root for copy-out.
    """

    children = list(extracted_dir.iterdir())
    if len(children) == 1 and children[0].is_dir():
        return children[0]
    return extracted_dir


def remove_existing_path(target: Path) -> None:
    if not target.exists():
        return
    if target.is_dir():
        shutil.rmtree(target)
        return
    target.unlink()


def replace_and_move_children(*, src_root: Path, dest_dir: Path) -> None:
    """
    Replace destination children and move source children into destination.

    Args:
        src_root: Source directory to move children from.
        dest_dir: Destination directory on host.

    Returns:
        None.
    """

    dest_dir.mkdir(parents=True, exist_ok=True)
    for child in src_root.iterdir():
        target = dest_dir / child.name
        # Replace existing destination entries to keep copy-out deterministic.
        remove_existing_path(target)
        shutil.move(str(child), str(target))


def copy_from_container(container: Container, *, src_path: str, dest_dir: Path) -> None:
    """
    Copy a file or directory from container to host.

    This uses docker get_archive, which returns a tar stream.
    """

    stream, _stat = container.get_archive(src_path)
    tmp_dir = Path(tempfile.mkdtemp(prefix="realmoi-docker-cp-"))
    try:
        tar_bytes = read_archive_stream(stream)
        safe_extract_tar_bytes(tar_bytes=tar_bytes, dest_dir=tmp_dir)
        src_root = select_archive_root(tmp_dir)
        replace_and_move_children(src_root=src_root, dest_dir=dest_dir)
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
        # Best-effort redaction (plain bytes replace).
        s = data
        for secret in redact_secrets:
            if secret:
                s = s.replace(secret.encode("utf-8"), b"***")
        return s

    def _run() -> None:
        written = 0
        log_file = log_path.open("ab")
        with log_file as f:
            try:
                for chunk in container.logs(stream=True, follow=True):
                    if not isinstance(chunk, (bytes, bytearray)):
                        continue
                    chunk = _redact(bytes(chunk))
                    if written >= max_bytes:
                        continue
                    remaining = max_bytes - written
                    chunk = chunk[:remaining]
                    _write_len = f.write(chunk)
                    f.flush()
                    written += len(chunk)
            except (docker.errors.APIError, OSError, ValueError):
                # Best effort: failing to collect logs should not fail the job.
                return

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t


def create_generate_container(
    *,
    client: docker.DockerClient,
    job: ContainerJob,
    resources: ContainerResources,
    extra_env: dict[str, str] | None = None,
) -> Container:
    ensure_image_ready(client=client, image=SETTINGS.runner_image)
    name = f"realmoi_{job.job_id}_generate_a{job.attempt}"
    job_dir_abs = str(job.job_dir.resolve())
    # Run as host uid:gid so the container can write to the bind-mounted /job.
    user = f"{os.getuid()}:{os.getgid()}"
    # Runner process reads MODE + OPENAI_BASE_URL; keep env narrow by default.
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
        extra_hosts={"host.docker.internal": "host-gateway"},
        user=user,
        volumes={job_dir_abs: {"bind": "/job", "mode": "rw"}},
        tmpfs={
            # Need `exec` so compiled binaries can run from /tmp (runner_test and user programs).
            "/tmp": "rw,size=512m,exec",
        },
        nano_cpus=int(resources.cpus * 1_000_000_000),
        mem_limit=f"{resources.memory_mb}m",
        memswap_limit=f"{resources.memory_mb}m",
        pids_limit=resources.pids_limit,
        cap_drop=["ALL"],
        security_opt=["no-new-privileges"],
        ulimits=[Ulimit(name="nofile", soft=1024, hard=1024)],
        labels={
            "realmoi.job_id": job.job_id,
            "realmoi.owner_user_id": job.owner_user_id,
            "realmoi.stage": "generate",
            "realmoi.attempt": str(job.attempt),
        },
        detach=True,
    )


def create_test_container(
    *,
    client: docker.DockerClient,
    job: ContainerJob,
    resources: ContainerResources,
    extra_env: dict[str, str] | None = None,
) -> Container:
    ensure_image_ready(client=client, image=SETTINGS.runner_image)
    name = f"realmoi_{job.job_id}_test_a{job.attempt}"
    job_dir_abs = str(job.job_dir.resolve())
    output_dir_abs = str((job.job_dir / "output").resolve())
    # Tests read input from /job (ro) and write outputs to /job/output (rw).
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
        # No network access for test runs.
        network_mode="none",
        read_only=True,
        tmpfs={
            # Need `exec` so compiled binaries can run from /tmp.
            "/tmp": "rw,size=256m,exec",
        },
        nano_cpus=int(resources.cpus * 1_000_000_000),
        mem_limit=f"{resources.memory_mb}m",
        memswap_limit=f"{resources.memory_mb}m",
        pids_limit=resources.pids_limit,
        cap_drop=["ALL"],
        security_opt=["no-new-privileges"],
        ulimits=[Ulimit(name="nofile", soft=1024, hard=1024)],
        labels={
            "realmoi.job_id": job.job_id,
            "realmoi.owner_user_id": job.owner_user_id,
            "realmoi.stage": "test",
            "realmoi.attempt": str(job.attempt),
        },
        detach=True,
    )
