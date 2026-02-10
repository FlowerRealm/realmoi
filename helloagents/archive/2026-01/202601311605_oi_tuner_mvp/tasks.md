# 任务清单：OI 调题助手（MVP）

> **@status:** completed | 2026-02-01 08:49

## 0. 当前功能表（截至 2026-02-01，代码已落地）

- [√] 多用户系统：开放注册、JWT 登录、`user/admin` 角色、管理员用户管理/重置密码
- [√] Job 会话：创建/启动/取消/列表/详情；job 目录持久化；服务重启后 reconcile（根据 state.json + 容器状态）
- [√] Runner：`realmoi-runner` Docker 镜像（Codex CLI 0.92.0 + g++ C++20 + Python）
- [√] 两阶段容器：
  - generate：联网 + 注入 `/codex_home/config.toml` + `/codex_home/auth.json`（Key 对用户不可见）
  - test：`--network=none` + `read_only` + `tmpfs` + CPU/内存/pids/ulimit 限额
- [√] 实时终端：后端落盘 `terminal.log` + SSE `terminal.sse`；前端 xterm.js 回放（offset 断线续传）
- [√] MCP 状态回传：Codex 调用 MCP tool `realmoi_status_update` → 写入 `agent_status.jsonl` → SSE `agent_status.sse`
- [√] 用量与计费：从 generate 阶段 JSONL usage 汇总 input/output/cached_* tokens；本地按 `model_pricing` 四类单价计算 cost
- [√] 模型配置：管理员从上游 `/v1/models` 拉取参考，本地启用/配置价格；用户仅能选择已启用模型
- [√] 用户 Codex 配置：每用户 `overrides_toml` 编辑 + `effective_config_toml` 预览（白名单键）
- [√] tests.zip 安全解包：zip slip/软链接/zip bomb（文件数/大小/深度）限制；解包到临时目录校验后再搬运
- [√] 自动清理：`scripts/cleanup_jobs.py`（TTL=7天），用于系统 cron（每天 00:00）

## 0.1 仍可改进（可选）

- [ ] 为 `job/state/report/solution/usage` 提供 JSON Schema 文件并在写入/读取时校验（前端更稳）
- [ ] 用户并发/资源配额（限速/额度/队列）
- [ ] 支持 SPJ/交互题/多文件工程模板

## A. 默认配置（已确定）

- [√] 执行模式：默认两阶段同镜像（generate → test）；单容器作为调试/兼容选项
- [√] Search：默认 `cached`；允许切换 `live/disabled`；Search 缓存由 Codex/上游侧管理，本系统不做缓存
- [√] 模型：用户创建 job 时手动选择（从可用模型列表获取；普通用户不可直接输入任意字符串）
- [√] 交付物：默认 `main.cpp + solution.json + report.json`
- [√] 测试数据：支持上传 `tests/` 目录或 `tests.zip`（解包到 `tests/`）
- [√] 保留策略：容器结束后保留 7 天并自动清理
- [√] 清理触发：system cron（每天 00:00）
- [√] 用户与权限：`user/admin` 两角色；默认开放注册；admin 可管理用户（禁用/重置密码/可选提升权限）
- [√] 访问控制：job 默认私有，仅 owner 与 admin 可访问（后续可引入 `share_token`）
- [√] 用量与计费：Token 从上游 usage 拉取并缓存；价格本地配置并计算 cost（不做本地估算）

## A1. 安全基线（高优先级必须补齐）

- [ ] 资源上限（DoS 防护）：
  - [ ] test 容器：CPU/内存/pids/ulimit/rootfs 只读/no-new-privileges/无网
  - [ ] runner：单用例超时、stdout/stderr 输出量上限、terminal.log 上限（超限标记到 report）
  - [ ] 后端：用户传入的 time/memory 必须 clamp 到服务端最大值
- [ ] tests.zip 解包安全：
  - [ ] 解包到临时目录 → 校验（zip slip/软链接/zip bomb/文件数与总大小）→ 再搬运到 `input/tests/`
  - [ ] 增加可配置限制：`REALMOI_TESTS_MAX_FILES/MAX_UNCOMPRESSED_BYTES/MAX_SINGLE_FILE_BYTES/MAX_DEPTH`
- [ ] 密钥泄露与提示词注入防护（generate 阶段）：
  - [ ] prompt 硬化：明确“不得读取/打印 `$CODEX_HOME` / 环境变量 / 系统信息”，忽略题面中的注入指令
  - [ ] 日志脱敏：终端流与 artifacts 写盘前，对已知 `OPENAI_API_KEY` 精确替换 + 形态学二次脱敏
  - [ ] 产物扫描：`main.cpp/solution.json/report.json` 中若检测到 key（至少精确匹配），置失败 `secret_leak_detected`
- [ ] 数据契约 v1（前端稳定解析）：
  - [ ] 为 `state/job/report/solution/usage` 补齐 `schema_version` 与枚举/错误码定义
  - [ ] 提供 JSON Schema 文件（建议 `schemas/*.json`），并在 runner/后端写入与读取时做校验

## B. Runner 镜像（最小可用）

- [ ] `Dockerfile`：基于 Debian/Ubuntu slim，安装 `g++/make/python3` 与必要工具（bash/curl/ca-certificates/coreutils）
- [ ] Codex CLI：在镜像内安装可执行文件（建议固定版本；提供 `codex --version` 校验步骤）
- [ ] Codex CLI 兼容性 smoke test（构建期/启动期）：
  - [ ] 校验 flags：`codex exec --json/--output-schema/--output-last-message` 是否存在并可用
  - [ ] 校验 Search：`--search` 与 `--enable web_search_request` 是否按预期生效
  - [ ] 校验 config key：`approval_policy/sandbox_mode/forced_login_method/cli_auth_credentials_store/history.../mcp_servers`（以固定版本为准）
- [ ] Runner 入口：提供稳定入口 `/app/run.sh`（或等价脚本），支持 `MODE=generate|test`
- [ ] 目录契约：验证 `/job/input/job.json` 存在；输出写入 `/job/output/`
  - [ ] `$CODEX_HOME` 约定：后端在启动 generate 容器前拷贝 `config.toml` + `auth.json` 到容器内，并设置 `CODEX_HOME` 指向该目录（runner 不在容器内生成/持久化密钥）

### B1. generate（Codex 生成 + 解析用量）

- [ ] 读取 `job.json.model/search_mode/problem/seed`
- [ ] 调用 `codex exec`：
  - [ ] 强制 `--json` 输出 JSONL（用于解析 usage）
  - [ ] 使用 `--output-schema`（固定 schema 文件路径）确保最后消息为 JSON（便于稳定提取 `main_cpp` + 诊断/思路字段）
  - [ ] 使用 `--output-last-message` 保存最后消息到 artifacts（避免 stdout 解析失败导致丢失）
  - [ ] 传递 model：`-m "{job.model}"`
  - [ ] 传递搜索模式（由 `job.search_mode` 映射；与 Codex CLI 官方一致）：
    - [ ] `disabled`：不启用 web search（默认；不传 `--search`，也不 `--enable web_search_request`）
    - [ ] `cached`：`codex exec --enable web_search_request ...`（不传 `--search`；由 Codex/上游侧返回缓存/索引结果）
    - [ ] `live`：`codex --search exec ...`（启用实时 web search）
  - [ ] 环境变量：`OPENAI_BASE_URL`（Key 不通过 env 传递，改用 `$CODEX_HOME/auth.json`）
- [ ] 生成阶段权限模型（按用户要求）：
  - [ ] 默认“无限权限”：`approval_policy=never` + `sandbox_mode=danger-full-access`
  - [ ] 关键防护依赖：prompt 硬化 + 日志/产物脱敏 + 产物扫描（见 proposal 5.5.3）
- [ ] 终端输出策略：
  - [ ] 用户可读：输出摘要日志（阶段开始/结束、文件写入、错误摘要）
  - [ ] 机器可读：原始 JSONL 另存到 `/job/output/artifacts/codex.jsonl`（不直接刷屏给用户）
- [ ] MCP 状态回传：
  - [ ] 镜像内提供 stdio MCP server：`realmoi-status`（工具：`realmoi_status_update`）
  - [ ] MCP server 写入 `/job/logs/agent_status.jsonl`（JSONL；字段：ts/seq/job_id/attempt/stage/level/progress/summary/meta）
  - [ ] 参数校验：stage enum + level enum + summary 长度（≤200）+ attempt>=1 + progress 0~100；敏感信息脱敏
  - [ ] 去重/限流：1s 内相同 stage+summary 合并（防刷屏）
  - [ ] MCP 协议：实现 MCP JSON-RPC（stdio）最小子集：
    - [ ] `initialize` → 返回 `capabilities.tools` + `serverInfo`（name/version）
    - [ ] `ping` → 返回空 result
    - [ ] `tools/list` → 返回 1 个 tool（`realmoi_status_update`，含 inputSchema）
    - [ ] `tools/call` → 仅支持 `realmoi_status_update`，成功返回 `content=[{type:\"text\",text:\"ok\"}]` + 可选 `structuredContent`（含写入 seq）
    - [ ] `notifications/initialized` → 可忽略
  - [ ] 启动方式：通过系统生成并拷贝进容器的 `config.toml` 固定配置 `[mcp_servers.realmoi-status]`（用户配置不可覆盖），避免每次运行 `codex mcp add/remove`
  - [ ] Prompt 强制：在 analysis/plan/coding/repair/done/error 阶段调用 tool（仅简要摘要）
- [ ] 解析 JSONL（容错实现）：
  - [ ] 获取 `codex_thread_id`（优先来自 `thread.started.thread_id`；缺失则留空）
  - [ ] 汇总 `turn.completed.usage`（允许多次出现）：`input/cached_input/output/cached_output`
  - [ ] 记录 `model`（优先来自事件；缺失则使用 `job.json.model`）
- [ ] 写出 `/job/output/main.cpp`（从 Codex 最终产物中抽取；严格保证是单文件 C++）
- [ ] 写出 `/job/output/solution.json`（从 Codex 最终 JSON 中抽取除 main_cpp 外的字段，原样保存便于前端展示）
- [ ] 写出 `/job/output/usage.json`（仅 tokens；cost 可不在 runner 计算，交由后端落库计算）
- [ ] 提取策略（按优先级）：
  - [ ] 解析 `last_message.json` 的 `main_cpp`
  - [ ] fallback：从最后消息中提取 ```cpp 代码块
  - [ ] 若都失败：记为 `invalid_output_format` 并进入 format retry
- [ ] 失败策略：任何异常都应在终端输出“可读错误摘要”，并以非 0 退出码结束 generate 容器

### B1.1 提示词与重试（Runner 内部策略）

- [ ] Prompt v1（generate）：将“只输出 JSON + main_cpp + 思路/诊断字段”的硬约束写死（参考 proposal 5.3）
- [ ] Prompt v1（repair）：包含 `report.json` 的失败摘要 + 用户当前代码（seed.current_code_cpp）+ 当前 main.cpp，要求输出完整替换版
- [ ] 重试分类与上限（建议）：
  - [ ] infra retry：上游超时/5xx/限流 → 指数退避最多 3 次（unauthorized 不重试）
  - [ ] format retry：输出不合规（无 JSON/main_cpp）→ 最多 2 次
  - [ ] quality retry：编译/测试失败 → 最多 2 轮 repair（每轮 repair 后重跑 test）
- [ ] attempt 归档：每次尝试写入 `/job/output/artifacts/attempt_{n}/`（codex.jsonl/last_message/main.cpp/solution.json/report.json）

### B2. test（无网编译与运行）

- [ ] 启动方式：宿主机以 `docker run --network=none` 运行同镜像，`MODE=test`
- [ ] Docker 资源限制（必须）：`--cpus/--memory/--memory-swap/--pids-limit/--ulimit/--read-only/--tmpfs/--cap-drop/--security-opt no-new-privileges`
- [ ] 磁盘写入防护（必须）：运行用户程序时切换到非 root 用户，并确保其对 `/job` 无写权限（仅允许写 `/tmp` 的受限 tmpfs）
- [ ] 编译：`g++ -std=c++20 -O2 -pipe -static?`（按镜像能力决定；MVP 可先动态链接）
- [ ] 运行：按 `job.json.tests` 枚举全部用例，记录每例 stdout/stderr/exit_code/time_ms（不因首个失败提前退出）
- [ ] 超时：实现时间限制（最小实现可用 `timeout`/subprocess 超时）
- [ ] 输出上限：stdout/stderr 合计超过阈值即终止用例并标记 `OLE`
- [ ] 输出对比：实现 `compare.mode=tokens|trim_ws|exact`
- [ ] report.json：按既定 schema 输出（含截断预览 + truncated 标记）
- [ ] artifacts：保存完整 stdout/stderr 与 diff 文件到 `/job/output/artifacts/`

## C. 后端（极简 Docker 编排 + 日志流）

- [ ] 项目初始化：FastAPI + 配置加载（env → settings）
- [ ] 数据目录：`data/`、`jobs/`、`logs/` 自动创建（若不存在）
- [ ] SQLite：接入并提供迁移方案（建议 Alembic；至少要有可重复的建表脚本）

### C1. 认证与用户（RBAC）

- [ ] users 表：字段与索引按 proposal 定义
- [ ] Auth API：`/api/auth/signup|login|me`（JWT HS256）
- [ ] 密码哈希：bcrypt/argon2（参数固化）
- [ ] 禁用策略：每次鉴权都校验 `is_disabled`
- [ ] Admin 用户 bootstrap：仅当 DB 中不存在 admin 时创建（env 提供初始账号）
- [ ] Admin Users API：`GET/PATCH/RESET_PASSWORD`（含“不可禁用自己/至少保留 1 个未禁用 admin”约束）

### C2. 上游集成（仅服务端持有 key）

- [ ] 配置：`REALMOI_OPENAI_BASE_URL` + `REALMOI_CODEX_API_KEY/REALMOI_OPENAI_API_KEY`
- [ ] 上游 models 代理：`GET /api/admin/upstream/models`
  - [ ] 请求上游：`GET {REALMOI_OPENAI_BASE_URL}/v1/models`
  - [ ] 失败映射：`upstream_unauthorized|upstream_unavailable`
  - [ ] 60s 内存缓存（建议）

### C3. 模型与价格（本地可选模型列表）

- [ ] `model_pricing` 表：`model/currency/unit/is_active` + 四类单价字段
- [ ] Admin Pricing API：
  - [ ] `GET /api/admin/pricing/models`（列表）
  - [ ] `PUT /api/admin/pricing/models/{model}`（upsert：保存价格 + is_active）
  - [ ] 校验：四类价格均为 `>=0` 的整数；缺价格禁止 `is_active=true`
- [ ] User Models API：`GET /api/models` 仅返回 `is_active=true` 且价格完整的模型

### C4. Jobs（会话）与容器编排

- [ ] 目录：`jobs/{job_id}/input|output|logs` 创建
- [ ] job 创建：`POST /api/jobs`（multipart）
  - [ ] 解析字段：`model/statement_md/current_code_cpp/tests_zip/...`
  - [ ] 校验：`model` 必须在 `GET /api/models` 的可选列表中（否则 `invalid_model`）
  - [ ] tests.zip 安全解包：临时目录 → 校验（zip slip/软链接/zip bomb/总大小/文件数/深度）→ 再搬运到 `input/tests/`
  - [ ] 生成 `job.json` 与 `state.json`（写入 `owner_user_id/model/search_mode/limits`）
- [ ] job 列表：`GET /api/jobs`（user 仅自己；admin 可筛选）
- [ ] job 详情：`GET /api/jobs/{job_id}`（返回 state 摘要）
- [ ] start：`POST /api/jobs/{job_id}/start`
  - [ ] generate 容器：有网 + 注入 `OPENAI_BASE_URL`；并在启动前拷贝 `$CODEX_HOME/config.toml` 与 `$CODEX_HOME/auth.json`（auth.json 含 key，对用户不可见）
  - [ ] test 容器：`--network=none` + 不注入 key
  - [ ] 资源限制：`--cpus/--memory/--pids-limit/--ulimit/--read-only/--tmpfs/--cap-drop` 等（见 proposal 5.5）
  - [ ] state 流转：`created→running_generate→running_test→succeeded/failed`
  - [ ] 幂等：running 状态下重复 start 不得重复建容器；终态返回 `already_finished`
  - [ ] 容器标识：name/label 绑定 job_id + stage
- [ ] cancel：`POST /api/jobs/{job_id}/cancel`（停止关联容器并写入 `cancelled`）
  - [ ] 幂等：重复 cancel 不报错；对终态不改变状态
- [ ] artifacts：下载 `main.cpp/solution.json/report.json`

### C5. 终端日志（SSE + 回放）

- [ ] attach：实时跟随容器 stdout/stderr
- [ ] 落盘：追加写入 `jobs/{job_id}/logs/terminal.log`
- [ ] 终端日志上限：超过阈值停止追加并写入“已截断”标记（state/report）
- [ ] 日志脱敏：转发与落盘前替换已知 key（`***`）+ 二次形态学脱敏
- [ ] SSE：`GET /api/jobs/{job_id}/terminal.sse?offset=...`
  - [ ] 先回放历史，再推送新增
  - [ ] 事件：`terminal/status/heartbeat`
- [ ] 拉取式回放：`GET /api/jobs/{job_id}/terminal?offset&limit`

### C5.1 Codex 状态流（MCP 回传，SSE + 回放）

- [ ] 文件：`jobs/{job_id}/logs/agent_status.jsonl`（由 MCP server 写入）
- [ ] SSE：`GET /api/jobs/{job_id}/agent_status.sse?offset=...`
  - [ ] 回放 + 实时推送新增（offset 语义与 terminal 一致）
  - [ ] 事件：`agent_status`（`data={"offset":1234,"item":{ts,seq,job_id,attempt,stage,level,progress,summary,meta}}`）
- [ ] 拉取式回放：`GET /api/jobs/{job_id}/agent_status?offset&limit`
  - [ ] 返回：`{offset,next_offset,items:[...]}`（items 为解析后的 JSON 对象数组）
- [ ] 前端：job 详情页增加“状态时间线/步骤条”（与终端并列显示）

### C6. 用量与计费（以 upstream usage 为准）

- [ ] `usage_records` 表：保存 raw usage + pricing 快照 + `cost_microusd`
- [ ] generate 结束后 ingest：
  - [ ] 后端读取 `/job/output/usage.json`（或直接解析容器内 artifacts）
  - [ ] 写入 `usage_records`（允许同一 job 多条记录）
  - [ ] 计算 cost：四类 tokens × 四类单价（microusd/1m tokens）
- [ ] User API：
  - [ ] `GET /api/jobs/{job_id}/usage`
  - [ ] `GET /api/billing/summary`（day/month 聚合）
- [ ] Admin API：`GET /api/admin/billing/summary`（按用户/模型/时间范围）

### C7. 重启恢复（reconcile）

- [ ] 服务启动扫描 `jobs/*/state.json`
- [ ] 对照 docker 容器 label/name：
  - [ ] 仍在运行 → 可重新 attach
  - [ ] 已退出 → 补写 exit_code/finished_at/status

### C8. 清理（7 天 TTL）

- [ ] `scripts/cleanup_jobs.py`：
  - [ ] 仅清理 `succeeded|failed|cancelled` 且过期的 job
  - [ ] 同步清理仍存在的容器（按 label/container_id）
  - [ ] 幂等 + `--dry-run`
- [ ] cron 文档：每天 00:00 执行示例
- [ ] 约束：清理 job 目录时不得删除 `usage_records/model_pricing`

### C9. 安全与审计（MVP 最小）

- [ ] 上游 key：服务端维护 `auth.json`（对用户不可见），仅在 generate 容器注入；不得写入 job.json/state.json
- [ ] 日志脱敏：对 stdout/stderr 中疑似 key 做替换（`***`）
- [ ] 两阶段隔离：test 阶段无网无 key（默认策略）
- [ ] 容器保留策略：不要 `--rm`；退出后由后端/cron 清理统一回收（保证 reconcile）

### C10. 用户配置（Codex config.toml，可视化编辑）

- [ ] DB：新增 `user_codex_settings`（或等价表）存储 `user_overrides_toml/updated_at`
- [ ] API：
  - [ ] `GET /api/settings/codex`：返回 `user_overrides_toml/effective_config_toml/allowed_keys`
  - [ ] `PUT /api/settings/codex`：保存 overrides，TOML 解析与 disallowed key 校验（返回最新 effective）
- [ ] 合成策略：base config（系统强制）+ user overrides（白名单）→ 生成容器前拷贝入 `$CODEX_HOME/config.toml`

## D. 前端（表单 + 终端 + 产物）

- [ ] 项目初始化：Next.js + TS + 基础 UI 框架（任选：shadcn/ui 或 AntD 等）
- [ ] API Client：统一封装（自动附带 JWT；统一错误处理与 toast）

### D1. 用户侧（User）

- [ ] 登录/注册页：对接 `/api/auth/signup|login`，保存 token
- [ ] Jobs 列表页：`GET /api/jobs`（仅我的）
  - [ ] 列表字段：job_id/status/model/created_at/finished_at/expires_at
  - [ ] 快捷操作：进入详情、（可选）在列表取消 running job（需二次确认）
- [ ] 创建 Job 页（表单）：
  - [ ] 模型下拉：`GET /api/models`
    - [ ] 空态：无模型时提示“请联系管理员启用模型并配置价格”
  - [ ] 题面输入：Markdown 文本框
  - [ ] 当前代码：可选（C++）
  - [ ] tests.zip 上传：可选
  - [ ] 参数：search_mode/compare_mode/limits
  - [ ] 创建后自动开始：默认开启（创建成功后自动调用 `/start`，失败则停留在详情页提示）
  - [ ] 提交：`POST /api/jobs`，创建后跳转详情页
  - [ ] 错误态：401 跳登录；`invalid_model` 刷新 models 并提示
- [ ] Job 详情页：
  - [ ] Header：状态徽章 + model/search_mode/created/finished/expires + Start/Cancel/Download
  - [ ] Tabs：Terminal / 状态 / 思路 / 报告 / 代码 / 用量
  - [ ] Terminal：
    - [ ] 订阅 `terminal.sse`（offset=byte offset；断线续传）
    - [ ] offset 持久化：localStorage（按 job_id 存 terminal_offset）
    - [ ] 连接状态：已连接/重连中/已断开
    - [ ] 自动滚动开关（默认开）；支持“暂停自动滚动”提示
    - [ ] 复制：提供“复制最近 N 行”按钮（避免全量复制卡死）
  - [ ] 状态（Agent）：
    - [ ] 订阅 `agent_status.sse`（offset 持久化：localStorage 按 job_id 存 agent_offset）
    - [ ] 步骤条映射：analysis/plan/search/coding/repair/done/error
    - [ ] 展示 level/progress/summary；按 seq 排序去重
  - [ ] 报告（Report）：
    - [ ] 拉取并解析 report.json（compile ok/错误预览；tests summary；用例表；diff 预览）
    - [ ] 失败定位：滚动并高亮 first_failure
  - [ ] 思路（Solution）：
    - [ ] 拉取并解析 solution.json（seed_code_idea / seed_code_bug_reason / solution_idea / assumptions / complexity；注意：默认不包含 main_cpp）
    - [ ] 展示：用户代码思路复盘 + 错误原因诊断 + 最终解法思路摘要
    - [ ] 失败回退：solution.json 解析失败时展示原始文本；404/已清理时展示空态提示
  - [ ] 代码（main.cpp）：
    - [ ] 预览（只读）+ 一键复制 + 下载
  - [ ] 用量（Billing）：
    - [ ] `GET /api/jobs/{job_id}/usage`（四类 tokens + cost）
    - [ ] `pricing_missing`：提示“未配置价格，无法计算成本”
  - [ ] 到期/已清理空态：
    - [ ] 若 job 文件已清理：终端/报告/代码不可用时给出明确提示
    - [ ] 用量仍可展示（来自 DB）
- [ ] 用量汇总页：`GET /api/billing/summary`（day/month）
  - [ ] 维度：按日/月图表 + 汇总卡片（tokens 四类 + cost）

### D1.1 用户设置：Codex 配置（每用户一份）

- [ ] 新增 Settings 页面（或在 Profile 下）：展示并编辑 `user_overrides_toml`
- [ ] 可视化编辑（优先）：对 allowed_keys 提供表单控件（下拉/开关/数字）
- [ ] 高级模式（可选）：直接编辑 TOML 文本（保存前做语法校验）
- [ ] 展示只读 `effective_config_toml` 预览（不包含任何 key）

### D2. 管理员侧（Admin）

- [ ] Admin 导航与路由守卫：`me.role=admin` 才显示/可访问
- [ ] Dashboard：用户数/运行中 job/今日用量与成本（聚合接口复用）
- [ ] Users：
  - [ ] 列表 + 搜索：`GET /api/admin/users`
  - [ ] 禁用/启用：`PATCH /api/admin/users/{id}`
  - [ ] 重置密码：`POST /api/admin/users/{id}/reset_password`
- [ ] Jobs：
  - [ ] 列表：`GET /api/jobs`（admin 视角 + 过滤 owner/status/model）
  - [ ] 详情：终端/状态/产物/用量（复用用户侧组件）
  - [ ] 取消：`POST /api/jobs/{job_id}/cancel`
- [ ] Models & Pricing：
  - [ ] 列表：`GET /api/admin/pricing/models`
  - [ ] 从上游导入（弹窗）：
    - [ ] 拉取：`GET /api/admin/upstream/models`（来自 `/v1/models`）
    - [ ] 搜索与选择；标注“已配置/未配置”
  - [ ] 价格表单（四类单价必填，整数 microusd/1m）
  - [ ] 保存/启用/禁用：`PUT /api/admin/pricing/models/{model}`
- [ ] Billing：
  - [ ] 全站汇总：`GET /api/admin/billing/summary`
  - [ ] 支持按用户/模型/时间过滤与图表展示

## E. 验证与交付

- [ ] 单元测试（后端）：
  - [ ] 计费计算：四类 tokens × 单价 → `cost_microusd`（边界：0、超大、round）
  - [ ] 权限：user/admin 访问控制（job 私有）
  - [ ] 模型：`GET /api/models` 仅返回可选项；`invalid_model` 校验
- [ ] 集成演示脚本（最小）：
  - [ ] admin 导入模型并配置价格/启用
  - [ ] user 创建 job 选择模型并启动
  - [ ] 终端可实时观看；结束后可下载产物；usage/cost 可查询
- [ ] 错误路径演示：
  - [ ] 上游 key 无效（`upstream_unauthorized`）
  - [ ] 上游超时（`upstream_unavailable`）
  - [ ] 编译失败/运行失败可观测（terminal + report）
- [ ] 文档：README（启动方式、环境变量、目录约定、cron 清理、两阶段安全说明）
