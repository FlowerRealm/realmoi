# 模块：runner（Docker 镜像 + 生成/测试脚本）

## 镜像

- 构建文件：`runner/Dockerfile`
- 镜像名（默认）：`realmoi-runner:dev`
- Docker 发布镜像（部署默认）：`realmoi/realmoi-runner:latest`（可按环境变量覆盖）
- 主要组件：
  - Node 22 + `@openai/codex`（Codex CLI 0.98.0）
  - `g++`（C++20 编译）
  - Python 3（runner 脚本 + MCP server）

## 入口与模式

- 入口：`runner/app/run.sh`
- 通过环境变量 `MODE` 选择执行：
  - `MODE=generate` → `runner/app/runner_generate.py`
  - `MODE=test` → `runner/app/runner_test.py`

## 输入契约

- 宿主机挂载 job 目录到容器：`/job`
- `runner_generate.py` 读取：`/job/input/job.json`
- `runner_test.py` 读取：`/job/input/job.json` + `/job/output/main.cpp`

## 输出契约（核心交付物）

- `main.cpp`：最终 C++20 单文件解法
- `solution.json`：结构化说明
  - `solution_idea`：最终算法思路
  - `seed_code_idea`：用户原代码思路复盘（如提供）
  - `seed_code_bug_reason`：用户原代码错误原因
  - `user_feedback_md`：面向用户的反馈（按“思路错误/思路正确但有瑕疵”输出）
  - `seed_code_issue_type`：用户代码问题类型（`wrong_approach` / `minor_bug` / `no_seed_code`）
  - `seed_code_wrong_lines`：关键错误行号（1-based，仅 `minor_bug`）
  - `seed_code_fix_diff`：统一 diff（仅 `minor_bug`，由模型输出的“补丁 diff”）
  - `seed_code_full_diff`：统一 diff（runner 计算的“全量 diff”，对比 seed→最终 `main.cpp`，用于前端差异视图）
- `report.json`：编译/测试结构化报告（compile_only / compile_and_test）
  - test 阶段首先写入：`output/artifacts/attempt_{n}/test_output/report.json`
  - 后端会复制为：`output/report.json`（便于前端稳定读取）
  - `tests[]` 每条用例会记录 `verdict/time_ms/memory_kb/stdout_b64/stderr_b64/diff`（用于前端“样例 / 结果”面板展示；`memory_kb` 来自 `wait4().ru_maxrss`，单位 kB）
- `usage.json`：从 Codex JSONL 事件解析 usage（含 cached_input/cached_output）

## Search 模式

- `job.json.search_mode`：
  - `disabled`：`codex exec --config web_search=disabled ...`（禁用 Search）
  - `cached`：`codex exec --config web_search=cached ...`（使用缓存索引；在 full-access/yolo 场景下需显式覆盖默认 live）
  - `live`：`codex exec --search ...`（实时检索）

## Codex 通道（实时流）

- 新增环境变量：`REALMOI_CODEX_TRANSPORT`
  - `appserver`（默认）：优先使用 `codex app-server`，消费 `item/reasoning/*delta`、`item/agentMessage/delta`、`item/commandExecution/outputDelta`
  - `exec`：回退旧链路 `codex exec --json`
  - `auto`：优先 appserver，失败后自动回退 exec
- appserver 模式会把结构化增量写入 `logs/agent_status.jsonl`（`kind` + `delta`），前端可获得真正实时思考/执行过程
- 思考增量现在会附带 `meta.summary_index`，并透传 `item/reasoning/summaryPartAdded` 为 `kind=reasoning_summary_boundary`（用于前端断句边界）
- appserver 事件解析已兼容 `camelCase/snake_case` 双命名（如 `item/agentMessage/delta` + `item/agent_message/delta`），并支持 `codex/event/agent_message_*` 回退提取
- 在 `turn/completed` 时 runner 会从 `turn` payload 再次兜底提取最终 assistant 文本，避免“Codex 内部已完成但外部 last_message 为空”
- appserver 失败时，runner 会输出 fallback 日志并自动切回 exec，保证可用性

## 思考量（Reasoning Effort）

- `job.json.reasoning_effort`：
  - 支持 `low/medium/high/xhigh`
  - runner 会在调用 Codex 时追加 `--config model_reasoning_effort=<value>`
  - 若字段缺失或值非法，runner 自动回退为 `medium`

## 提示词与重试

- generate：要求仅输出符合 JSON Schema 的单个 JSON 对象，必须包含 `main_cpp`
- repair：结合 `report.json` 摘要对生成代码做“整文件修复”，同样只输出一个 JSON 对象并包含 `main_cpp`
- 补充说明字段：
  - prompt 会引导 Codex 额外输出 `solution_idea/seed_code_idea/seed_code_bug_reason` 与“面向用户的反馈”字段
  - runner 会把这些字段（如存在）摘取落盘到 `output/solution.json`，供前端展示/下载
- Schema 约束（以代码为准）：
  - `runner/schemas/codex_output_schema.json` 当前仅强制 `main_cpp`（`additionalProperties=true`，允许附带更多字段）
- 重试策略：
  - runner 内：infra 重试（退避）+ format 重试（要求严格 JSON 输出）
  - backend 外层：quality 重试（generate+test）→ repair prompt

## 状态回传（agent_status.jsonl）

- 写入目标：`/job/logs/agent_status.jsonl`（local executor 下为 `${REALMOI_JOB_DIR}/logs/agent_status.jsonl`，供后端 MCP `job.subscribe` 订阅后转发通知到前端）
- appserver 模式：
  - runner 解析 `codex app-server` 增量事件，并通过 MCP 工具写入 `kind=... delta=...` 行（真正实时的思考/执行/结果流）
- test 模式：
  - `runner_test.py` 也会通过 MCP 工具 `status.update` 写入测试阶段状态（开始/编译/进度/通过/失败），确保用户在 `job.subscribe` 的 `agent_status` 通知流中能看到“测试中”的过程与结果
- MCP（Codex ↔ 外界沟通）：
  - base config 内置 stdio MCP server：`runner/app/realmoi_status_mcp.py`
  - 提供工具：
    - `status.update`：写入短状态行（`stage/summary`），用于 UI 时间线
    - `agent.delta`：写入结构化增量（`kind/delta/meta`），用于前端实时流
    - `judge.self_test`：在隔离临时目录运行 `runner_test.py`（编译+跑 tests），返回 `ok/status/first_failure_*`，并额外写入一条 UI 状态提示（通过/未通过）
  - 当 `tests.present=true` 时，runner 提示词会要求 Codex 在输出最终 JSON 前先调用 `judge.self_test` 并循环修复直至通过
