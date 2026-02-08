from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from backend.app.services.zip_safe import InvalidZip, ZipLimits, extract_zip_safe


def _limits() -> ZipLimits:
    return ZipLimits(max_files=100, max_uncompressed_bytes=10_000_000, max_single_file_bytes=1_000_000, max_depth=8)


def test_extract_zip_safe_ok(tmp_path: Path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("tests/1.in", "1 2\n")
        zf.writestr("tests/1.out", "3\n")

    zip_path = tmp_path / "tests.zip"
    zip_path.write_bytes(buf.getvalue())

    dest = tmp_path / "out_tests"
    extract_zip_safe(zip_path, dest, _limits())
    assert (dest / "1.in").read_text(encoding="utf-8") == "1 2\n"


def test_extract_zip_safe_zip_slip(tmp_path: Path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../evil.txt", "x")
    zip_path = tmp_path / "tests.zip"
    zip_path.write_bytes(buf.getvalue())
    with pytest.raises(InvalidZip) as e:
        extract_zip_safe(zip_path, tmp_path / "out", _limits())
    assert str(e.value) == "zip_slip"


def test_extract_zip_safe_symlink_rejected(tmp_path: Path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        info = zipfile.ZipInfo("tests/link")
        # Mark as symlink (unix): 0120000 (symlink) + 0777 perms.
        info.external_attr = (0o120777 & 0xFFFF) << 16
        zf.writestr(info, "ignored")
    zip_path = tmp_path / "tests.zip"
    zip_path.write_bytes(buf.getvalue())
    with pytest.raises(InvalidZip) as e:
        extract_zip_safe(zip_path, tmp_path / "out", _limits())
    assert str(e.value) == "symlink_not_allowed"

