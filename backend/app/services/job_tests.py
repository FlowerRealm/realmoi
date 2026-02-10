from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from ..utils.fs import read_json


DEFAULT_MAX_PREVIEW_BYTES = 64 * 1024
MAX_MAX_PREVIEW_BYTES = 256 * 1024


@dataclass(frozen=True)
class JobTestMeta:
    name: str
    group: str
    input_rel: str
    expected_rel: str | None
    expected_present: bool


def _sanitize_tests_rel(rel: str) -> str:
    rel = str(rel or "").strip()
    if not rel.startswith("tests/"):
        raise ValueError("invalid_tests_rel")
    inner = rel.removeprefix("tests/").lstrip("/")
    p = PurePosixPath(inner)
    if not inner or p.is_absolute() or ".." in p.parts:
        raise ValueError("invalid_tests_rel")
    return inner


def _safe_read_preview_text(path: Path, *, max_bytes: int) -> dict[str, Any]:
    size_bytes = int(path.stat().st_size)
    with path.open("rb") as fp:
        raw = fp.read(max_bytes)
    return {
        "text": raw.decode("utf-8", errors="replace"),
        "truncated": size_bytes > max_bytes,
        "bytes": size_bytes,
    }


def list_job_tests(*, job_json_path: Path, tests_dir: Path) -> list[JobTestMeta]:
    """List tests from a job input directory.

    Supports:
      - `manifest.json` (format=auto/manifest)
      - in/out pairs (`*.in` + optional `*.out`)

    Args:
        job_json_path: Path to `input/job.json`.
        tests_dir: Path to the extracted tests directory (typically `input/tests`).

    Returns:
        A stable-sorted list of test metadata.
    """
    if not tests_dir.exists():
        return []

    try:
        job = read_json(job_json_path)
    except Exception:
        job = {}

    tests = job.get("tests") or {}
    fmt = str(tests.get("format") or "auto")

    manifest_path = tests_dir / "manifest.json"
    if fmt in ("auto", "manifest") and manifest_path.exists():
        try:
            m = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            m = {}

        items: list[JobTestMeta] = []
        for c in m.get("cases") or []:
            if not isinstance(c, dict):
                continue
            name = str(c.get("name") or "").strip()
            if not name:
                continue
            group = str(c.get("group") or "default").strip() or "default"
            inp = str(c.get("in") or "").strip()
            if not inp:
                continue

            p_in = PurePosixPath(inp)
            if p_in.is_absolute() or ".." in p_in.parts:
                continue
            input_rel = f"tests/{inp.lstrip('/')}"

            out = c.get("out")
            expected_rel = None
            expected_present = False
            if out:
                out_s = str(out).strip()
                p_out = PurePosixPath(out_s)
                if not out_s or p_out.is_absolute() or ".." in p_out.parts:
                    out_s = ""
                if out_s:
                    expected_rel = f"tests/{out_s.lstrip('/')}"
                    expected_present = (tests_dir / out_s).exists()

            items.append(
                JobTestMeta(
                    name=name,
                    group=group,
                    input_rel=input_rel,
                    expected_rel=expected_rel,
                    expected_present=expected_present,
                )
            )

        items.sort(key=lambda x: (x.group, x.name))
        return items

    # in_out_pairs
    cases: list[JobTestMeta] = []

    has_subdir = any(p.is_dir() for p in tests_dir.iterdir())
    for root, _dirs, files in os.walk(tests_dir):
        root_p = Path(root)
        group = (
            root_p.relative_to(tests_dir).parts[0]
            if has_subdir and root_p != tests_dir
            else "default"
        )
        for fn in files:
            if not fn.endswith(".in"):
                continue
            in_path = root_p / fn
            rel_in = in_path.relative_to(tests_dir).as_posix()
            base = fn[: -len(".in")]
            out_path = root_p / f"{base}.out"
            rel_out = out_path.relative_to(tests_dir).as_posix() if out_path.exists() else None
            cases.append(
                JobTestMeta(
                    name=base,
                    group=group,
                    input_rel=f"tests/{rel_in}",
                    expected_rel=f"tests/{rel_out}" if rel_out else None,
                    expected_present=bool(rel_out),
                )
            )

    cases.sort(key=lambda c: (c.group, c.name))
    return cases


def read_job_test_preview(
    *,
    tests_dir: Path,
    input_rel: str,
    expected_rel: str | None,
    max_bytes: int,
) -> dict[str, Any]:
    """Read preview text for a single test case input/expected.

    Args:
        tests_dir: Path to extracted tests directory.
        input_rel: Relative path like `tests/01.in`.
        expected_rel: Relative path like `tests/01.out` or None.
        max_bytes: Max bytes to read per file (clamped).

    Returns:
        A dict with `input` and `expected` preview payload.
    """
    if not tests_dir.exists():
        raise FileNotFoundError("tests_not_found")

    max_bytes = int(max_bytes or DEFAULT_MAX_PREVIEW_BYTES)
    max_bytes = max(1, min(max_bytes, MAX_MAX_PREVIEW_BYTES))

    in_inner = _sanitize_tests_rel(input_rel)
    in_path = (tests_dir / in_inner).resolve()
    root = tests_dir.resolve()
    if root not in in_path.parents and in_path != root:
        raise ValueError("invalid_tests_rel")
    if not in_path.exists():
        raise FileNotFoundError("input_not_found")

    result: dict[str, Any] = {"input": _safe_read_preview_text(in_path, max_bytes=max_bytes)}

    if expected_rel:
        out_inner = _sanitize_tests_rel(expected_rel)
        out_path = (tests_dir / out_inner).resolve()
        if root not in out_path.parents and out_path != root:
            raise ValueError("invalid_tests_rel")
        if out_path.exists():
            result["expected"] = _safe_read_preview_text(out_path, max_bytes=max_bytes)
        else:
            result["expected"] = {"text": "", "truncated": False, "bytes": 0, "missing": True}
    else:
        result["expected"] = None

    return result

