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


def extract_zip_safe(zip_path: Path, dest_dir: Path, limits: ZipLimits) -> None:
    """
    Safely extract tests.zip.

    Strategy: extract to temp dir -> validate -> atomic move to dest_dir.
    """

    if not zip_path.exists():
        raise InvalidZip("zip_not_found")

    with zipfile.ZipFile(zip_path) as zf:
        infos = zf.infolist()
        if len(infos) > limits.max_files:
            raise InvalidZip("too_many_files")

        total_uncompressed = 0
        for info in infos:
            # Directories are allowed.
            name = info.filename
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
            total_uncompressed += info.file_size
            if total_uncompressed > limits.max_uncompressed_bytes:
                raise InvalidZip("zip_too_large")

        tmp_root = Path(tempfile.mkdtemp(prefix="realmoi-tests-"))
        try:
            zf.extractall(tmp_root)
            # Post-extract validation: no symlinks.
            for root, dirs, files in os.walk(tmp_root):
                for n in dirs + files:
                    p = Path(root) / n
                    if p.is_symlink():
                        raise InvalidZip("symlink_not_allowed")

            # Normalize: allow zip to contain tests/ or directly cases.
            extracted_tests = tmp_root / "tests"
            move_src = extracted_tests if extracted_tests.exists() else tmp_root

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

            # If we moved tmp_root/tests, tmp_root may still exist.
            if tmp_root.exists():
                shutil.rmtree(tmp_root, ignore_errors=True)
        except Exception:
            shutil.rmtree(tmp_root, ignore_errors=True)
            raise
