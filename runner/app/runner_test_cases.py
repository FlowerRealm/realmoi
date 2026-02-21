from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, cast

from runner_test_fs import job_path, read_text
from runner_test_models import Case, CompareMode


def normalize_compare_mode(value: str, *, default: CompareMode) -> CompareMode:
    v = str(value or "").strip()
    if v in ("tokens", "trim_ws", "exact"):
        return cast(CompareMode, v)
    return default


def normalize_tokens(s: str) -> list[str]:
    return s.split()


def normalize_trim_ws(s: str) -> str:
    lines = [line.rstrip() for line in s.replace("\r\n", "\n").split("\n")]
    return "\n".join(lines).rstrip("\n") + "\n"


def compare_exact(actual: str, expected: str) -> tuple[bool, str, str, str]:
    ok = actual == expected
    if ok:
        return True, "", expected[:200], actual[:200]
    return False, "exact mismatch", expected[:200], actual[:200]


def compare_trim_ws(actual: str, expected: str) -> tuple[bool, str, str, str]:
    a = normalize_trim_ws(actual)
    e = normalize_trim_ws(expected)
    ok = a == e
    if ok:
        return True, "", e[:200], a[:200]
    return False, "trim_ws mismatch", e[:200], a[:200]


def compare_tokens(actual: str, expected: str) -> tuple[bool, str, str, str]:
    a_tokens = normalize_tokens(actual)
    e_tokens = normalize_tokens(expected)
    if a_tokens == e_tokens:
        return True, "", " ".join(e_tokens[:50]), " ".join(a_tokens[:50])
    n = min(len(a_tokens), len(e_tokens))
    idx = next((i for i in range(n) if a_tokens[i] != e_tokens[i]), n)
    return (
        False,
        f"tokens mismatch at {idx}: expected={e_tokens[idx] if idx < len(e_tokens) else '<eof>'} actual={a_tokens[idx] if idx < len(a_tokens) else '<eof>'}",
        " ".join(e_tokens[max(0, idx - 10) : idx + 10]),
        " ".join(a_tokens[max(0, idx - 10) : idx + 10]),
    )


def compare_output(actual: str, expected: str, mode: CompareMode) -> tuple[bool, str, str, str]:
    if mode == "exact":
        return compare_exact(actual, expected)
    if mode == "trim_ws":
        return compare_trim_ws(actual, expected)
    return compare_tokens(actual, expected)


def load_cases_from_manifest(*, manifest_path: Path, default_mode: CompareMode) -> list[Case]:
    m = json.loads(read_text(manifest_path))
    cases: list[Case] = []
    for c in m.get("cases") or []:
        name = str(c.get("name") or "")
        group = str(c.get("group") or "default")
        inp = str(c.get("in") or "")
        out = c.get("out")
        cm_raw = str(c.get("compare_mode") or m.get("compare_mode") or default_mode)
        cm = normalize_compare_mode(cm_raw, default=default_mode)
        cases.append(
            Case(
                name=name,
                group=group,
                input_rel=inp,
                expected_rel=str(out) if out else None,
                compare_mode=cm,
            )
        )
    return cases


def load_cases_from_pairs(*, tests_dir: Path, default_mode: CompareMode) -> list[Case]:
    cases: list[Case] = []
    has_subdir = any(p.is_dir() for p in tests_dir.iterdir())
    for root, _dirs, files in os.walk(tests_dir):
        root_p = Path(root)
        group = root_p.relative_to(tests_dir).parts[0] if has_subdir and root_p != tests_dir else "default"
        for fn in files:
            if not fn.endswith(".in"):
                continue
            in_path = root_p / fn
            rel_in = str(in_path.relative_to(tests_dir))
            base = fn[: -len(".in")]
            out_path = root_p / f"{base}.out"
            rel_out = str(out_path.relative_to(tests_dir)) if out_path.exists() else None
            cases.append(
                Case(
                    name=base,
                    group=group,
                    input_rel=rel_in,
                    expected_rel=rel_out,
                    compare_mode=default_mode,
                )
            )
    cases.sort(key=lambda c: (c.group, c.name))
    return cases


def load_cases(job: dict[str, Any]) -> list[Case]:
    tests = job.get("tests") or {}
    tests_dir = job_path("input") / str(tests.get("dir") or "tests")
    fmt = str(tests.get("format") or "auto")
    default_mode = normalize_compare_mode(
        str((tests.get("compare") or {}).get("mode") or "tokens"),
        default="tokens",
    )

    manifest_path = tests_dir / "manifest.json"
    if fmt in ("auto", "manifest") and manifest_path.exists():
        return load_cases_from_manifest(manifest_path=manifest_path, default_mode=default_mode)

    if not tests_dir.exists():
        return []

    return load_cases_from_pairs(tests_dir=tests_dir, default_mode=default_mode)
