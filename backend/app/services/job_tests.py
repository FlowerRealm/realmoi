from __future__ import annotations

# Job tests listing + preview helpers.
#
# This module is used by both HTTP and MCP routes to present a stable list of
# available tests and small previews for inputs/expected outputs.

import json
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from ._preview_io import safe_read_preview_text
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


def resolve_tests_file_path(*, tests_dir: Path, tests_rel: str) -> Path:
    """Resolve `tests/...` paths under `tests_dir` while preventing traversal."""
    rel = str(tests_rel or "").strip()
    if not rel.startswith("tests/"):
        raise ValueError("invalid_tests_rel")
    inner = rel.removeprefix("tests/").lstrip("/")
    p = PurePosixPath(inner)
    if not inner or p.is_absolute() or ".." in p.parts:
        raise ValueError("invalid_tests_rel")

    candidate = (tests_dir / inner).resolve()
    root = tests_dir.resolve()
    if root not in candidate.parents and candidate != root:
        raise ValueError("invalid_tests_rel")
    return candidate


def manifest_case_to_meta(*, tests_dir: Path, case: dict[str, Any]) -> JobTestMeta | None:
    name = str(case.get("name") or "").strip()
    if not name:
        return None

    group = str(case.get("group") or "default").strip() or "default"
    inp = str(case.get("in") or "").strip()
    if not inp:
        return None

    p_in = PurePosixPath(inp)
    if p_in.is_absolute() or ".." in p_in.parts:
        return None
    input_rel = f"tests/{inp.lstrip('/')}"

    out = case.get("out")
    expected_rel = None
    expected_present = False
    if out:
        out_s = str(out).strip()
        p_out = PurePosixPath(out_s)
        if out_s and not p_out.is_absolute() and ".." not in p_out.parts:
            expected_rel = f"tests/{out_s.lstrip('/')}"
            expected_present = (tests_dir / out_s).exists()

    return JobTestMeta(
        name=name,
        group=group,
        input_rel=input_rel,
        expected_rel=expected_rel,
        expected_present=expected_present,
    )


def list_tests_from_manifest(*, tests_dir: Path, manifest_path: Path) -> list[JobTestMeta] | None:
    if not manifest_path.exists():
        return None
    try:
        m = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(m, dict):
        return []

    items: list[JobTestMeta] = []
    cases = m["cases"] if "cases" in m and isinstance(m["cases"], list) else []
    for case in cases:
        if not isinstance(case, dict):
            continue
        meta = manifest_case_to_meta(tests_dir=tests_dir, case=case)
        if meta is None:
            continue
        items.append(meta)

    items.sort(key=lambda x: (x.group, x.name))
    return items


def list_tests_from_pairs(*, tests_dir: Path) -> list[JobTestMeta]:
    cases: list[JobTestMeta] = []

    has_subdir = any(p.is_dir() for p in tests_dir.iterdir())
    for root, _dirs, files in os.walk(tests_dir):
        root_p = Path(root)
        group = root_p.relative_to(tests_dir).parts[0] if has_subdir and root_p != tests_dir else "default"
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


def list_job_tests(*, job_json_path: Path, tests_dir: Path) -> list[JobTestMeta]:
    # List tests from a job input directory.
    #
    # Supports:
    # - `manifest.json` (format=auto/manifest)
    # - in/out pairs (`*.in` + optional `*.out`)
    if not tests_dir.exists():
        return []

    try:
        job = read_json(job_json_path)
    except Exception:
        job = {}

    tests = job.get("tests") or {}
    fmt = str(tests.get("format") or "auto")

    manifest_path = tests_dir / "manifest.json"
    if fmt in ("auto", "manifest"):
        items = list_tests_from_manifest(tests_dir=tests_dir, manifest_path=manifest_path)
        if items is not None:
            return items

    return list_tests_from_pairs(tests_dir=tests_dir)


def read_job_test_preview(
    *,
    tests_dir: Path,
    input_rel: str,
    expected_rel: str | None,
    max_bytes: int,
) -> dict[str, Any]:
    # Read preview text for a single test case input/expected.
    if not tests_dir.exists():
        raise FileNotFoundError("tests_not_found")

    max_bytes = int(max_bytes or DEFAULT_MAX_PREVIEW_BYTES)
    max_bytes = max(1, min(max_bytes, MAX_MAX_PREVIEW_BYTES))

    in_path = resolve_tests_file_path(tests_dir=tests_dir, tests_rel=input_rel)
    if not in_path.exists():
        raise FileNotFoundError("input_not_found")

    result: dict[str, Any] = {"input": safe_read_preview_text(in_path, max_bytes=max_bytes)}

    if expected_rel:
        out_path = resolve_tests_file_path(tests_dir=tests_dir, tests_rel=expected_rel)
        if out_path.exists():
            result["expected"] = safe_read_preview_text(out_path, max_bytes=max_bytes)
        else:
            result["expected"] = {"text": "", "truncated": False, "bytes": 0, "missing": True}
    else:
        result["expected"] = None

    return result
