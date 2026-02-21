from __future__ import annotations

# End-to-end smoke test: 0/1 knapsack.
#
# 目标：
# - 在本地或 CI 环境里，对“创建 job -> 启动 -> 等待 -> 拉取 report”链路做一次全流程验证
# - 通过 MCP WS（/api/mcp/ws）实时 tail 任务状态（可选）
#
# 说明：这是测试脚本，不是业务代码；因此容错以“输出可读日志 + 不中断清理”为主。
#
# AUTO_COMMENT_HEADER_V1: e2e_knapsack.py
# - 该脚本的成功判定：report.status=succeeded 且 compile.ok 且 summary.failed=0
# - 该脚本优先验证“接口链路”而不是“题目本身”，因此输入规模较小

import argparse
import base64
import io
import json
import os
import threading
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from urllib.parse import quote

try:
    from e2e_support import (  # type: ignore
        APIRequestFailed,
        MCPWebSocketClient,
        api_request,
        now_milliseconds,
        print_line,
        tail_job_stream_mcp,
        tail_terminal_log_local,
    )
except ModuleNotFoundError:  # pragma: no cover
    import sys as _sys
    from pathlib import Path as _Path

    _scripts_dir = str(_Path(__file__).resolve().parent)
    if _scripts_dir not in _sys.path:
        _sys.path.insert(0, _scripts_dir)
    from e2e_support import (  # type: ignore
        APIRequestFailed,
        MCPWebSocketClient,
        api_request,
        now_milliseconds,
        print_line,
        tail_job_stream_mcp,
        tail_terminal_log_local,
    )


def make_knapsack_tests_zip() -> bytes:
    """构造一份最小 `tests.zip`（输入/期望输出）用于端到端验证。"""
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
    """返回 0/1 背包题面（Markdown）。"""
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
    """返回一份故意错误的 C++ 种子代码（贪心 v/w，0/1 背包不成立）。"""
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


@dataclass(frozen=True)
class E2EArgs:
    api_base: str
    admin_username: str
    admin_password: str
    model: str
    search_mode: str
    timeout_seconds: int
    poll_seconds: float
    tail_terminal: bool
    jobs_root: str


@dataclass(frozen=True)
class JobWaitConfig:
    """等待 job 结束的配置。"""

    timeout_seconds: int
    poll_seconds: float
    tail_terminal: bool
    jobs_root: Path


def parse_args() -> E2EArgs:
    """解析命令行参数并回填环境变量默认值。"""
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument("--api-base", default=os.environ.get("REALMOI_E2E_API_BASE", "http://localhost:8000/api"))
    arg_parser.add_argument("--admin-username", default=os.environ.get("REALMOI_ADMIN_USERNAME", "admin"))
    arg_parser.add_argument("--admin-password", default=os.environ.get("REALMOI_ADMIN_PASSWORD", "admin-password-123"))
    arg_parser.add_argument("--model", default=os.environ.get("REALMOI_E2E_MODEL", "gpt-5.2-codex"))
    arg_parser.add_argument("--search-mode", choices=["disabled", "cached", "live"], default="disabled")
    arg_parser.add_argument("--timeout-seconds", type=int, default=1800)
    arg_parser.add_argument("--poll-seconds", type=float, default=2.0)
    arg_parser.add_argument("--tail-terminal", action="store_true")
    arg_parser.add_argument("--jobs-root", default=os.environ.get("REALMOI_JOBS_ROOT", "jobs"))
    ns = arg_parser.parse_args()
    return E2EArgs(
        api_base=str(ns.api_base),
        admin_username=str(ns.admin_username),
        admin_password=str(ns.admin_password),
        model=str(ns.model),
        search_mode=str(ns.search_mode),
        timeout_seconds=int(ns.timeout_seconds),
        poll_seconds=float(ns.poll_seconds),
        tail_terminal=bool(ns.tail_terminal),
        jobs_root=str(ns.jobs_root),
    )


def login_admin(*, client: httpx.Client, api_base: str, username: str, password: str) -> str:
    """使用管理员账号登录并返回 access token。"""
    return request_access_token(
        client=client,
        api_base=api_base,
        path="/auth/login",
        body={"username": username, "password": password},
    )


def request_access_token(
    *,
    client: httpx.Client,
    api_base: str,
    path: str,
    body: dict[str, Any],
) -> str:
    payload = api_request(
        client,
        api_base=api_base,
        method="POST",
        path=path,
        json=body,
    ).json()
    token = str((payload or {}).get("access_token") or "")
    if not token:
        raise APIRequestFailed(f"request_access_token returned empty token path={path}")
    return token


def enable_pricing_for_model(*, client: httpx.Client, api_base: str, token: str, model: str) -> None:
    """确保某模型在 admin pricing 中已启用（用于 E2E）。"""
    api_request(
        client,
        api_base=api_base,
        method="PUT",
        path=f"/admin/pricing/models/{quote(model, safe='')}",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "currency": "USD",
            "is_active": True,
            "input_microusd_per_1m_tokens": 1,
            "cached_input_microusd_per_1m_tokens": 1,
            "output_microusd_per_1m_tokens": 1,
            "cached_output_microusd_per_1m_tokens": 1,
        },
    )


def create_job_knapsack(*, mcp: MCPWebSocketClient, model: str, search_mode: str) -> str:
    """通过 MCP 创建 knapsack job 并返回 job_id。"""
    tests_zip = make_knapsack_tests_zip()
    try:
        tests_zip_b64 = base64.b64encode(tests_zip).decode("ascii")
    except (UnicodeDecodeError, ValueError) as exc:
        raise APIRequestFailed(f"tests_zip encode failed: {type(exc).__name__}: {exc}") from exc
    created = mcp.call_tool(
        name="job.create",
        arguments={
            "model": model,
            "statement_md": knapsack_statement_md(),
            "current_code_cpp": seed_wrong_cpp(),
            "tests_zip_b64": tests_zip_b64,
            "tests_format": "auto",
            "compare_mode": "tokens",
            "run_if_no_expected": True,
            "search_mode": search_mode,
            "reasoning_effort": "medium",
            "time_limit_ms": 2000,
            "memory_limit_mb": 1024,
        },
    )
    job_id = str((created or {}).get("job_id") or "")
    if not job_id:
        raise APIRequestFailed("mcp job.create returned empty job_id")
    return job_id


def cancel_job_best_effort(*, mcp: MCPWebSocketClient, job_id: str) -> None:
    """尽力取消 job（用于 timeout 清理；失败不抛异常）。"""
    try:
        mcp.call_tool(name="job.cancel", arguments={"job_id": job_id})
    except (APIRequestFailed, OSError, ValueError) as exc:
        print_line(f"[e2e] cancel failed (best-effort): {type(exc).__name__}: {exc}")


def wait_for_job(
    *,
    mcp: MCPWebSocketClient,
    job_id: str,
    tail_thread: threading.Thread | None,
    config: JobWaitConfig,
) -> str:
    """轮询 job 状态直到结束或超时。"""
    deadline = time.time() + float(config.timeout_seconds)
    last_term_off = 0

    while True:
        # MCP 轮询状态：后端返回的 payload 是 dict（包含 status 字段）。
        state = mcp.call_tool(name="job.get_state", arguments={"job_id": job_id})
        if not isinstance(state, dict):
            raise APIRequestFailed("mcp job.get_state returned invalid payload")
        status = str(state.get("status") or "")

        if config.tail_terminal and tail_thread is None:
            # Fallback: local tail when MCP tail thread isn't running.
            last_term_off = tail_terminal_log_local(
                jobs_root=config.jobs_root,
                job_id=job_id,
                last_offset=last_term_off,
            )

        if status in ("succeeded", "failed", "cancelled"):
            return status

        if time.time() > deadline:
            print_line("[e2e] timeout, cancelling job...")
            cancel_job_best_effort(mcp=mcp, job_id=job_id)
            return "timeout"

        time.sleep(float(config.poll_seconds))


def fetch_report_json(*, mcp: MCPWebSocketClient, job_id: str) -> dict[str, Any]:
    """通过 MCP 拉取 `report.json` 并返回解析后的 dict。"""
    artifacts = mcp.call_tool(name="job.get_artifacts", arguments={"job_id": job_id, "names": ["report.json"]})
    items = (artifacts or {}).get("items") if isinstance(artifacts, dict) else None
    report = items.get("report.json") if isinstance(items, dict) else None
    if not isinstance(report, dict):
        raise APIRequestFailed("mcp report.json missing")
    return report


def main() -> int:
    args = parse_args()

    api_base = str(args.api_base)
    model = str(args.model).strip()
    if not model:
        print_line("[e2e] missing --model")
        return 2

    print_line(f"[e2e] api_base={api_base}")
    print_line(f"[e2e] model={model} search_mode={args.search_mode}")

    user_token, username = prepare_user_token(args=args, api_base=api_base, model=model)
    print_line(f"[e2e] user signup ok: {username}")
    return run_and_verify_knapsack_job(args=args, api_base=api_base, model=model, user_token=user_token)


def prepare_user_token(*, args: E2EArgs, api_base: str, model: str) -> tuple[str, str]:
    with httpx.Client(timeout=30.0, trust_env=False) as client:
        # 1) 管理员登录：用于启用 pricing（某些环境默认未配置定价）。
        admin_token = login_admin(
            client=client,
            api_base=api_base,
            username=args.admin_username,
            password=args.admin_password,
        )
        print_line("[e2e] admin login ok")

        # 2) 保障该 model 可计费（否则 usage_records 可能没有 cost 字段）。
        enable_pricing_for_model(client=client, api_base=api_base, token=admin_token, model=model)
        print_line("[e2e] pricing enabled")

        # 3) 注册普通用户：用其 token 连接 MCP 并创建 job。
        username = f"e2e_knapsack_{now_milliseconds()}"
        user_token = request_access_token(
            client=client,
            api_base=api_base,
            path="/auth/signup",
            body={"username": username, "password": "password-123"},
        )
        return user_token, username


def run_and_verify_knapsack_job(*, args: E2EArgs, api_base: str, model: str, user_token: str) -> int:
    mcp = MCPWebSocketClient(api_base=api_base, token=user_token)
    try:
        # 4) 创建 job（传入 statement + seed code + tests.zip）。
        job_id = create_job_knapsack(mcp=mcp, model=model, search_mode=args.search_mode)
        print_line(f"[e2e] job created: {job_id}")

        # 5) 启动 job。
        mcp.call_tool(name="job.start", arguments={"job_id": job_id})
        print_line("[e2e] job started, waiting...")

        stop_tail = threading.Event()
        tail_thread: threading.Thread | None = None
        if args.tail_terminal:
            # 可选：订阅 MCP 流（agent_status + terminal）用于实时打印。
            tail_thread = threading.Thread(
                target=tail_job_stream_mcp,
                kwargs={"stop": stop_tail, "api_base": api_base, "token": user_token, "job_id": job_id},
                daemon=True,
            )
            tail_thread.start()

        config = JobWaitConfig(
            timeout_seconds=int(args.timeout_seconds),
            poll_seconds=float(args.poll_seconds),
            tail_terminal=bool(args.tail_terminal),
            jobs_root=Path(str(args.jobs_root)),
        )
        final_status = wait_for_job(mcp=mcp, job_id=job_id, tail_thread=tail_thread, config=config)
        if final_status == "timeout":
            return 1
        print_line(f"[e2e] finished: {final_status}")

        stop_tail.set()
        if tail_thread is not None:
            tail_thread.join(timeout=2.0)

        # 7) 拉取 report.json 并给出最终判定。
        report = fetch_report_json(mcp=mcp, job_id=job_id)
        rep_status = str(report.get("status") or "")
        compile_ok = bool((report.get("compile") or {}).get("ok"))
        failed = int(((report.get("summary") or {}).get("failed") or 0))
        print_line(f"[e2e] report.status={rep_status} compile_ok={compile_ok} failed={failed}")

        ok = rep_status == "succeeded" and compile_ok and failed == 0
        if not ok:
            print_line(json.dumps(report, ensure_ascii=False, indent=2))
            return 1

        print_line("[e2e] ✅ knapsack passed")
        return 0
    finally:
        # Best-effort: the process is short-lived; explicit close is not required here.
        pass


if __name__ == "__main__":
    raise SystemExit(main())
