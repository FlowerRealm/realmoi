# 模块：mcp（通信总线：user / judge / codex）

本模块定义本项目中 MCP（Model Context Protocol）在**用户前端**、**独立测评机（judge worker）**与 **Codex/runner** 之间的职责边界、入口、工具命名空间与端到端数据流。

## 目标

- 让 user / judge / codex 三方交互尽可能统一为 “MCP tools + notifications” 模式。
- 除 **Codex 进程生命周期管理（spawn/kill/重试）** 仍由 runner 自己负责外，其余“对外沟通”（状态、日志、产物、测评交互、用量上报）均通过 MCP 完成。

## 入口与角色

### 1) backend WebSocket MCP 网关

- 入口：`GET /api/mcp/ws`
- 鉴权：
  - `user`：JWT（`?token=` 或 `Authorization: Bearer ...`）
  - `judge`：`REALMOI_JUDGE_MCP_TOKEN`（`?token=`）
- `initialize` 会返回：
  - `serverInfo.role = "user" | "judge"`（便于客户端自检与日志排查）

### 2) runner stdio MCP server（供 Codex 调用）

- server：`realmoi-status`
- 命令：`python -X utf8 -m realmoi_status_mcp`
- 职责：
  - 接收 Codex 的工具调用（状态、增量、自测）
  - 将结果**落盘到 job 目录的日志文件**（例如 `logs/agent_status.jsonl`）
  - 由后续链路（judge worker → backend → frontend）把这些日志同步给用户

## 工具命名空间（SSOT）

### user tools（JWT）

- `models.list`
- `job.create` / `job.start` / `job.cancel`
- `job.get_state` / `job.get_artifacts`
- `job.get_tests` / `job.get_test_preview`
  - 用于前端展示“样例 / 结果”面板：列出 tests.zip 解包后的 case，并按需读取 input/expected 预览
- `job.subscribe` / `job.unsubscribe`
- notifications：
  - `agent_status`
  - `terminal`

### judge tools（judge token）

- 控制面：
  - `judge.claim_next` / `judge.release_claim`
- 数据面：
  - `judge.input.list` / `judge.input.read_chunk`
  - `judge.job.get_state` / `judge.job.patch_state`
  - `judge.job.append_terminal` / `judge.job.append_agent_status`
  - `judge.job.put_artifacts`
- generate 配置与计费：
  - `judge.prepare_generate`
  - `judge.usage.ingest`

### codex tools（runner stdio MCP）

- `status.update`：写入短状态行（`stage/summary`），用于 UI 时间线
- `agent.delta`：写入结构化增量（`kind/delta/meta`），用于前端实时流
- `judge.self_test`：在隔离临时目录运行 `runner_test.py`（编译+跑 tests），用于 Codex 生成阶段的“先自测再输出”

## 典型端到端流程

### 创建并启动 Job（用户）

1. frontend → `models.list` 获取模型列表
2. frontend → `job.create`（携带 `statement_md`、`tests_zip_b64` 等输入）
3. frontend → `job.start`
4. frontend → `job.subscribe(streams=["agent_status","terminal"])` 接收实时通知
5. frontend → `job.get_tests` / `job.get_test_preview`（展示用户上传的样例输入/输出；结果来自 `report.json`）

### 独立测评机执行（judge worker）

1. judge → `judge.claim_next` 抢占一个 `queued` Job
2. judge → `judge.input.list/read_chunk` 下载 `input/`
3. judge 本地执行 `JobManager(generate → test)`
4. judge → `judge.job.append_terminal/append_agent_status` 回传实时日志
5. judge → `judge.job.patch_state` 同步 `state.json`
6. judge → `judge.job.put_artifacts` 上传 `main.cpp/solution.json/report.json`
7. judge → `judge.usage.ingest` 上报 `usage.json`（并入库 `usage_records`）
8. judge → `judge.release_claim` 释放抢占锁

### Codex 与外界沟通（runner）

- `runner_generate.py` / `runner_test.py` 会通过 runner stdio MCP tools 写入 `logs/agent_status.jsonl`
- judge worker 会把 `logs/agent_status.jsonl` 变化同步为 `judge.job.append_agent_status`
- frontend 通过 `job.subscribe` 收到 `agent_status` 通知并实时渲染

## 约束与注意

- `REALMOI_JUDGE_MCP_TOKEN` 视为高权限密钥：仅部署侧配置，不应暴露给前端或普通用户。
- user 工具访问控制：
  - 默认仅允许访问 `owner_user_id` 属于自己的 job
  - `admin` 角色可访问全量 job（用于运维与排障）

## 参考实现

- `scripts/e2e_knapsack.py`：REST 仅用于获取 JWT；Job 全流程（create/start/get_state/get_artifacts + subscribe 实时输出）通过 MCP 完成。
