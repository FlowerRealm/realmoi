from __future__ import annotations

import os
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


class InvalidZip(Exception):
    pass


@dataclass(frozen=True)
class ZipLimits:
    max_files: int
    max_uncompressed_bytes: int
    max_single_file_bytes: int
    max_depth: int


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    # For Unix zip, top 16 bits are file mode.
    mode = (info.external_attr >> 16) & 0xFFFF
    return (mode & 0o170000) == 0o120000


def _validate_zip_paths(*, infos: list[zipfile.ZipInfo], limits: ZipLimits) -> None:
    # Pre-extract validation to prevent zip-slip and limit resource usage.

    total_uncompressed = 0
    for info in infos:
        # Directories are allowed.
        name = str(info.filename or "")
        if not name:
            continue

        p = PurePosixPath(name)
        if p.is_absolute() or ".." in p.parts:
            raise InvalidZip("zip_slip")
        if len(p.parts) > limits.max_depth:
            raise InvalidZip("path_too_deep")

        if _is_symlink(info):
            raise InvalidZip("symlink_not_allowed")

        if info.file_size > limits.max_single_file_bytes:
            raise InvalidZip("file_too_large")

        total_uncompressed += int(info.file_size or 0)
        if total_uncompressed > limits.max_uncompressed_bytes:
            raise InvalidZip("zip_too_large")


def _validate_no_symlinks(*, root: Path) -> None:
    # Post-extract validation: ensure extraction did not create symlinks.
    for walk_root, dirs, files in os.walk(root):
        for name in dirs + files:
            p = Path(walk_root) / name
            if p.is_symlink():
                raise InvalidZip("symlink_not_allowed")


def _move_into_place(*, move_src: Path, dest_dir: Path) -> None:
    dest_dir.parent.mkdir(parents=True, exist_ok=True)
    if dest_dir.exists():
        shutil.rmtree(dest_dir)

    try:
        os.replace(move_src, dest_dir)
    except OSError as e:
        # EXDEV: cross-device link (e.g. /tmp tmpfs -> disk). Fall back to copy+remove.
        if getattr(e, "errno", None) == 18:
            shutil.move(str(move_src), str(dest_dir))
        else:
            raise


def extract_zip_safe(zip_path: Path, dest_dir: Path, limits: ZipLimits) -> None:
    """
    Safely extract tests.zip.

    Strategy: extract to temp dir -> validate -> atomic move to dest_dir.
    """

    if not zip_path.exists():
        raise InvalidZip("zip_not_found")

    with zipfile.ZipFile(zip_path) as zip_file:
        infos = zip_file.infolist()
        if len(infos) > limits.max_files:
            raise InvalidZip("too_many_files")

        _validate_zip_paths(infos=infos, limits=limits)

        tmp_root = Path(tempfile.mkdtemp(prefix="realmoi-tests-"))
        try:
            zip_file.extractall(tmp_root)
            _validate_no_symlinks(root=tmp_root)

            # Normalize: allow zip to contain tests/ or directly cases.
            extracted_tests = tmp_root / "tests"
            move_src = extracted_tests if extracted_tests.exists() else tmp_root

            _move_into_place(move_src=move_src, dest_dir=dest_dir)

            # If we moved tmp_root/tests, tmp_root may still exist.
            if tmp_root.exists():
                shutil.rmtree(tmp_root, ignore_errors=True)
        except Exception:
            shutil.rmtree(tmp_root, ignore_errors=True)
            raise
