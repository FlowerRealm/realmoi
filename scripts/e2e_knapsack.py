from __future__ import annotations

import argparse
import io
import json
import os
import time
from urllib.parse import quote
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx


def _now_ms() -> int:
    return int(time.time() * 1000)


def _print(msg: str) -> None:
    print(msg, flush=True)


class ApiFailed(Exception):
    pass


@dataclass(frozen=True)
class ApiErrorInfo:
    status_code: int
    code: str
    message: str


def _parse_api_error(resp: httpx.Response) -> ApiErrorInfo:
    code = "http_error"
    message = resp.text
    try:
        data = resp.json()
        if isinstance(data, dict) and isinstance(data.get("error"), dict):
            err = data["error"]
            code = str(err.get("code") or code)
            message = str(err.get("message") or message)
    except Exception:
        pass
    return ApiErrorInfo(status_code=resp.status_code, code=code, message=message)


def api_request(
    client: httpx.Client,
    *,
    api_base: str,
    method: str,
    path: str,
    token: str | None = None,
    **kwargs: Any,
) -> httpx.Response:
    url = api_base.rstrip("/") + (path if path.startswith("/") else "/" + path)
    headers = dict(kwargs.pop("headers", {}) or {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resp = client.request(method, url, headers=headers, **kwargs)
    if resp.status_code >= 400:
        err = _parse_api_error(resp)
        raise ApiFailed(f"{method} {path}: {err.status_code} {err.code} {err.message}")
    return resp


def make_knapsack_tests_zip() -> bytes:
    cases = {
        "tests/1.in": "3 4\n2 3\n1 2\n3 4\n",
        "tests/1.out": "6\n",
        "tests/2.in": "5 0\n1 10\n2 20\n3 30\n4 40\n5 50\n",
        "tests/2.out": "0\n",
        "tests/3.in": "4 10\n1 1\n2 2\n3 3\n4 4\n",
        "tests/3.out": "10\n",
        "tests/4.in": "5 10\n2 6\n2 3\n6 5\n5 4\n4 6\n",
        "tests/4.out": "15\n",
        "tests/5.in": "6 11\n1 1\n2 6\n5 18\n6 22\n7 28\n3 10\n",
        "tests/5.out": "40\n",
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, content in cases.items():
            zf.writestr(name, content)
    return buf.getvalue()


def knapsack_statement_md() -> str:
    return """# 01 背包（模板题）

给定 n 件物品和一个容量为 W 的背包。第 i 件物品的重量为 w_i，价值为 v_i。
每件物品最多选择一次（0/1）。

请你求出在总重量不超过 W 的前提下，能获得的最大总价值。

## 输入格式

第一行两个整数 n W。
接下来 n 行，每行两个整数 w_i v_i。

## 输出格式

输出一个整数：最大总价值。

## 约束（参考）

- 1 ≤ n ≤ 1000
- 0 ≤ W ≤ 10000
- 0 ≤ w_i ≤ W
- 0 ≤ v_i ≤ 10^9
"""


def seed_wrong_cpp() -> str:
    # 一个常见错误：按 v/w 贪心（0/1 背包不成立）
    return r"""#include <bits/stdc++.h>
using namespace std;

int main() {
  ios::sync_with_stdio(false);
  cin.tie(nullptr);

  int n, W;
  if (!(cin >> n >> W)) return 0;
  struct Item {int w; long long v;};
  vector<Item> a(n);
  for (int i = 0; i < n; i++) cin >> a[i].w >> a[i].v;

  sort(a.begin(), a.end(), [](const Item& x, const Item& y){
    return (long double)x.v / max(1, x.w) > (long double)y.v / max(1, y.w);
  });

  long long ans = 0;
  for (auto &it : a) {
    if (it.w <= W) { W -= it.w; ans += it.v; }
  }
  cout << ans << "\n";
  return 0;
}
"""


def tail_terminal_log_local(*, jobs_root: Path, job_id: str, last_offset: int) -> int:
    log_path = jobs_root / job_id / "logs" / "terminal.log"
    if not log_path.exists():
        return last_offset
    data = log_path.read_bytes()
    if last_offset >= len(data):
        return last_offset
    chunk = data[last_offset:]
    try:
        text = chunk.decode("utf-8", errors="replace")
    except Exception:
        text = ""
    if text:
        _print(text.rstrip("\n"))
    return len(data)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api-base", default=os.environ.get("REALMOI_E2E_API_BASE", "http://localhost:8000/api"))
    ap.add_argument("--admin-username", default=os.environ.get("REALMOI_ADMIN_USERNAME", "admin"))
    ap.add_argument("--admin-password", default=os.environ.get("REALMOI_ADMIN_PASSWORD", "admin-password-123"))
    ap.add_argument("--model", default=os.environ.get("REALMOI_E2E_MODEL", "gpt-5.2-codex"))
    ap.add_argument("--search-mode", choices=["disabled", "cached", "live"], default="disabled")
    ap.add_argument("--timeout-seconds", type=int, default=1800)
    ap.add_argument("--poll-seconds", type=float, default=2.0)
    ap.add_argument("--tail-terminal", action="store_true")
    ap.add_argument("--jobs-root", default=os.environ.get("REALMOI_JOBS_ROOT", "jobs"))
    args = ap.parse_args()

    api_base = str(args.api_base)
    model = str(args.model).strip()
    if not model:
        _print("[e2e] missing --model")
        return 2

    client = httpx.Client(timeout=30.0, trust_env=False)

    _print(f"[e2e] api_base={api_base}")
    _print(f"[e2e] model={model} search_mode={args.search_mode}")

    # 1) login admin
    admin_login = api_request(
        client,
        api_base=api_base,
        method="POST",
        path="/auth/login",
        json={"username": args.admin_username, "password": args.admin_password},
    ).json()
    admin_token = str(admin_login.get("access_token") or "")
    if not admin_token:
        raise ApiFailed("admin login returned empty token")
    _print("[e2e] admin login ok")

    # 2) ensure model is active+priced
    api_request(
        client,
        api_base=api_base,
        method="PUT",
        path=f"/admin/pricing/models/{quote(model, safe='')}",
        token=admin_token,
        json={
            "currency": "USD",
            "is_active": True,
            "input_microusd_per_1m_tokens": 1,
            "cached_input_microusd_per_1m_tokens": 1,
            "output_microusd_per_1m_tokens": 1,
            "cached_output_microusd_per_1m_tokens": 1,
        },
    )
    _print("[e2e] pricing enabled")

    # 3) signup user
    username = f"e2e_knapsack_{_now_ms()}"
    password = "password-123"
    user_signup = api_request(
        client,
        api_base=api_base,
        method="POST",
        path="/auth/signup",
        json={"username": username, "password": password},
    ).json()
    user_token = str(user_signup.get("access_token") or "")
    if not user_token:
        raise ApiFailed("signup returned empty token")
    _print(f"[e2e] user signup ok: {username}")

    # 4) create job with tests.zip
    tests_zip = make_knapsack_tests_zip()
    statement_md = knapsack_statement_md()

    data = {
        "model": model,
        "statement_md": statement_md,
        "current_code_cpp": seed_wrong_cpp(),
        "tests_format": "auto",
        "compare_mode": "tokens",
        "run_if_no_expected": "true",
        "search_mode": args.search_mode,
        "time_limit_ms": "2000",
        "memory_limit_mb": "1024",
    }
    files = {"tests_zip": ("tests.zip", tests_zip, "application/zip")}
    created = api_request(
        client,
        api_base=api_base,
        method="POST",
        path="/jobs",
        token=user_token,
        data=data,
        files=files,
    ).json()
    job_id = str(created.get("job_id") or "")
    if not job_id:
        raise ApiFailed("create job returned empty job_id")
    _print(f"[e2e] job created: {job_id}")

    # 5) start
    api_request(
        client,
        api_base=api_base,
        method="POST",
        path=f"/jobs/{job_id}/start",
        token=user_token,
    )
    _print("[e2e] job started, waiting...")

    # 6) poll
    deadline = time.time() + float(args.timeout_seconds)
    jobs_root = Path(str(args.jobs_root))
    last_term_off = 0
    last_state: dict[str, Any] | None = None

    while True:
        st = api_request(client, api_base=api_base, method="GET", path=f"/jobs/{job_id}", token=user_token).json()
        last_state = st
        status = str(st.get("status") or "")
        if args.tail_terminal:
            last_term_off = tail_terminal_log_local(jobs_root=jobs_root, job_id=job_id, last_offset=last_term_off)

        if status in ("succeeded", "failed", "cancelled"):
            _print(f"[e2e] finished: {status}")
            break
        if time.time() > deadline:
            _print("[e2e] timeout, cancelling job...")
            try:
                api_request(client, api_base=api_base, method="POST", path=f"/jobs/{job_id}/cancel", token=user_token)
            except Exception:
                pass
            return 1
        time.sleep(float(args.poll_seconds))

    try:
        report = api_request(
            client,
            api_base=api_base,
            method="GET",
            path=f"/jobs/{job_id}/artifacts/report.json",
            token=user_token,
        ).json()
    except ApiFailed as e:
        _print(f"[e2e] report fetch failed: {e}")
        if last_state is not None:
            _print("[e2e] last job state:")
            _print(json.dumps(last_state, ensure_ascii=False, indent=2))
        _print("[e2e] terminal.log tail:")
        tail_terminal_log_local(jobs_root=jobs_root, job_id=job_id, last_offset=max(0, last_term_off - 20_000))
        return 1

    rep_status = str(report.get("status") or "")
    compile_ok = bool((report.get("compile") or {}).get("ok"))
    failed = int(((report.get("summary") or {}).get("failed") or 0))
    _print(f"[e2e] report.status={rep_status} compile_ok={compile_ok} failed={failed}")

    ok = rep_status == "succeeded" and compile_ok and failed == 0
    if not ok:
        _print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    _print("[e2e] ✅ knapsack passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
