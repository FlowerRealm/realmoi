# Changelog

本项目使用语义化版本号（SemVer），并遵循 Keep a Changelog 的组织方式记录变更。

## [0.2.124] - 2026-02-16

### 修复

- **[frontend/auth]**: `/login`、`/signup` 的输入框前缀图标不再与占位文字重叠（强制 `padding-left` 优先级，避免被基础样式覆盖）

### 维护

- **[repo/git]**: 推送变更到 `origin/master`
  - ⚠️ EHRB: 远端主分支变更 - 用户已确认风险
  - 检测依据: `master(分支)` + 语义判定（推送到远端主分支）

### 验证

- **[scripts/playwright]**: UI 巡检回归：`output/playwright/ui-audit/20260216_171708/report.md`（66/66 ok，指标全为 0）

## [0.2.123] - 2026-02-16

### 调整

- **[frontend/admin-pricing]**: 模型价格卡片在“未编辑”状态改为纯展示样式（去掉类似输入框的外框），仅在点击“编辑”后才出现表单外观
- **[frontend/admin-pricing]**: 只读态移除 `upstream_channel/currency/unit` 元信息展示，降低噪声与“可编辑错觉”（渠道仅在编辑态的“高级字段”中可改）

### 验证

- **[scripts/playwright]**: UI 巡检回归：`output/playwright/ui-audit/20260216_163411/report.md`（66/66 ok，指标全为 0）

## [0.2.122] - 2026-02-16

### 调整

- **[frontend/admin-users]**: 将 `Admin / Users` 的“右侧管理面板”改为点击列表弹出“管理用户”小窗口（Modal），桌面端列表恢复单栏展示

### 验证

- **[scripts/playwright]**: UI 巡检回归：`output/playwright/ui-audit/20260216_161705/report.md`（66/66 ok，指标全为 0）

## [0.2.121] - 2026-02-16

### 新增

- **[backend/admin-users]**: 新增 `POST /api/admin/users`：管理员创建用户（username/password/role/is_disabled）
- **[frontend/admin-users]**: `Admin / Users` 重新设计并补齐功能：新建用户、角色切换、启用/禁用、重置密码（Modal）+ 右侧管理面板
- **[backend/tests]**: 新增 `test_admin_users.py` 覆盖用户管理接口（create/list/patch/reset_password）

### 调整

- **[backend/admin-users]**: `GET /api/admin/users` 支持 `role` 与 `is_disabled` 过滤参数

### 修复

- **[frontend/admin-users]**: 移动端列表列收敛（隐藏创建时间），避免按钮被裁切；UI 巡检回归 `clip/occluded` 指标清零
- **[tests]**: pytest 继承真实 `jobs/` 快照时忽略 dangling symlinks，避免 `shutil.copytree` 因缺失 target 报错

## [0.2.120] - 2026-02-16

### 修复

- **[frontend/admin-pricing]**: “创建”按钮在窄列下不再自动换行成竖排字（调整表单栅格占比 + `whitespace-nowrap`）
- **[frontend/admin-users]**: `Admin / Users` 页面改为与其它业务页一致的 glass 风格（移除 Semi Card/Table 表现差异，改为自绘表格 + 同款筛选/分页条）

## [0.2.119] - 2026-02-16

### 维护

- **[scripts/playwright]**: `pw_ui_audit.sh` 在默认隔离 `jobs_root` 时自动注入一个样例 Job（从 `jobs/` 复制），避免 `/jobs/[jobId]` 因无数据被标记为 skipped
- **[frontend/playwright]**: UI 巡检截图增加重试，降低偶发 `Page.captureScreenshot` 协议错误导致的 `report.md` error 记录

## [0.2.118] - 2026-02-16

### 修复

- **[frontend/layout]**: 业务页外层由 `overflow-hidden` 调整为 `overflow-x-hidden`，避免内容被截断且保留横向溢出保护（`/billing`、`/settings/codex`、`/admin/*`）
- **[frontend/header]**: `AppHeader` 主导航在窄屏改为横向滚动（不再 wrap），降低顶栏高度波动导致的内容/按钮错位风险
- **[frontend/table]**: `.table-scroll-card` 的卡片 body 增加 `overflow-x: auto`，并将 `Admin / Users` 表格 wrapper 调整为 `overflow-x-auto`，减少移动端表格被裁切/无法横向滚动的问题

### 调整

- **[frontend/playwright]**: UI 巡检报告新增自动信号：overflow 裁切、点击目标遮挡/重叠、按钮行不对齐、文本截断，并在 `report.md` 汇总

### 维护

- **[scripts/playwright]**: `pw_ui_audit.sh` 对输出目录做绝对路径归一化，避免 Playwright 输出落到 `frontend/` 下

## [0.2.117] - 2026-02-16

### 新增

- **[frontend/playwright]**: 新增“全站 UI 巡检”能力（仅 Chromium）：自动发现路由、多视口逐页截图、生成 `report.md` + `report.jsonl`
- **[scripts/playwright]**: 新增一键脚本 `scripts/pw_ui_audit.sh`：自动启动 backend/frontend 并产出巡检报告到 `output/playwright/ui-audit/<timestamp>/`

### 维护

- **[frontend/lint]**: 补齐 `newapi/ratio` 组件的类型声明，修复 `@typescript-eslint/no-explicit-any` 导致的 lint 失败

## [0.2.116] - 2026-02-10

### 调整

- **[frontend/admin-pricing]**: 单条模型改为“默认只读 + 编辑态”交互：点击“编辑”后才可修改字段，提供“保存/取消”并支持取消回滚

### 维护

- **[repo/git]**: 推送变更到 `origin/master`
  - ⚠️ EHRB: 远端主分支变更 - 用户已确认风险
  - 检测依据: `master(分支)` + 语义判定（推送到远端主分支）

## [0.2.115] - 2026-02-10

### 调整

- **[frontend/admin-pricing]**: 重做 `Admin / Pricing` 信息架构与视觉：从宽表格改为卡片式编辑，新增顶部指标、待保存状态、开关交互与缺失字段高亮提示

## [0.2.114] - 2026-02-10

### 修复

- **[runner/report]**: `memory_kb` 改为通过 `wait4().ru_maxrss` 获取，避免在部分环境下读取 `/proc/<pid>/status` 失败导致前端显示 `—`

### 维护

- **[repo/git]**: 推送变更到 `origin/master`
  - ⚠️ EHRB: 远端主分支变更 - 用户已确认风险
  - 检测依据: `master(分支)` + 语义判定（推送到远端主分支）

## [0.2.113] - 2026-02-10

### 调整

- **[frontend/cockpit]**: 样例面板顶部时间指标改为展示“总耗时”（汇总 `tests[].time_ms`），内存继续展示峰值内存

## [0.2.112] - 2026-02-10

### 调整

- **[frontend/cockpit]**: 样例面板顶部指标改为展示实际峰值时间/峰值内存（不再展示 TL/ML 限制）

## [0.2.111] - 2026-02-10

### 调整

- **[frontend/cockpit]**: 样例面板“内存”统一按 MB 单位展示（由 `memory_kb` 转换）

## [0.2.110] - 2026-02-10

### 调整

- **[frontend/cockpit]**: 样例面板按 verdict 整卡变色，移除字节大小与 `exit=...` 展示，新增时间/内存展示（更接近 CPH 插件观感）

### 新增

- **[runner/report]**: `report.json` 的 `tests[]` 新增 `memory_kb`（峰值 RSS 估计）供前端展示“空间”

### 文档

- **[docs]**: 更新 `helloagents/modules/runner.md`、`helloagents/modules/frontend.md` 同步字段与前端展示

## [0.2.109] - 2026-02-10

### 新增

- **[backend/mcp]**: 新增 user tools `job.get_tests` / `job.get_test_preview`，用于拉取 tests.zip 样例输入/输出预览
- **[frontend/cockpit]**: 新增“样例 / 结果”栏（CPH 风格），与代码并列展示 input/expected/actual（stdout）与 verdict/diff

### 测试

- **[tests/backend]**: MCP WS 用例覆盖新 tools（`job.get_tests` / `job.get_test_preview`）

### 文档

- **[docs]**: 更新 `helloagents/modules/mcp.md`、`helloagents/modules/frontend.md` 同步 tool 与 UI

## [0.2.108] - 2026-02-10

### 调整

- **[frontend/cockpit]**: “解读与反馈”改为一条 `assistant` 消息（`messageKey=job-feedback-*`），用于稳定控制其在消息流中的位置

## [0.2.107] - 2026-02-10

### 调整

- **[frontend/cockpit]**: “解读与反馈”移动到左侧 `job-token-*` 的思考过程下方展示，保证与思考内容连续呈现
- **[frontend/cockpit]**: 右侧“差异”视图优先渲染 `seed_code_full_diff`（seed→最终 `main.cpp` 的全量 diff）
- **[runner/artifacts]**: `solution.json` 新增 `seed_code_full_diff`（runner 计算的全量 diff）

### 文档

- **[docs]**: 更新 `helloagents/modules/runner.md`、`helloagents/modules/frontend.md` 同步字段与前端展示行为

## [0.2.106] - 2026-02-10

### 调整

- **[frontend/cockpit]**: 左侧新增“解读与反馈”折叠区展示 `solution.json`；右侧代码面板支持“最终代码/差异”切换，并以图形化 diff 视图展示 `seed_code_fix_diff`；移除默认的“Job 已结束...请查看右侧面板”提示

## [0.2.105] - 2026-02-10

### 调整

- **[runner/prompt]**: generate/repair 提示词新增“面向用户的反馈”输出规范（区分“思路错误 / 思路正确但有瑕疵”，并要求给出错误行号与 diff）
- **[runner/artifacts]**: `solution.json` 落盘新增 `user_feedback_md/seed_code_issue_type/seed_code_wrong_lines/seed_code_fix_diff` 字段
- **[frontend/cockpit]**: Job 终态拉取 `solution.json` 并在右侧面板新增“解读与反馈”折叠区展示；失败 Job 也会尝试拉取 artifacts 便于排查

### 文档

- **[docs]**: 更新 `helloagents/modules/runner.md`、`helloagents/modules/frontend.md` 同步产物字段与前端展示行为

## [0.2.104] - 2026-02-10

### 修复

- **[backend/auth]**: 兼容 `bcrypt` 新版本移除 `__about__` 导致 `passlib` 打印 `(trapped) error reading bcrypt version` 的问题（在 `backend/app/auth.py` 启动时补齐 `bcrypt.__about__.__version__`）

## [0.2.103] - 2026-02-10

### 调整

- **[scripts/e2e]**: `scripts/e2e_knapsack.py` Job 全链路切换为 MCP（create/start/get_state/get_artifacts + subscribe 实时输出）
- **[deployment/docker]**: `docker-compose.yml` 默认启用独立测评机模式并补齐 `REALMOI_JUDGE_MCP_TOKEN` / `REALMOI_JUDGE_API_BASE_URL` 传递
- **[deployment/env]**: `.env.docker.example` 移除过期项并补齐 `REALMOI_JUDGE_MCP_TOKEN` / `REALMOI_JUDGE_WORK_ROOT`
- **[repo/kb]**: `.gitignore` 不再忽略 `helloagents/`（知识库纳入版本管理）

## [0.2.102] - 2026-02-10

### 调整

- **[backend/mcp]**: 用户侧 MCP tools 命名空间化（统一为 `models.*` / `job.*`，与 `judge.*` 对齐）
  - 旧：`realmoi_models_list`、`realmoi_job_*`
  - 新：`models.list`、`job.create/start/cancel/get_state/get_artifacts/subscribe/unsubscribe`
- **[job_manager/env]**: 移除 generate 阶段注入的 HTTP 自测环境变量（当前链路已统一使用 MCP `judge.self_test`）
- **[backend/jobs]**: 移除 HTTP 外部自测接口 `POST /api/jobs/{job_id}/self-test`（统一走 MCP）
- **[backend/jobs]**: 移除 SSE 实时接口 `terminal.sse/agent_status.sse`（统一走 MCP notifications）
- **[backend/settings]**: 移除未使用的 `judge_self_test_timeout_seconds` 配置项

### 前端

- **[frontend/mcp]**: Portal/Cockpit 全量改为调用新 tool 名（并保持订阅通知协议不变）
- **[frontend/cleanup]**: 删除未使用的 `frontend/src/lib/sse.ts`

### 文档

- **[docs]**: 新增 `helloagents/modules/mcp.md`（作为 MCP 通信总线 SSOT）
- **[docs]**: 更新 `helloagents/modules/frontend.md` 同步新 tool 名与 MCP 描述
- **[docs]**: 更新 `helloagents/context.md` 同步 MCP 传输与 runner 版本信息
- **[docs]**: 更新 `README.md`、`helloagents/modules/backend.md`、`helloagents/modules/runner.md` 移除 SSE/HTTP 自测说明，改为 MCP

### 测试

- **[tests/backend]**: 更新 `backend/tests/test_mcp_ws.py` 断言新 tool 名
- **[tests/backend]**: 删除 `backend/tests/test_jobs.py` 中的 HTTP 自测接口用例

## [0.2.101] - 2026-02-09

### 调整

- **[runner/mcp]**: runner stdio MCP tools 命名空间化（更贴近语义、避免 `realmoi_*` 堆叠）
  - 旧：`realmoi_status_update` / `realmoi_agent_delta` / `realmoi_judge_self_test`
  - 新：`status.update` / `agent.delta` / `judge.self_test`

### 测试

- **[tests/runner]**: 更新 `runner_generate` 提示词与调用名称断言

### 文档

- **[docs]**: 更新 `README.md`、`helloagents/modules/runner.md`、`helloagents/modules/backend.md` 同步新 tool 名

## [0.2.100] - 2026-02-09

### 调整

- **[backend/mcp]**: judge MCP tools 改为 `judge.*` 命名空间（统一端点下更清晰）
  - 旧：`realmoi_judge_*`
  - 新：`judge.*`（例如 `judge.claim_next`、`judge.job.put_artifacts`）
- **[judge/daemon]**: 独立测评机调用的 tool 名称同步更新

### 测试

- **[tests/backend]**: 更新 `MCP judge` 用例断言与调用名称

### 文档

- **[docs]**: 更新 `README.md` 与 `helloagents/modules/backend.md` 同步 tool 命名空间

## [0.2.99] - 2026-02-09

### 调整

- **[backend/mcp]**: 合并用户侧 MCP 与 judge MCP 为单一 WebSocket 端点
  - 统一入口：`GET /api/mcp/ws`
  - 鉴权：用户使用登录 JWT；judge worker 使用 `REALMOI_JUDGE_MCP_TOKEN`
- **[backend/mcp]**: 代码结构整理：judge MCP tools/session 从 `routers/` 迁移到 `services/`（路由仅保留统一入口）
- **[judge/daemon]**: 独立测评机连接地址改为 `/api/mcp/ws`（不再使用 `/api/mcp/judge/ws`）

### 测试

- **[tests/backend]**: 更新 MCP judge 用例改为通过统一 `/api/mcp/ws` 覆盖

### 文档

- **[docs]**: 更新 `README.md` 与 `helloagents/modules/backend.md` 同步统一入口

## [0.2.98] - 2026-02-09

### 新增

- **[backend/mcp-judge]**: 为独立测评机补齐 generate 阶段的“配置与计费”MCP 工具
  - tools：`realmoi_judge_prepare_generate`（返回 `effective_config_toml` + `auth_json` + `openai_base_url`）
  - tools：`realmoi_judge_usage_ingest`（写回 `usage.json` 并入库 `usage_records`）

### 调整

- **[judge/daemon]**: 独立测评机不再直接访问 DB / 密钥 / 计费逻辑
  - generate 配置通过 MCP tool `realmoi_judge_prepare_generate` 获取（backend 为密钥与渠道配置真源）
  - 用量通过 MCP tool `realmoi_judge_usage_ingest` 上报（backend 负责入库与费用计算）
- **[job_manager]**: `JobManager` 支持注入 `generate_bundle_provider` 与 `usage_reporter`，方便独立 judge 复用执行逻辑

### 测试

- **[tests/backend]**: 扩展 `MCP judge ws` 用例覆盖 prepare_generate + usage_ingest，并新增 provider 注入“避免 DB 访问”用例

### 文档

- **[docs]**: 更新 `README.md` 与 `helloagents/modules/backend.md` 同步新增 tools

## [0.2.97] - 2026-02-09

### 新增

- **[backend/mcp-judge]**: 扩展独立测评机 MCP 通道 `GET /api/mcp/judge/ws` 的数据面能力
  - tools：`realmoi_judge_job_get_state` / `realmoi_judge_input_list` / `realmoi_judge_input_read_chunk`
  - tools：`realmoi_judge_job_patch_state` / `realmoi_judge_job_append_terminal` / `realmoi_judge_job_append_agent_status` / `realmoi_judge_job_put_artifacts`
- **[judge/workspace]**: 新增 `REALMOI_JUDGE_WORK_ROOT`（judge 本地 job 临时目录，默认 `/tmp/realmoi-judge-work`）
  - 默认值：local runner → `/tmp/realmoi-judge-work`；docker runner → `{REALMOI_JOBS_ROOT}/.judge-work`

### 调整

- **[judge/daemon]**: 独立测评机执行链路改为“全程通过 MCP 与 backend 交互”
  - 输入：通过 MCP 拉取 `input/`（题面、tests 等）
  - 过程：通过 MCP 回传 `state.json` 变更与实时日志（terminal + agent_status）
  - 产物：通过 MCP 写回 `output/main.cpp/solution.json/report.json`

### 测试

- **[tests/backend]**: 扩展 `MCP judge ws` 用例覆盖 input 下载、日志 append、state patch、产物写回

### 文档

- **[docs]**: 更新 `README.md` 与 `helloagents/modules/backend.md` 同步 MCP judge 数据面 tools 与工作目录配置

## [0.2.96] - 2026-02-09

### 新增

- **[backend/mcp-judge]**: 新增独立测评机 MCP 通道 `GET /api/mcp/judge/ws`
  - tools：`realmoi_judge_claim_next` / `realmoi_judge_release_claim`
  - 鉴权：`REALMOI_JUDGE_MCP_TOKEN`（backend 与 judge 必须一致）

### 调整

- **[judge/daemon]**: `backend/app/judge_daemon.py` 改为通过 MCP 抢占/释放 `queued` Job
  - 不再直接扫描并操作 `jobs/{job_id}/logs/judge.lock`
- **[judge/lock]**: `judge.lock` 增加 `claim_id`，release 改为后端校验 `claim_id`

### 修复

- **[backend/mcp-gateway]**: 修复 MCP 网关读取 `JOB_MANAGER` 时机导致的空指针风险
  - `realmoi_job_start/cancel` 改为运行时从 `singletons.JOB_MANAGER` 取值

### 测试

- **[tests/backend]**: 新增 `MCP judge ws` 抢占/释放用例，并更新 `JobManager` 相关测试

### 文档

- **[docs]**: 更新 `README.md` 与 `helloagents/modules/backend.md` 补充 `MCP judge` 对接方式与环境变量

## [0.2.95] - 2026-02-09

### 新增

- **[backend/mcp-gateway]**: 新增 WebSocket MCP 网关 `GET /api/mcp/ws`
  - tools：`realmoi_job_create/start/cancel/get_state/get_artifacts/subscribe/unsubscribe`、`realmoi_models_list`
  - notifications：`agent_status`（主流）+ `terminal`（回退流）

### 调整

- **[frontend/mcp]**: Portal/Cockpit 的 Job 创建、状态订阅、产物拉取、取消操作改为全部通过 MCP 传输

### 文档

- **[docs]**: 更新 `helloagents/modules/frontend.md` 与 `helloagents/modules/backend.md` 同步 MCP 网关对接方式

## [0.2.94] - 2026-02-09

### 调整

- **[runner/status]**: `runner_test.py` 在 test 阶段通过 MCP 工具 `realmoi_status_update` 回传状态
  - 覆盖编译/进度/通过/失败，确保 `agent_status.sse` 能实时展示测试过程

### 文档

- **[docs]**: 更新 `helloagents/modules/runner.md` 与 `helloagents/modules/backend.md` 同步测试阶段状态流说明

## [0.2.93] - 2026-02-09

### 新增

- **[mcp/judge-self-test]**: runner MCP 新增自测工具 `realmoi_judge_self_test`
  - Codex 可通过 MCP 触发隔离自测（编译 + 跑 tests），并获取 `ok/status/first_failure_*` 摘要
- **[mcp/agent-delta]**: runner MCP 新增增量写入工具 `realmoi_agent_delta`
  - 用于写入结构化实时流（`kind/delta/meta`），供前端展示思考/执行/结果增量

### 调整

- **[codex/config]**: Codex base config 的 MCP server 改为 `python -m realmoi_status_mcp`，同时支持 Docker runner 与 local runner
- **[codex/config]**: MCP tool 超时上调（避免自测时间较长时被提前中断）
- **[runner/prompt]**: 当 `tests.present=true` 时，提示词改为要求调用 MCP 工具 `realmoi_judge_self_test`（不再注入 HTTP 自测模板）
- **[mcp/job-dir]**: `realmoi_status_mcp.py` 支持从 `REALMOI_JOB_DIR` 定位 job 目录（local executor 可用）
- **[runner/status]**: `runner_generate.py` 的 agent_status 写入改为全部通过 MCP 工具完成（避免多处直写 jsonl）

### 文档

- **[docs]**: 更新 `README.md` 与 `helloagents/modules/*` 同步 MCP 自测用法与职责边界

### 测试

- **[tests/runner]**: 更新 `backend/tests/test_runner_generate.py` 的自测提示词断言

## [0.2.92] - 2026-02-09

### 新增

- **[judge/external-api]**: 新增对 Codex 友好的外部自测接口
  - `POST /api/jobs/{job_id}/self-test`
  - 鉴权方式：`X-Job-Token`（`input/job.json` 中 `judge.self_test_token`）
  - 入参：`{"main_cpp":"..."}`，后端在隔离临时目录执行 `runner_test.py` 并返回结构化 `report`
  - 新增服务实现：`backend/app/services/self_test_api.py`

### 调整

- **[runner/prompt]**: `runner_generate` 提示词新增外部自测接口提示（URL + token），便于 Codex 直接 HTTP 调用
- **[job_manager/env]**: generate 阶段自动注入：
  - `REALMOI_JUDGE_SELF_TEST_URL`
  - `REALMOI_JUDGE_SELF_TEST_TOKEN`

### 测试

- **[tests/backend]**: 新增 `test_external_self_test_requires_valid_job_token` 与 `test_external_self_test_returns_report_for_codex`

## [0.2.91] - 2026-02-09

### 新增

- **[judge/independent]**: 新增独立测评机模式（参考 UOJ 的“Web + Judge Worker”解耦思路）
  - `backend/app/settings.py` 新增：
    - `judge_mode`（`embedded` / `independent`）
    - `judge_machine_id`
    - `judge_poll_interval_ms`
    - `judge_lock_stale_seconds`
  - `backend/app/services/job_manager.py` 新增独立队列能力：
    - `start_job` 在 `independent` 模式下写入 `queued` 状态，不在 API 进程内起线程
    - 新增 `claim_next_queued_job()` + `run_claimed_job()`，通过 `logs/judge.lock` 抢占任务
    - 新增 stale lock 清理逻辑，避免 worker 异常退出后任务长期卡死
    - 本地执行 `cancel_job` 增加“按 state 中 PID 杀进程”的跨进程兜底
    - `reconcile` 在独立模式下不再把本地 running 任务直接判定为 `local_process_missing`
  - 新增独立守护进程入口：`backend/app/judge_daemon.py`
    - 轮询 `queued` 任务并执行抢占后的 job
  - `docker-compose.yml` 新增 `judge` 服务，默认以 `independent` 模式运行
  - `frontend/src/components/assistant/Cockpit.tsx` 新增 `queued` 状态展示（“已排队，等待测评机”）
  - `Makefile` 新增 `make judge` 目标，便于本地独立启动 judge worker

### 测试

- **[tests/backend]**: `backend/tests/test_job_manager_local_executor.py` 新增覆盖：
  - 独立模式下 `start_job` 进入 `queued`
  - `claim_next_queued_job` 抢占与 lock 释放
  - 独立模式 `reconcile` 不误判 running 本地任务失败
  - `cancel_job` 通过 state PID 终止本地进程

### 文档

- **[docs]**: 更新 `README.md` 与 `.env.docker.example`
  - 增加独立测评机启动方式（`REALMOI_JUDGE_MODE=independent` + `make judge`）
  - 补充 Docker 下 `judge` 服务说明与相关环境变量

## [0.2.90] - 2026-02-09

### 调整

- **[tests/isolation]**: 测试数据策略由“全新空数据”调整为“默认继承真实数据快照”
  - `backend/tests/conftest.py` 新增 `REALMOI_TEST_INHERIT_REAL_DATA`（默认 `true`），启动 pytest 时自动从真实数据复制快照到隔离临时目录
  - 默认快照来源：
    - 数据库：`REALMOI_TEST_SEED_DB_PATH`（默认 `data/realmoi.db`）
    - 任务目录：`REALMOI_TEST_SEED_JOBS_ROOT`（默认 `jobs`）
  - 仍保持测试隔离写入：测试实际读写路径固定为临时目录中的 `test.db` 与 `jobs/`，不会回写真实数据
  - `backend/tests/conftest.py` 新增测试 admin 账号兜底同步：在隔离副本中统一为 `REALMOI_ADMIN_USERNAME/REALMOI_ADMIN_PASSWORD`，避免继承快照后 admin 凭据不可预测导致测试失败
  - `backend/tests/test_auth.py`、`backend/tests/test_jobs.py`、`backend/tests/test_settings_codex.py` 的测试用户改为随机后缀，避免与继承快照中的既有账号冲突

### 验证

- **[tests/backend]**: 执行 `pytest -q backend/tests/test_docker_service.py backend/tests/test_auth.py` 通过（4/4）
- **[tests/backend]**: 执行 `pytest -q backend/tests/test_docker_service.py backend/tests/test_auth.py backend/tests/test_jobs.py backend/tests/test_settings_codex.py` 通过（11/11）
- **[tests/backend]**: 执行 `pytest -q` 通过（49/49）

## [0.2.89] - 2026-02-09

### 修复

- **[tests/isolation]**: 修复 pytest 运行时可能误用本地真实数据目录的问题
  - `backend/tests/conftest.py` 将测试环境变量初始化提前到模块导入阶段执行，确保在任何 `backend.app.*` 模块导入前生效
  - 使用 `tempfile.mkdtemp(prefix=\"realmoi-pytest-\")` 生成隔离目录，并通过 `setdefault` 设置 `REALMOI_DB_PATH`、`REALMOI_JOBS_ROOT`、`REALMOI_CODEX_AUTH_JSON_PATH` 等关键变量
  - `client` fixture 移除晚初始化逻辑，避免 `Settings`/`engine` 已锁定默认路径后才设置环境变量

### 验证

- **[tests/backend]**: 执行 `pytest -q backend/tests/test_docker_service.py backend/tests/test_auth.py` 通过（4/4）
- **[tests/backend]**: 执行 `pytest -q` 通过（49/49）

## [0.2.88] - 2026-02-09

### 修复

- **[runner/appserver]**: 修复“会话已完成但外部拿不到结果”的兼容性问题
  - `runner/app/runner_generate.py` 新增 turn/item 文本提取回填逻辑：在 `turn/completed` 时从 `turn` 结构兜底提取最终 assistant 文本
  - 兼容 `camelCase/snake_case` 事件命名：`item/agentMessage/delta`、`item/agent_message/delta`、`item/commandExecution/outputDelta`、`item/command_execution/output_delta` 等
  - 新增 `codex/event/agent_message_*` 回退通道：当主流 `item/*` 事件缺失时，仍可恢复最终输出并写回 `last_message`
  - 兼容 `codex/event/item_completed` 的嵌套 `msg.item` 结构，避免工具执行已完成但外层解析丢失

### 验证

- **[tests/runner]**: 执行 `./.venv/bin/python -m pytest -q backend/tests/test_runner_generate.py` 通过（10/10）
- **[tests/backend]**: 执行 `./.venv/bin/python -m pytest -q backend/tests`，出现与本次改动无关的既有失败（用户重复注册导致 `409`）

## [0.2.87] - 2026-02-09

### 修复

- **[runner/frontend/realtime]**: 修复 Codex 思考流断句不稳定导致的“半句拼接”问题
  - `runner/app/runner_generate.py` 透传 `item/reasoning/summaryPartAdded` 为 `reasoning_summary_boundary` 事件
  - `runner/app/runner_generate.py` 为 `reasoning_summary_delta` 增加 `meta.summary_index`（来源于 `summaryIndex`）
  - `frontend/src/components/assistant/Cockpit.tsx` 增加思考缓冲器，改为“段落级”分段（按空行 + 边界事件）并强制 flush
  - `frontend/src/components/assistant/Cockpit.tsx` 在切换到执行/结果事件前先刷出剩余思考片段，避免句子顺序错位
  - `frontend/src/components/assistant/Cockpit.tsx` 思考段落改为独立 `details` 条目，默认收起，实现“每段完成后自动折叠”

### 文档

- **[docs/realtime]**: 同步 Codex 思考断句策略说明
  - `README.md` 新增 `summaryTextDelta` 非句边界语义说明与当前断句实现
  - `helloagents/modules/runner.md`、`helloagents/modules/frontend.md` 补充 `summaryPartAdded/summaryIndex` 处理说明

## [0.2.86] - 2026-02-09

### 新增

- **[runner/realtime]**: 新增 `codex app-server` 实时链路，支持真正增量事件流
  - `runner/app/runner_generate.py` 新增 appserver 通道实现（`initialize` / `thread/start` / `turn/start`）
  - 实时消费并透传 `item/reasoning/*delta`、`item/commandExecution/outputDelta`、`item/agentMessage/delta`
  - 新增 `REALMOI_CODEX_TRANSPORT`（`appserver/exec/auto`）通道开关

### 修复

- **[frontend/realtime]**: 修复“后台执行完再假流式回放”问题
  - `frontend/src/components/assistant/Cockpit.tsx` 改为主订阅 `agent_status.sse`，`terminal.sse` 降级为回退
  - Job 完成时按“结构化流优先、终端流兜底”收口 `job-token-*` 消息
  - Codex `【思考】` 分段改为灰色轻量文本单独展示，接近 TUI 风格，不再和执行步骤样式混合
  - 思考区调整为“单行条目持续追加 + 不截断”：每条思考增量独立一行展示，默认展开，保留全部思考内容
  - 结构化实时流改为“并列时间线”渲染：调用 Codex 后内部思考/执行项不再堆在 `【编码】调用 Codex（call n）` 下，而是逐条并列展示

- **[backend/realtime]**: 增加后端透传开关并改进本地日志采集实时性
  - `backend/app/settings.py` 新增 `runner_codex_transport`（默认 `appserver`）
  - `backend/app/services/job_manager.py` 透传 `REALMOI_CODEX_TRANSPORT` 到 runner
  - `backend/app/services/local_runner.py` 由按行读取改为按字节块读取，降低无换行场景下的流式延迟

### 文档

- **[docs]**: 同步更新运行与模块说明
  - `README.md` 增加 `REALMOI_RUNNER_CODEX_TRANSPORT` 配置说明
  - `helloagents/modules/runner.md`、`helloagents/modules/backend.md`、`helloagents/modules/frontend.md` 同步实时流设计与回退策略

### 验证

- **[tests/backend]**: 新增 `parse_usage` 对 appserver tokenUsage 兼容测试
  - `backend/tests/test_runner_generate.py::test_parse_usage_supports_appserver_token_usage`

## [0.2.85] - 2026-02-08

### 配置调整

- **[make/dev]**: `make dev` 改为纯本地启动流程，不再依赖 Docker 构建
  - `Makefile` 中 `dev` 目标移除 `runner-build` 前置依赖
  - `RUNNER_IMAGE` 默认值统一为 `realmoi/realmoi-runner:latest`
  - 启动日志增加 runner 镜像提示，明确“按需拉取”行为

### 文档

- **[docs/dev]**: 同步更新本地开发说明，避免“`make dev` 会构建 Docker”误解
  - `README.md` 标注 `make dev` 仅执行本地依赖安装与服务启动
  - `helloagents/modules/backend.md` 同步默认 runner 镜像与开发流程描述

### 验证

- **[make]**: 执行 `make -n dev`，确认不包含 Docker 构建步骤
- **[backend]**: 执行 `pytest -q backend/tests/test_docker_service.py backend/tests/test_job_manager_upstream_channel.py` 通过（3/3）

## [0.2.84] - 2026-02-08

### 配置调整

- **[deployment/docker]**: `REALMOI_OPENAI_API_KEY` 改为可空，支持后台手动配置上游 Key
  - `docker-compose.yml` 中 `REALMOI_OPENAI_API_KEY` 从必填插值改为可空默认值
  - `.env.docker.example` 改为默认留空并标注“建议在管理员后台配置”
  - `README.md` 同步更新“可由管理员在前端后台配置上游渠道 api_key”

### 新增

- **[deployment/docker]**: 新增本地构建部署路径（不依赖远程业务镜像）
  - `docker-compose.yml` 为 `backend/frontend` 增加 `build` 配置
  - `Makefile` 新增 `docker-build-local` 与 `docker-up-local`
  - `README.md` 与 `helloagents/modules/deployment.md` 补充本地构建说明

### 验证

- **[docker-compose]**: 执行 `docker compose config` 通过
- **[docker-compose]**: 空 env 文件下执行 `docker compose --env-file <empty> config` 通过（`REALMOI_OPENAI_API_KEY=""`）
- **[make]**: 执行 `make help` / `make -n docker-up-local` 通过

## [0.2.83] - 2026-02-08

### 新增

- **[deployment/docker]**: 新增应用级 Docker 交付与拉取部署能力
  - 增加 `Dockerfile.backend` 与 `Dockerfile.frontend`
  - 增加根目录 `docker-compose.yml` 与 `.env.docker.example`，支持直接 `docker compose pull && docker compose up -d`
  - 增加 `.dockerignore`，降低构建上下文体积

- **[ci/github-actions]**: 新增 Tag 自动发布 Docker 镜像流水线
  - 新增 `.github/workflows/docker-release.yml`
  - 触发条件：`push` 到 `v*` tag 或 `workflow_dispatch`
  - 发布镜像：`realmoi-backend` / `realmoi-frontend` / `realmoi-runner`
  - 登录凭据从 GitHub Secrets 读取：`DOCKERHUB_USERNAME` + `DOCKERHUB_TOKEN`

- **[backend/docker]**: 后端在启动 runner 容器前自动检查并拉取镜像
  - 新增 `ensure_image_ready()`，首次缺失时自动 `pull`
  - `create_generate_container()` / `create_test_container()` 复用该逻辑
  - 新增测试 `backend/tests/test_docker_service.py`

### 文档

- **[docs]**: 更新 Docker 部署与发版文档
  - `README.md` 新增「Docker 部署」与「GitHub Tag 自动发布 Docker 镜像」章节
  - 新增 `helloagents/modules/deployment.md`，并同步更新模块索引
  - `helloagents/modules/backend.md`、`helloagents/modules/runner.md` 同步运行行为与镜像信息

### 验证

- **[backend]**: 执行 `./.venv/bin/pytest backend/tests/test_docker_service.py` 通过（2/2）
- **[docker-compose]**: 执行 `REALMOI_OPENAI_API_KEY=dummy docker compose config` 通过

## [0.2.82] - 2026-02-08

### 配置调整

- **[frontend/api]**: 将 `NEXT_PUBLIC_API_BASE_URL` 默认地址调整为 `http://0.0.0.0:8000/api`
  - 默认回退值由 `localhost` 变更为 `0.0.0.0`
  - 保留外网保护：当显式配置为 `localhost/127.0.0.1` 且当前主机非本地时，自动回退为运行时主机地址

### 文档

- **[docs]**: 同步更新前端配置说明
  - `README.md` 前端启动示例改为 `http://0.0.0.0:8000/api`
  - `helloagents/modules/frontend.md` 更新 `NEXT_PUBLIC_API_BASE_URL`/`NEXT_PUBLIC_API_PORT` 行为描述

### 验证

- **[frontend]**: 执行 `npm --prefix frontend run lint` 通过
- **[frontend]**: 执行 `npm --prefix frontend run build` 通过

## [0.2.81] - 2026-02-08

### 修复

- **[frontend/api]**: 修复构建时环境变量写死 `localhost` 导致外网仍请求本机地址
  - 当 `NEXT_PUBLIC_API_BASE_URL` 为 `localhost/127.0.0.1` 且当前访问主机不是本地时，自动忽略该配置
  - 回退到运行时推断地址：`{当前访问主机}:{NEXT_PUBLIC_API_PORT|8000}/api`

### 验证

- **[frontend]**: 执行 `npm --prefix frontend run lint` 通过
- **[frontend]**: 执行 `npm --prefix frontend run build` 通过

## [0.2.80] - 2026-02-08

### 修复

- **[frontend/api]**: 修复外网访问时 API 默认地址仍指向 `localhost:8000` 的问题
  - `frontend/src/lib/api.ts` 的默认 API base 从固定常量改为运行时推断
  - 未配置 `NEXT_PUBLIC_API_BASE_URL` 时，自动使用“当前访问主机 + `:8000/api`”
  - 新增 `NEXT_PUBLIC_API_PORT`，用于覆盖运行时推断端口（默认 `8000`）

### 文档

- **[docs]**: 更新后端地址配置说明
  - `README.md` 标注 `NEXT_PUBLIC_API_BASE_URL` 为可选项，并说明默认推断行为
  - `helloagents/modules/frontend.md` 同步新增 `NEXT_PUBLIC_API_PORT` 说明

### 验证

- **[frontend]**: 执行 `npm --prefix frontend run lint` 通过
- **[frontend]**: 执行 `npm --prefix frontend run build` 通过

## [0.2.79] - 2026-02-08

### 修复

- **[frontend/assistant]**: 修复 Chat「思考过程」中阶段步骤重复显示的问题
  - `parseStatusUpdateLine()` 仅解析 runner 标准输出的 `[status] ...` 行，不再把 `status_update(...)` 脚本源码当作状态事件
  - `cleanTokenText()` 在 here-doc 清洗阶段不再提取状态，避免同一阶段同时由脚本源码与真实日志各生成一条步骤
  - 保留真实阶段日志（`[status] stage=... summary=...`）用于标题生成，步骤卡片恢复单次展示

### 验证

- **[frontend]**: 执行 `npm --prefix frontend run lint` 通过

## [0.2.78] - 2026-02-08

### 修复

- **[frontend/assistant]**: 思考过程日志按事件切分展示，避免整段内容挤在“编码”单条中
  - `token` 日志切分从“仅按 exit 边界”改为“按事件边界”切分（阶段状态、结果、Token统计、后端重试）
  - 每条折叠项标题改为语义化标题（如 `编码 · ...`、`结果 · ...`、`Token统计`、`后端重试 #N`）
  - 修复一次 Job 多轮 generate/repair 时，过程日志被合并成单条“编码”记录的问题

### 验证

- **[frontend]**: 执行 `npm --prefix frontend run lint` 通过
- **[frontend]**: 执行 `npm --prefix frontend run build` 通过

## [0.2.77] - 2026-02-08

### 改进

- **[frontend/assistant]**: New Job 参数新增“思考量”手动选择
  - 参数面板新增 `思考量` 下拉，支持 `low/medium/high/xhigh` 四档
  - 新建与续聊创建 Job 时均会提交 `reasoning_effort`
  - Cockpit 顶部状态栏新增当前思考量展示

- **[backend/jobs]**: `/api/jobs` 支持并持久化 `reasoning_effort`
  - `POST /api/jobs` 新增表单字段 `reasoning_effort`（默认 `medium`）
  - `input/job.json` 与 `state.json` 同步写入该字段，便于追踪与复现

- **[runner/generate]**: 将思考量透传到 Codex CLI
  - `runner_generate.py` 新增 `normalize_reasoning_effort()`，非法值回退 `medium`
  - 调用 `codex exec` 时追加 `--config model_reasoning_effort=<value>`

### 验证

- **[backend]**: 执行 `./.venv/bin/pytest backend/tests/test_jobs.py backend/tests/test_runner_generate.py` 通过（10/10）
- **[frontend]**: 执行 `npm --prefix frontend run lint` 通过

## [0.2.76] - 2026-02-08

### 修复

- **[runner/generation-stream]**: 恢复并增强思考过程的实时流式可见性
  - `status_update()` 除写入 `agent_status.jsonl` 外，新增同步输出 `[status] stage=... summary=...` 到终端日志
  - Codex JSON 事件解析新增 `reasoning`/`agent_message` 进度提示，避免仅在最终结果时才有输出
  - 统一终端提示为中文（错误、失败、Token 统计），减少英文噪音

- **[runner/language-guard]**: 增加说明字段中文校验，防止结果回退英文
  - 新增 `has_cjk_text()` 与 `explanation_fields_are_chinese()` 校验
  - 若 `solution_idea`/`seed_code_idea`/`seed_code_bug_reason` 任一缺少中文，触发重试而非直接落盘
  - 重试提示词补充“说明字段和 `status_update` summary 均必须为中文”

- **[frontend/assistant]**: Cockpit 输出文案全面中文化
  - 结果区标题统一为中文：`前置假设`、`复杂度`、`思考过程`、`工作区`、`代码`、`取消任务`
  - 过程日志支持解析 `[status] stage=... summary=...` 并映射为中文阶段标签（分析/方案/编码/修复等）
  - 失败摘要文案改为中文（`首个失败用例`）

### 验证

- **[backend]**: 执行 `./.venv/bin/pytest backend/tests/test_runner_generate.py` 通过（4/4）
- **[frontend]**: 执行 `npm --prefix frontend run lint` 通过
- **[frontend]**: 执行 `npm --prefix frontend run build` 通过
- **[runner]**: 执行 `python -m compileall runner/app/runner_generate.py` 通过

## [0.2.75] - 2026-02-08

### 修复

- **[frontend/header]**: `/jobs` 路由下顶栏“助手”导航高亮修复
  - 将 `/jobs` 与 `/jobs/{jobId}` 识别为“助手”域路由
  - 在 Job 详情页时，顶栏“助手”按钮保持激活高亮
  - 其他导航高亮逻辑保持不变

### 验证

- **[frontend]**: 执行 `npm --prefix frontend run lint` 通过

## [0.2.74] - 2026-02-08

### 改进

- **[runner/generate-prompt]**: 提示词强化“最终说明字段使用中文”约束
  - `build_prompt_generate()` 新增硬性要求：`solution_idea`、`seed_code_idea`、`seed_code_bug_reason` 必须中文输出
  - `build_prompt_repair()` 同步新增相同中文约束，避免修复轮次回退到英文
  - schema 格式修复重试提示追加“说明字段必须中文”要求

### 验证

- **[runner]**: 执行 `python -m compileall runner/app/runner_generate.py` 通过

## [0.2.72] - 2026-02-08

### 改进

- **[frontend/assistant]**: 过程日志恢复 Codex 思考摘要
  - 在清理命令噪音的同时保留 `status_update(stage, summary)` 信息
  - 将思考信息格式化为 `[ANALYSIS] ...`、`[PLAN] ...`、`[CODING] ...` 等可读条目
  - 继续移除 `MODE=...`、`$ /bin/bash -lc ...`、`exit=...` 等包装日志

### 验证

- **[frontend]**: 执行 `npm --prefix frontend run lint` 与 `npm --prefix frontend run build` 通过

## [0.2.71] - 2026-02-08

### 改进

- **[frontend/assistant]**: 过程日志清理命令包装噪音
  - 移除 `MODE=...`、`$ /bin/bash -lc ...`、`exit=0` 等执行包装行
  - 移除 `status_update(...)` here-doc 片段（含 `from runner_generate...`、`PY` 结束标记）
  - 保留有效业务日志，减少过程面板的命令噪音

### 验证

- **[frontend]**: 执行 `npm --prefix frontend run lint` 与 `npm --prefix frontend run build` 通过

## [0.2.70] - 2026-02-08

### 改进

- **[frontend/assistant]**: 移除过程日志（思考过程）区域边框
  - 去掉 `PROCESS (N)` 容器外边框
  - 去掉过程条目之间与条目展开区的边框线
  - 保留折叠结构与代码风文本展示，视觉更轻量

### 验证

- **[frontend]**: 执行 `npm --prefix frontend run lint` 与 `npm --prefix frontend run build` 通过

## [0.2.69] - 2026-02-08

### 改进

- **[frontend/assistant]**: 过程日志样式对齐 VSCode Codex 扩展风格
  - 一级折叠头改为 `PROCESS (N)` 工具面板样式（紧凑、浅灰、细边框）
  - 二级“步骤 N”折叠项改为等宽字体摘要，展开后正文采用代码风文本样式
  - 调整边框、分隔线与背景层次，减少聊天气泡感，更接近工具输出面板

### 验证

- **[frontend]**: 执行 `npm --prefix frontend run lint` 与 `npm --prefix frontend run build` 通过

## [0.2.68] - 2026-02-08

### 改进

- **[frontend/assistant]**: 过程日志内的每条明细支持二级折叠
  - 保留一级“过程日志（N条）”汇总折叠项
  - 一级展开后，每条日志再以独立 `details` 默认折叠展示
  - 每条日志摘要显示“日志 N · 首行预览”，点击后展开完整内容

### 验证

- **[frontend]**: 执行 `npm --prefix frontend run lint` 与 `npm --prefix frontend run build` 通过

## [0.2.67] - 2026-02-08

### 改进

- **[frontend/assistant]**: 过程日志收敛为“单条默认折叠”展示
  - token 日志不再逐条显示多个折叠块，改为单个“过程日志（N条）”折叠项
  - 执行中保持展开，任务结束后自动回到折叠态
  - 展开后按条目显示完整过程日志，保留条目间分隔

### 验证

- **[frontend]**: 执行 `npm --prefix frontend run lint` 与 `npm --prefix frontend run build` 通过

## [0.2.66] - 2026-02-08

### 修复

- **[frontend/assistant]**: 过滤历史会话中的旧版 Job 提示文案
  - Chat 渲染层新增 legacy 提示过滤，不再显示“已创建 Job / 正在启动并追踪终端输出”等旧消息
  - 同时过滤“我会基于上一轮代码与追加指令...”旧版提示，避免新旧行为混杂
  - 仅影响展示，不改写本地历史原始数据

### 验证

- **[frontend]**: 执行 `npm --prefix frontend run lint` 通过

## [0.2.65] - 2026-02-08

### 改进

- **[frontend/assistant]**: 移除 token 流中的冗余提示文案
  - 删除“已创建 Job / 正在启动并追踪终端输出”自动消息
  - 删除 token 卡片中的“Token级流式输出中”状态标签
  - 删除 token 内容中的“Job ... Token级流式输出”标题行
  - 保持按命令结果分条和默认折叠，仅展示核心日志正文

### 验证

- **[frontend]**: 执行 `npm --prefix frontend run lint` 与 `npm --prefix frontend run build` 通过

## [0.2.64] - 2026-02-08

### 修复

- **[frontend/assistant]**: 回退 token 流外层气泡，保持“去外层框”行为
  - `job-token-*` 恢复为无外层白底边框容器
  - 保留内部折叠条目与普通文本风格统一（标题、正文、白底条目）
  - 避免再次出现用户指定要移除的那层外框

### 验证

- **[frontend]**: 执行 `npm --prefix frontend run lint` 与 `npm --prefix frontend run build` 通过

## [0.2.63] - 2026-02-08

### 改进

- **[frontend/assistant]**: Token 流消息视觉与普通 assistant 输出统一
  - `job-token-*` 恢复使用普通 assistant 外层气泡样式（白底边框）
  - token 标题文本字号与普通正文对齐
  - 折叠条目改为白底边框样式，避免与普通输出产生风格割裂

### 验证

- **[frontend]**: 执行 `npm --prefix frontend run lint` 与 `npm --prefix frontend run build` 通过

## [0.2.62] - 2026-02-08

### 改进

- **[frontend/assistant]**: 移除 token 流消息外层气泡框
  - `job-token-*` 消息不再渲染外层白底边框气泡
  - 保留内部折叠日志卡片，减少视觉层级嵌套
  - 普通 assistant/user 消息样式保持不变

### 验证

- **[frontend]**: 执行 `npm --prefix frontend run lint` 与 `npm --prefix frontend run build` 通过

## [0.2.61] - 2026-02-08

### 改进

- **[frontend/assistant]**: Token 折叠日志取消“单一外层大框”容器
  - 移除日志列表外层统一边框容器
  - 每条日志改为独立圆角块（保持默认折叠）
  - 展开内容区保留内部顶部分隔线，提升阅读层次

### 验证

- **[frontend]**: 执行 `npm --prefix frontend run lint` 与 `npm --prefix frontend run build` 通过

## [0.2.60] - 2026-02-08

### 改进

- **[frontend/assistant]**: Token 日志默认折叠并增加条目分隔
  - 每条 token 日志改为 `details/summary`，默认折叠，按点击展开查看详情
  - 日志容器增加条目分割线（`divide-y`），逐条阅读更清晰
  - 统一清理 `[runner]` 与 `[codex]` 前缀，仅保留核心日志文本

### 验证

- **[frontend]**: 执行 `npm --prefix frontend run lint` 与 `npm --prefix frontend run build` 通过
- **[playwright]**: 回归 `A+B` 新 Job `b70228eabe9942c6a369517041fcb1bf`，快照可见默认折叠条目（`日志 1 · MODE=generate`）

## [0.2.59] - 2026-02-08

### 改进

- **[frontend/assistant]**: Token 流条目改为“对话式逐条展示”
  - 保留按 `exit` 结束线切分逻辑，但移除“片段 N”文案
  - 每条日志独立显示为普通聊天条目块，阅读顺序与对话一致
  - 去除日志中的 `[codex]` 前缀，保留核心命令与输出内容

### 验证

- **[frontend]**: 执行 `npm --prefix frontend run lint` 与 `npm --prefix frontend run build` 通过

## [0.2.58] - 2026-02-08

### 改进

- **[frontend/assistant]**: Token 流消息按 `[codex] exit=...` 进行片段拆分展示
  - `job-token-*` 消息新增解析：标题与日志正文分离
  - 日志正文按每次 `"[codex] exit=..."` 结束线切分为独立片段（片段 1/2/3...）
  - 每个片段以独立浅色块展示，提升长日志可读性

### 验证

- **[frontend]**: 执行 `npm --prefix frontend run lint` 通过
- **[playwright]**: 截图 `output/playwright/20260208_chat_layout/chat_token_stream_split_by_exit.png`，可见“片段 1”分块展示

## [0.2.57] - 2026-02-08

### 改进

- **[frontend/assistant]**: Token 级流式消息卡片改为普通聊天样式
  - 移除 token 流消息的深色“终端风”底色与等宽字体
  - 统一为 assistant 默认浅色气泡样式（与普通回答视觉一致）
  - 保留流式状态徽标与“Token级流式输出中”文案，仅调整视觉样式

### 验证

- **[frontend]**: 执行 `npm --prefix frontend run lint` 通过
- **[playwright]**: 截图 `output/playwright/20260208_chat_layout/chat_token_stream_normal_style.png`，确认 token 流卡片为普通 assistant 气泡样式

## [0.2.56] - 2026-02-08

### 修复

- **[frontend/assistant]**: 移除 Chat 内 `Job ... 实时进展（已结束）` 状态流消息
  - 删除 `agent_status.sse` 到 Chat 消息卡片的同步逻辑，不再生成 `job-stream-*` 消息
  - 保留 `terminal.sse` 的 token 级流式消息（`job-token-*`），满足逐 token 可见性
  - 增加历史消息过滤：`job-stream-*` 即使存在于旧会话缓存中也不会显示

### 验证

- **[frontend]**: 执行 `npm --prefix frontend run lint` 与 `npm --prefix frontend run build` 通过
- **[playwright]**: 截图 `output/playwright/20260208_chat_layout/chat_no_status_stream_message.png`，确认 Chat 仅展示 Token 级流与最终答复，无“实时进展（已结束）”卡片

## [0.2.55] - 2026-02-08

### 改进

- **[frontend/assistant]**: Cockpit 结构重排为「Chat + Code 并列」双栏工作区
  - 移除左侧运行信息栏与移动端抽屉
  - 移除 `STATUS` 页面入口，不再提供独立状态页
  - Chat 区保留实时状态流 + Token 流 + 输入框；Code 区固定在右侧展示 `main.cpp`
  - 顶部精简为统一操作栏（Job 信息、Cancel、返回大厅）

### 验证

- **[frontend]**: 执行 `npm --prefix frontend run lint` 与 `npm --prefix frontend run build` 通过
- **[playwright]**: 截图 `output/playwright/20260208_chat_layout/chat_code_split_no_sidebar.png`（无左栏、无 STATUS、Chat/Code 并列）

## [0.2.54] - 2026-02-08

### 修复

- **[frontend/assistant]**: 调整助手主画布顶部安全间距，避免内容与固定顶栏发生视觉重叠
  - `AssistantApp` 外层容器由 `pt-10 md:pt-12` 调整为 `pt-16 md:pt-20`
  - 在保持 `100dvh` 结构不变的前提下，为内容区与导航栏预留稳定呼吸空间

### 验证

- **[frontend]**: 执行 `npm --prefix frontend run lint` 通过

## [0.2.53] - 2026-02-08

### 改进

- **[frontend/assistant]**: 移除 Cockpit 的 `TERMINAL` 页面入口，统一在 `CHAT/STATUS/CODE` 三标签工作流内操作
  - 顶部标签移除 `TERMINAL`，避免与 Chat 流式输出入口重复
  - 删除 xterm 面板渲染逻辑，保留 `terminal.sse` 作为 Chat Token 流数据源
  - `agent_status.sse` 与 Token 流仍在 `CHAT` 内实时展示，`STATUS` 仅保留结构化状态时间线

### 验证

- **[frontend]**: 执行 `npm --prefix frontend run lint` 与 `npm --prefix frontend run build` 通过
- **[playwright]**: 截图 `output/playwright/20260208_chat_stream/chat_no_terminal_tab.png` 显示仅 `CHAT/STATUS/CODE`

## [0.2.52] - 2026-02-08

### 新增

- **[frontend/assistant]**: Chat 面板新增 Job 实时流式消息
  - 将 `agent_status.sse` 的增量事件实时写入 `CHAT` 区消息卡片，按同一 `jobId` 持续更新（非一次性落地）
  - 流式消息使用 `messageKey` 去重更新，避免重复追加同一条状态
  - Job 完成时自动将流式卡片切换为“已结束”并补最终状态（如 `succeeded/failed`）
  - Chat 消息区新增自动滚动到底部，保证流式进度可见
- **[frontend/assistant]**: 新增 Token 级流式输出卡片
  - 从 `terminal.sse` 增量消费终端 chunk，实时写入 `job-token-{jobId}` 消息
  - 终端 chunk 做 ANSI/控制字符清洗并保留最近 6000 字符，避免 UI 被日志噪音淹没
  - Token 流消息使用深色等宽样式，与普通状态流卡片区分；任务结束后自动标记“已结束”

### 验证

- **[frontend]**: 执行 `npm --prefix frontend run lint` 与 `npm --prefix frontend run build` 通过
- **[playwright]**: 验证截图 `output/playwright/20260208_chat_stream/chat_stream_status.png`，可见 `Job ... 实时进展（已结束）` 卡片
- **[playwright]**: Token 流截图 `output/playwright/20260208_chat_stream/chat_token_stream_status.png`，可见 `Token级流式输出（已结束）` 卡片

## [0.2.51] - 2026-02-08

### 修复

- **[frontend/assistant]**: 强化 Cockpit `CHAT` 页签底部锚定布局，输入栏固定在 Chat 面板内部最底部
  - `CHAT` 容器改为 `flex-col` 主轴布局，消息区 `flex-1 + overflow-y-auto`
  - 输入栏增加 `mt-auto + shrink-0 + border-t`，避免在消息较短时上浮到中部
  - 修复“输入栏看起来独立悬浮”与“未贴底”观感问题
- **[frontend/assistant]**: 修复会话历史被错误覆盖与 URL 直达恢复丢失问题
  - 新增 `historyHydrated` 门闩，避免首次挂载时 `history=[]` 提前写回 localStorage 覆盖已有历史
  - 当通过 `/jobs/{jobId}` 直达时，自动从 `realmoi_assistant_history` 里按 `run.jobId` 匹配并恢复会话上下文
  - 恢复成功后同步 `sessionId/currentPrompt/messages/runs`，后续会话变更可持续正确落盘

### 验证

- **[frontend]**: 执行 `npm --prefix frontend run lint` 通过
- **[playwright]**: 回归截图 `output/playwright/20260208_chat_layout/chat_bottom_final.png`
- **[playwright]**: 补充验证截图 `output/playwright/20260208_chat_layout/chat_bottom_final_v2.png`
- **[playwright]**: 注入 `realmoi_assistant_history` 后刷新页面，`localStorage.getItem(...).includes('s1') === true`（历史未被清空）

## [0.2.50] - 2026-02-08

### 改进

- **[frontend/assistant]**: Cockpit 工作区改为“终端 + 对话合并面板”
  - 原中区对话面板与右侧终端面板合并为单一工作区，统一为 `CHAT / TERMINAL / STATUS / CODE` 顶部标签切换
  - 保留左侧运行信息栏（当前 Job、Runs、Cancel、返回大厅），并新增移动端“运行信息”抽屉开合
  - 统一主工作区间距体系（header/content/footer），修复多面板并列导致的拥挤、边框不齐与视觉重叠
  - 对话标签页内保留原输入交互，非对话标签页保留状态/模型摘要与失败提示，减少信息漂移
  - 按交互反馈调整：对话输入栏收回到 `CHAT` 页签内部底部（不再独立为页面级底栏）

### 验证

- **[frontend]**: 执行 `npm --prefix frontend run lint` 与 `npm --prefix frontend run build` 通过
- **[playwright]**: 合并后界面截图见 `output/playwright/20260208_merge_workspace/cockpit_merged_chat.png` 与 `output/playwright/20260208_merge_workspace/cockpit_merged_terminal.png`

## [0.2.49] - 2026-02-07

### 改进

- **[frontend/ui]**: 统一助手端样式基线，修复字体、边框对齐与重叠观感问题
  - 全局字体切换为 `Geist + Noto Sans SC`，中文显示不再发虚或风格混杂
  - 统一玻璃面板圆角/边框/阴影强度，减少“框压框”与重叠感
  - Header 导航、Portal、Cockpit 与输入面板统一为同一尺寸体系（文本、按钮、间距）
  - Assistant 顶部留白上调（`pt-20/pt-24`），避免内容与顶栏视觉挤压
  - Terminal 初始化增加 `ResizeObserver + fonts.ready` 触发 `fit()`，降低字号错位和截断问题

### 验证

- **[frontend]**: 执行 `npm --prefix frontend run lint` 与 `npm --prefix frontend run build` 通过
- **[playwright]**: 样式回归截图见 `.playwright-cli/page-2026-02-07T22-59-56-106Z.png`

## [0.2.48] - 2026-02-07

### 修复

- **[runner/schema]**: 修复 `codex_output_schema` 与上游 JSON Schema 约束不兼容
  - `runner/schemas/codex_output_schema.json` 的 `required` 补齐 `assumptions` 与 `complexity`
  - 避免上游报错：`invalid_json_schema` / `Missing 'assumptions'`
  - 生成阶段不再因 schema 校验失败重试直至 `generate_failed`

### 验证

- **[backend]**: 执行 `source ".venv/bin/activate" && pytest backend/tests -q` 通过（33 passed）
- **[frontend]**: 执行 `npm --prefix frontend run lint` 与 `npm --prefix frontend run build` 通过
- **[playwright]**: 完整回归证据见 `output/playwright/20260207_full_regression/summary_fullreg4.md`

## [0.2.47] - 2026-02-07

### 修复

- **[frontend/assistant]**: 历史会话恢复后同步 URL 到当前 Job
  - 点击 RECENT SESSIONS 进入 Cockpit 时，地址栏会自动对齐为 `/jobs/{jobId}`
  - 避免刷新后丢失当前 Job 上下文

- **[frontend/jobs-route]**: 修复 `/jobs/[jobId]` 动态参数读取兼容性
  - Job 详情页改为异步读取 `params`（Next 16）
  - 直达 `/jobs/{jobId}` 不再错误落回 Portal

- **[frontend/assistant]**: 失败态消息与 artifacts 拉取策略优化
  - 仅在 `status=succeeded` 时请求 `solution/main/report` artifacts
  - 失败态直接展示 `state.error` 原因（如 `failed: generate_failed`）
  - 消除失败任务下无意义的 artifacts 404 请求噪音

- **[frontend/portal]**: 非 admin 用户模型加载流程去除 admin 接口探测
  - 普通用户不再请求 `/api/admin/upstream/channels`
  - 消除助手首页的 403 控制台噪音

### 验证

- **[frontend]**: 执行 `npm --prefix frontend run lint` 与 `npm --prefix frontend run build` 通过
- **[playwright]**: 全流程回归记录见 `output/playwright/20260207_full_regression/summary.md`

## [0.2.46] - 2026-02-07

### 修复

- **[frontend/assistant]**: 修复 New Job 首次启动在开发态可能重复创建 Job 的问题
  - `Cockpit` 初次启动流程新增防重入标记，避免 `POST /api/jobs` 与 `/start` 被触发两次
  - Playwright 复测确认二次提交仅创建 1 个 Job

### 验证

- **[frontend]**: 执行 `npm --prefix frontend run lint` 与 `npm --prefix frontend run build` 通过
- **[playwright]**: `A+B` 流程复测（`output/playwright/20260207_ab_flow/`）通过“单次创建”验收

## [0.2.45] - 2026-02-07

### 改进

- **[frontend/assistant]**: 创建 Job 后同步更新浏览器地址到 `/jobs/{jobId}`
  - 首次创建 Job 与“继续对话”创建的新 Job 都会写入新地址
  - 在 Runs 列表切换 Job 时地址栏会同步为对应 `jobId`
  - 点击“返回大厅/退出”时地址恢复为 `/`
  - 直接打开 Job 详情且缺少上下文 Prompt 时，输入区自动进入只读提示模式

- **[frontend/routes]**: 启用 `/jobs/[jobId]` 详情路由页面
  - 访问 `/jobs/{jobId}` 时直接进入 Cockpit 并追踪该 Job
  - 保持 `/jobs` 路由重定向到 `/` 的兼容行为

### 验证

- **[frontend]**: 执行 `npm --prefix frontend run lint` 与 `npm --prefix frontend run build` 通过

## [0.2.44] - 2026-02-07

### 改进

- **[frontend/assistant]**: New Job 模型来源改为“自动拉取 + 本地缓存 + 回退”
  - 优先读取本地缓存 `realmoi_admin_upstream_models_cache_v1`
  - 缓存 180 秒内直接复用，避免每次进入都触发上游请求
  - 自动尝试实时拉取管理端全部启用渠道的模型
  - 实时拉取失败时自动回退到 `/api/models`，避免模型下拉只剩历史占位值
  - 模型下拉按 `"[渠道] model_id"` 展示，并支持同名模型按渠道区分

- **[frontend/assistant]**: New Job 提交补充 `upstream_channel`
  - 选中模型后同时提交渠道信息，避免运行时丢失渠道路由

- **[backend/jobs]**: `POST /api/jobs` 支持“实时模型 + 渠道”创建
  - 新增可选表单字段 `upstream_channel`
  - 当模型未在 `model_pricing` 中激活时，只要渠道有效且启用也可创建 Job
  - `job.json`/`state.json` 持久化 `upstream_channel`，generate 阶段优先按该字段解析上游目标

### 新增

- **[backend/tests]**: `backend/tests/test_jobs.py` 新增“未入价表模型 + upstream_channel”创建成功用例

### 验证

- **[frontend]**: 执行 `npm --prefix frontend run lint` 与 `npm --prefix frontend run build` 通过
- **[backend]**: 执行 `source ".venv/bin/activate" && pytest backend/tests -q` 通过（31 passed）

## [0.2.43] - 2026-02-07

### 改进

- **[frontend/assistant]**: New Job 参数精简并修正模型下拉展示
  - 移除 `Search` 与 `Compare Mode` 字段，避免无效配置干扰
  - 模型下拉统一显示为 `"[渠道] model_id"`，并过滤未绑定渠道的模型
  - 提交 Job 时仅发送必要字段（model/statement/code/tests/limits），由后端使用默认 search/compare 策略

- **[backend/models]**: `/api/models` 增加渠道有效性过滤
  - 仅返回绑定到“已启用渠道”的激活模型，避免 New Job 出现未分配/失效渠道模型
  - 返回结果按渠道与模型名排序，提升前端可读性和稳定性

### 新增

- **[backend/tests]**: `backend/tests/test_models_api.py` 增补“仅返回启用渠道模型”覆盖

### 验证

- **[frontend]**: 执行 `npm --prefix frontend run lint` 与 `npm --prefix frontend run build` 通过
- **[backend]**: 执行 `source ".venv/bin/activate" && pytest backend/tests -q` 通过（30 passed）

## [0.2.42] - 2026-02-07

### 改进

- **[frontend/admin]**: `/admin/upstream-models` 新增“默认值 + 手动刷新 + 自动延迟刷新”
  - 默认自动刷新间隔设为 180 秒
  - 支持手动刷新（强制拉取全部已启用渠道）
  - 支持自动延迟刷新（关闭/60/180/300/600 秒）
  - 新增本地缓存与最近更新时间展示，避免每次进入页面都发起全量请求

### 验证

- **[frontend]**: 执行 `npm --prefix frontend run lint` 与 `npm --prefix frontend run build` 通过

## [0.2.41] - 2026-02-07

### 改进

- **[frontend/admin]**: `/admin/upstream-models` 移除“查询渠道启用勾选”区域
  - 页面默认查询全部已启用渠道
  - 保留渠道配置区中的 `is_enabled` 作为查询范围与运行时范围的统一开关

### 验证

- **[frontend]**: 执行 `npm --prefix frontend run lint` 与 `npm --prefix frontend run build` 通过

## [0.2.40] - 2026-02-07

### 改进

- **[backend/admin]**: `/api/admin/upstream/channels` 移除默认伪渠道返回
  - 渠道管理列表仅展示可管理命名渠道，避免出现不可删除 default 项

- **[frontend/admin]**: 渠道前缀文案去 default 化
  - Pricing 页面空渠道前缀由 `default` 改为 `未分配`
  - 用户模型展示空渠道前缀由 `default` 改为 `unassigned`

### 验证

- **[backend]**: 执行 `source ".venv/bin/activate" && pytest backend/tests -q` 通过（30 passed）
- **[frontend]**: 执行 `npm --prefix frontend run lint` 与 `npm --prefix frontend run build` 通过

## [0.2.39] - 2026-02-07

### 修复

- **[frontend/admin]**: 修复 `/admin/pricing` 首次加载偶发 `upstream_unauthorized` 影响整体展示的问题
  - 实时模型聚合拉取改为按渠道容错：单渠道失败不再中断整个列表
  - 失败渠道改为汇总提示（部分失败）而非整体失败

### 验证

- **[frontend]**: 执行 `npm --prefix frontend run lint` 与 `npm --prefix frontend run build` 通过

## [0.2.38] - 2026-02-07

### 改进

- **[frontend/admin]**: `/admin/pricing` 移除“模型来源选择”字段
  - 页面默认自动聚合全部启用渠道的实时模型
  - 顶部刷新按钮统一同时刷新价格配置与实时模型

### 验证

- **[frontend]**: 执行 `npm --prefix frontend run lint` 与 `npm --prefix frontend run build` 通过

## [0.2.37] - 2026-02-07

### 改进

- **[frontend/admin]**: `/admin/pricing` 实时模型来源默认聚合“全部已启用渠道”
  - 默认不再要求先选择单一渠道
  - 聚合模式下按启用渠道并发拉取模型，优先使用非 default 渠道映射

### 验证

- **[frontend]**: 执行 `npm --prefix frontend run lint` 与 `npm --prefix frontend run build` 通过

## [0.2.36] - 2026-02-07

### 改进

- **[frontend/admin]**: `/admin/pricing` 改为“实时模型 ID 驱动”展示
  - 新增“实时模型来源”渠道选择与手动刷新能力
  - 表格主视图优先展示上游实时返回的模型 ID，不再固定展示历史残留模型
  - 若实时模型尚未配置价格，自动以占位行展示并可直接编辑保存

### 验证

- **[frontend]**: 执行 `npm --prefix frontend run lint` 与 `npm --prefix frontend run build` 通过

## [0.2.35] - 2026-02-07

### 修复

- **[frontend/admin]**: 修复 `/admin/pricing` 启用模型偶发不持久化问题
  - 价格字段从失焦写入改为受控输入实时写入，避免“编辑后立即保存”提交旧值
  - 启用前增加本地校验：4 个价格字段未填齐时阻止提交并提示

### 改进

- **[frontend/admin]**: `/admin/upstream-models` 模型列表默认过滤“奇怪模型”
  - 默认只显示常见对话模型（如 gpt/codex/claude/gemini 等）
  - 提供“显示全部模型”开关，便于需要时查看 embedding/tts/realtime 等完整结果

### 验证

- **[frontend]**: 执行 `npm --prefix frontend run lint` 与 `npm --prefix frontend run build` 通过

## [0.2.34] - 2026-02-07

### 修复

- **[backend/admin]**: 修复 `/api/admin/upstream/models` 在代理环境下误报 `upstream_unavailable` 的问题
  - 上游请求改为 `trust_env=False`，避免受宿主机代理环境变量影响
  - 异常信息补充异常类型与细节，提升排查效率

### 新增

- **[backend/tests]**: `backend/tests/test_admin_upstream_models.py` 增加 `trust_env=False` 断言

### 验证

- **[backend]**: 执行 `source ".venv/bin/activate" && pytest backend/tests -q` 通过（30 passed）
- **[backend/live]**: 实测 `GET /api/admin/upstream/models?channel=Realms` 返回 200，模型列表正常

## [0.2.33] - 2026-02-07

### 改进

- **[frontend/admin]**: `/admin/upstream-models` 上游请求失败提示文案可读性增强
  - 将 `upstream_unavailable` 映射为中文可排查提示（Base URL / 网络 / 代理）
  - 将 `upstream_unauthorized` 映射为中文提示（API Key 校验）
  - 对未知渠道、禁用渠道错误补充中文说明

### 验证

- **[frontend]**: 执行 `npm --prefix frontend run lint` 与 `npm --prefix frontend run build` 通过

## [0.2.32] - 2026-02-07

### 改进

- **[frontend/admin]**: `/admin/upstream-models` 新建渠道弹窗不透明度提升
  - 遮罩透明度从较浅值提升为更深层级，背景干扰更小
  - 弹窗面板背景与阴影加重，视觉层级更清晰

### 验证

- **[frontend]**: 执行 `npm --prefix frontend run lint` 与 `npm --prefix frontend run build` 通过

## [0.2.31] - 2026-02-07

### 改进

- **[frontend/admin]**: `/admin/upstream-models` 新建渠道弹窗样式优化为“正常表单”形态
  - 入口由小尺寸图标改为更显眼的“图标 + 文字”按钮
  - 弹窗内改为分组字段布局，提升可读性与填写体验
  - 底部操作区补齐主次按钮（新增/取消）与状态反馈

### 验证

- **[frontend]**: 执行 `npm --prefix frontend run lint` 与 `npm --prefix frontend run build` 通过

## [0.2.30] - 2026-02-07

### 变更

- **[frontend/admin]**: `/admin/upstream-models` 新增渠道入口改为图标弹窗样式
  - 渠道配置区移除常驻“新增渠道”表单，改为右上角 `+` 图标按钮触发
  - 点击图标后打开居中小窗（modal）填写渠道信息
  - 新增成功后自动关闭弹窗并刷新渠道与模型列表

### 验证

- **[frontend]**: 执行 `npm --prefix frontend run lint` 与 `npm --prefix frontend run build` 通过

## [0.2.29] - 2026-02-07

### 变更

- **[backend/admin]**: 渠道管理接口补齐“密钥脱敏 + 删除渠道”能力
  - `GET /api/admin/upstream/channels` 返回 `api_key_masked` 与 `has_api_key`，不再返回明文 `api_key`
  - `PUT /api/admin/upstream/channels/{channel}` 支持“空 API Key 保持原值不变”，新增渠道仍要求必须提供密钥
  - 新增 `DELETE /api/admin/upstream/channels/{channel}`，支持删除非默认渠道
  - 删除保护：`default` 不可删；被 `model_pricing.upstream_channel` 引用时返回 409 冲突

- **[frontend/admin]**: `/admin/upstream-models` 渠道配置交互增强
  - 渠道编辑输入框改为“可留空保持密钥不变”行为
  - UI 仅展示脱敏密钥占位，不再展示明文
  - 新增非默认渠道删除按钮
  - 保持“多渠道默认全启用 + 渠道前缀模型名”行为

### 新增

- **[backend/tests]**: `backend/tests/test_admin_upstream_models.py` 增补覆盖
  - 渠道列表密钥脱敏字段断言
  - 渠道删除成功、在用冲突、默认渠道禁止删除、不存在渠道删除失败

### 验证

- **[backend]**: 执行 `source ".venv/bin/activate" && pytest backend/tests -q` 通过（30 passed）
- **[frontend]**: 执行 `npm --prefix frontend run lint` 与 `npm --prefix frontend run build` 通过

## [0.2.28] - 2026-02-07

### 变更

- **[backend/admin]**: 上游渠道改为支持数据库持久化配置
  - 新增渠道表：`upstream_channels`
  - 新增接口：`PUT /api/admin/upstream/channels/{channel}`（新增/编辑渠道）
  - 渠道列表接口 `GET /api/admin/upstream/channels` 返回完整配置（含 source 与启用状态）
  - 上游模型透传 `GET /api/admin/upstream/models` 改为优先读取 DB 渠道配置（保留 env 映射兜底）

- **[frontend/admin]**: `/admin/upstream-models` 增加“前端配置渠道”能力
  - 支持新增渠道（channel/display_name/base_url/api_key/models_path/is_enabled）
  - 支持编辑已有渠道并保存到后端
  - 继续支持多渠道聚合查询与“默认全启用”选择行为
  - 模型结果保持“`[渠道] 模型名`”前缀展示

- **[backend/runtime]**: generate 阶段渠道解析改为可读取 DB 渠道配置
  - 模型绑定 `upstream_channel` 后，运行时可直接命中前端配置的渠道

### 新增

- **[backend/tests]**: 新增/增强渠道持久化相关覆盖
  - `backend/tests/test_admin_upstream_models.py` 增加渠道新增/更新用例
  - `backend/tests/test_job_manager_upstream_channel.py` 改为验证 DB 渠道路由

### 验证

- **[backend]**: 执行 `source ".venv/bin/activate" && pytest backend/tests -q` 通过（26 passed）
- **[frontend]**: 执行 `npm --prefix frontend run lint` 与 `npm --prefix frontend run build` 通过

## [0.2.27] - 2026-02-07

### 变更

- **[frontend/admin]**: `/admin/upstream-models` 升级为“前端配置渠道 + 多渠道聚合”
  - 新增渠道配置区（复选框），默认全部启用
  - 支持“全启用/全禁用”
  - 支持聚合查询所有启用渠道并统一展示
  - 输出“`[渠道] 模型名`”前缀格式用于区分同名模型

- **[backend/admin]**: 新增 `GET /api/admin/upstream/channels`
  - 返回默认渠道 + 配置中的命名渠道，供前端渠道配置使用

- **[backend/models]**: `GET /api/models` 新增模型展示字段
  - 返回 `upstream_channel`
  - 返回 `display_name`（格式：`[channel_or_default] model`）
  - 前端模型下拉改为显示 `display_name`，提交仍使用原始 `model`

- **[frontend/admin]**: `/admin/pricing` 模型列增加渠道前缀展示
  - 显示格式：`[channel_or_default] model`
  - 保留原始 model 作为次级信息

### 新增

- **[backend/tests]**: 新增与更新测试
  - `backend/tests/test_models_api.py`（模型展示名与渠道字段）
  - `backend/tests/test_admin_upstream_models.py` 增补渠道列表接口覆盖

### 验证

- **[backend]**: 执行 `source ".venv/bin/activate" && pytest backend/tests -q` 通过（25 passed）
- **[frontend]**: 执行 `npm --prefix frontend run lint` 与 `npm --prefix frontend run build` 通过

## [0.2.26] - 2026-02-07

### 变更

- **[backend/upstream]**: 新增“按 `upstream_channel` 选择上游”的运行时路由能力
  - 新增 `REALMOI_UPSTREAM_CHANNELS_JSON` 配置（JSON 映射 `channel -> base_url/api_key/models_path`）
  - generate 阶段根据 `model_pricing.upstream_channel` 解析渠道，并覆盖容器 `OPENAI_BASE_URL`
  - generate 阶段按渠道动态下发 `/codex_home/auth.json`，确保 `OPENAI_API_KEY` 与渠道一致

- **[backend/admin]**: `GET /api/admin/upstream/models` 支持 `channel` 查询参数
  - 可按渠道查看上游模型列表
  - 上游 models 结果缓存改为按渠道隔离

- **[frontend/admin]**: `/admin/upstream-models` 新增渠道输入框
  - 留空查询默认上游
  - 填写渠道后查询对应上游

### 新增

- **[backend/tests]**: 新增多渠道能力测试
  - `backend/tests/test_upstream_channels.py`（渠道解析）
  - `backend/tests/test_admin_upstream_models.py`（admin 上游模型渠道查询）
  - `backend/tests/test_job_manager_upstream_channel.py`（generate 阶段按模型渠道路由）

### 验证

- **[backend]**: 执行 `source ".venv/bin/activate" && pytest backend/tests -q` 通过（23 passed）
- **[frontend]**: 执行 `npm --prefix frontend run lint` 与 `npm --prefix frontend run build` 通过

## [0.2.25] - 2026-02-07

### 变更

- **[backend/admin]**: 为模型定价配置新增 `upstream_channel` 字段并开放管理接口读写
  - `model_pricing` 增加 `upstream_channel`（字符串）
  - `GET /api/admin/pricing/models` 返回该字段
  - `PUT /api/admin/pricing/models/{model}` 支持更新该字段（自动 `trim`）
  - 兼容已存在数据库：启动时自动补齐缺失列

- **[frontend/admin]**: `/admin/pricing` 支持编辑“上游渠道（upstream_channel）”
  - 新增模型时可填写 `upstream_channel`
  - 模型列表新增 `upstream_channel` 可编辑列，并随“保存”一并提交

### 新增

- **[backend/tests]**: 新增 `backend/tests/test_admin_pricing_channel.py`
  - 覆盖 `upstream_channel` 的创建、读取、更新保持行为

### 验证

- **[backend]**: 执行 `source ".venv/bin/activate" && pytest backend/tests/test_admin_pricing_channel.py backend/tests/test_jobs.py -q` 通过（3 passed）
- **[backend]**: 执行 `source ".venv/bin/activate" && pytest backend/tests -q` 通过（17 passed）
- **[frontend]**: 执行 `npm --prefix frontend run lint` 与 `npm --prefix frontend run build` 通过

## [0.2.24] - 2026-02-07

### 改进

- **[frontend/billing]**: 将 `/billing` KPI 卡片层级与 `/admin/billing` 进一步对齐
  - 卡片布局改为同款 6 项结构（费用、记录、覆盖/范围、总 Tokens、交互 Tokens、缓存 Tokens）
  - 记录卡补齐已定价/未定价说明，费用卡补齐 microusd 明细
  - 保留用户账单语义下的差异化指标（缓存命中率、时间窗）

### 验证

- **[frontend]**: 执行 `npm --prefix frontend run lint` 与 `npm --prefix frontend run build` 通过

## [0.2.23] - 2026-02-07

### 改进

- **[frontend/billing]**: 将 `/billing` 筛选交互与 `/admin/billing` 对齐
  - 筛选区改为可折叠 `<details>` 结构，展示“当前生效条件”
  - 切换为草稿态编辑（快捷范围与日期输入仅更新草稿）
  - 新增“草稿未应用”状态提示与“筛选已生效/应用筛选”按钮文案
  - 仅在点击“应用筛选”后触发真实查询（并重置分页游标）

### 验证

- **[frontend]**: 执行 `npm --prefix frontend run lint` 与 `npm --prefix frontend run build` 通过

## [0.2.22] - 2026-02-07

### 改进

- **[frontend/billing]**: 将 `/billing` 按天趋势升级为双轴图（Tokens 柱状 + Cost 折线）
  - 左轴表达 daily tokens，右轴表达 daily cost
  - 同步保留日期、费用、缓存命中率等日维度标签
  - 与现有筛选条件联动，自动按查询窗口刷新

### 验证

- **[frontend]**: 执行 `npm --prefix frontend run lint` 与 `npm --prefix frontend run build` 通过

## [0.2.21] - 2026-02-07

### 新增

- **[backend/billing]**: 新增 `GET /api/billing/daily` 用户侧按天趋势接口
  - 基于 `start/end` 返回按天聚合点位（records/tokens/cache_ratio/cost）
  - 输出补齐空白日期，保证前端趋势图时间轴连续

- **[frontend/billing]**: 新增 `/billing` “按天趋势”可视化区块
  - 柱高表示当日总 Tokens
  - 同步展示当日费用与缓存命中率
  - 与现有筛选联动（start/end 变化后自动刷新趋势）

### 验证

- **[backend]**: 执行 `source ".venv/bin/activate" && pytest backend/tests/test_billing.py -q` 通过（3 passed）
- **[backend]**: 执行 `source ".venv/bin/activate" && pytest backend/tests -q` 通过（16 passed）
- **[frontend]**: 执行 `npm --prefix frontend run lint` 与 `npm --prefix frontend run build` 通过

## [0.2.20] - 2026-02-07

### 变更

- **[backend/billing]**: 重构用户账单接口为“范围聚合 + 游标明细 + 单条拆解”三层结构
  - 新增 `GET /api/billing/windows`（时间范围聚合）
  - 新增 `GET /api/billing/events`（按 `created_at desc, id desc` 游标分页）
  - 新增 `GET /api/billing/events/{record_id}/detail`（单条价格快照 + 成本拆解）
  - 保留 `GET /api/billing/summary` 兼容旧调用
  - 修复游标比较中的时区兼容问题（SQLite naive/aware datetime）

- **[frontend/billing]**: 重构 `/billing` 页面信息架构，保留现有玻璃背景/边框视觉，仅替换内容组织
  - 顶部：查询范围与刷新状态（含 60 秒自动刷新）
  - 中部：KPI（总费用、请求数、总 token、缓存命中率、定价覆盖率）+ token 结构卡片
  - 底部：明细表 + 游标翻页 + 行展开费用拆解
  - 筛选持久化：`start/end/limit` 写入 localStorage，刷新后保持

### 新增

- **[backend/tests]**: 新增 `backend/tests/test_billing.py`
  - 覆盖 `windows` 聚合统计
  - 覆盖 `events` 游标分页
  - 覆盖 `detail` 成本拆解与跨用户访问权限隔离

### 验证

- **[backend]**: 执行 `source ".venv/bin/activate" && pytest backend/tests/test_billing.py -q` 通过（2 passed）
- **[backend]**: 执行 `source ".venv/bin/activate" && pytest backend/tests -q` 通过（15 passed）
- **[frontend]**: 执行 `npm --prefix frontend run lint` 与 `npm --prefix frontend run build` 通过

## [0.2.19] - 2026-02-07

### 改进

- **[frontend/admin]**: `/admin/billing` 筛选交互改为“草稿态 + 手动应用”
  - 输入筛选条件时不再自动触发请求（避免每次输入都刷新数据）
  - 仅点击“应用筛选”后更新请求条件并拉取数据
  - 新增“草稿未应用”提示与“筛选已生效”状态按钮

### 验证

- **[frontend]**: 执行 `npm --prefix frontend run lint` 与 `npm --prefix frontend run build` 通过

## [0.2.18] - 2026-02-07

### 改进

- **[frontend/admin]**: 优化 `/admin/billing` 信息层级，避免筛选区挤占首屏关键指标
  - 首屏优先展示 KPI（费用、记录、活跃用户/模型、Token 结构）
  - 将筛选区改为可折叠区域（`<details>`），默认收起
  - 在筛选标题展示当前生效条件摘要（时间范围 / owner / model）

### 验证

- **[frontend]**: 执行 `npm --prefix frontend run lint` 与 `npm --prefix frontend run build` 通过

## [0.2.17] - 2026-02-07

### 变更

- **[backend/admin]**: 重构 `/api/admin/billing/summary` 为面向管理看板的数据结构
  - 新增查询参数：`range_days`、`top_limit`、`recent_limit`
  - 返回内容升级：`query`、`total`、`top_users`、`top_models`、`recent_records`
  - 支持已定价/未定价记录分离统计，并输出可读金额（`amount`）

- **[frontend/admin]**: 重构 `/admin/billing` 信息架构，替换原 JSON 直出视图
  - 顶部 KPI：总费用、记录数、活跃用户/模型、Token 结构
  - 中部榜单：Top 用户、Top 模型
  - 底部明细：最近 usage 记录表（时间/用户/模型/job/stage/tokens/cost）
  - 新增筛选：时间范围、owner_user_id、model、Top 条数、明细条数

### 新增

- **[backend/tests]**: 新增 `backend/tests/test_admin_billing.py`
  - 覆盖范围：时间窗过滤、Top 用户聚合、owner/model 组合过滤、recent records 返回结构

### 验证

- **[backend]**: 执行 `source ".venv/bin/activate" && pytest backend/tests -q` 通过（13 passed）
- **[frontend]**: 执行 `npm --prefix frontend run lint` 与 `npm --prefix frontend run build` 通过

## [0.2.16] - 2026-02-06

### 修复

- **[frontend/ui]**: 修复 overlay 顶栏与页面主题区边框视觉叠加问题
  - 将业务页主内容容器上边距由 `pt-5` 调整为 `pt-8`
  - 覆盖页面：`/billing`、`/settings/codex`、`/admin/users`、`/admin/pricing`、`/admin/upstream-models`、`/admin/billing`

### 验证

- **[frontend]**: 执行 `npm -C frontend run lint` 与 `npm -C frontend run build` 通过

## [0.2.15] - 2026-02-06

### 变更

- **[frontend/ui]**: 按用户要求进一步收口为“与 `/` 页面完全一致”的外层样式
  - 业务页面统一使用 `/` 同款壳层：`pt-14 + selection + overflow` 结构
  - 业务页面导航统一切换为 `AppHeader mode=\"overlay\"`
  - 登录/注册页容器层级对齐 `/` 的画布结构

### 验证

- **[frontend]**: 执行 `npm -C frontend run lint` 与 `npm -C frontend run build` 通过

## [0.2.14] - 2026-02-06

### 变更

- **[frontend/ui]**: 按用户要求将全站背景统一对齐 `/` 页面样式，全部切回亮背景
  - 登录/注册、Billing、Settings、Admin 全页面改为复用 `FluidBackground`
  - 移除页面层对 `realm-bg-dark` 的使用，确保视觉一致

### 验证

- **[frontend]**: 执行 `npm -C frontend run lint` 与 `npm -C frontend run build` 通过

## [0.2.13] - 2026-02-06

### 变更

- **[frontend/ui]**: 调整全站背景层级，形成“首页 New Job 更亮、其余页面显著更暗”的视觉分层
  - 首页助手（`/`）：保留 `FluidBackground` 亮色基调
  - 其余页面：统一切换为 `realm-bg-dark` 深色背景

### 改进

- **[frontend/ui]**: 修复多处图标上下左右未对齐问题（输入面板、样例删除、发送按钮、返回按钮、移动端返回）
  - 新增通用图标对齐样式：`icon-wrap`
  - 将文本符号图标（`➔`、`×`、`←`）替换为统一 SVG 图标

### 验证

- **[frontend]**: 执行 `npm -C frontend run lint` 与 `npm -C frontend run build` 通过

## [0.2.12] - 2026-02-05

### 变更

- **[frontend]**: 完成“基于 New Job + Job Detailed 风格”的全站 UI 重构落地
  - 覆盖页面: `/login`、`/signup`、`/billing`、`/settings/codex`、`/admin/users`、`/admin/pricing`、`/admin/upstream-models`、`/admin/billing`
  - 公共组件: `globals.css` 设计 token、`AppHeader`、`Form`、`AuthCard`、`RequireAuth`、`RequireAdmin`

### 新增

- **[frontend]**: 新增历史路由兼容重定向页面
  - `/jobs` → `/`
  - `/jobs/[jobId]` → `/`

### 说明

- **[frontend]**: 执行 `npm -C frontend run lint` 与 `npm -C frontend run build` 均通过

## [0.2.11] - 2026-02-05

### 新增

- **[helloagents]**: 新建全站 UI 重设计实施规划方案包（基于 `new job` + `job detailed` 风格）
  - 方案: [202602060616_full-ui-redesign-cockpit-style](plan/202602060616_full-ui-redesign-cockpit-style/)
  - 交付: proposal + tasks + FigJam 信息架构图

### 改进

- **[kb]**: 更新知识库索引与 frontend 模块文档，标记“设计先行”到“可实施规划”状态切换

## [0.2.10] - 2026-02-03

### 变更

- **[frontend]**: 按用户要求先交付设计稿，撤回 Liquid Glass 前端代码落地（实现留待后续按设计执行）

### 新增

- **[designs]**: 新增/更新全站 Liquid Glass UI 设计稿 `designs/realmoi_ui.pen`（仅设计稿，尚未落地到前端代码）
  - 方案: [202602031250_liquid-glass-frontend-redesign](plan/202602031250_liquid-glass-frontend-redesign/)
  - 决策: liquid-glass-frontend-redesign#D001(不引入 UI 库), liquid-glass-frontend-redesign#D002(深色终端玻璃面板 + xterm 透明背景), liquid-glass-frontend-redesign#D003(全站样式以 Portal/Cockpit 为基准)

## [0.2.9] - 2026-02-02

### 变更

- **[frontend]**: 恢复独立路由页面（Jobs/Billing/Codex Settings/Admin）并在主页加入导航链接（不改后端接口）
  - 页面：`/jobs`、`/jobs/{job_id}`、`/billing`、`/settings/codex`、`/admin/*`

## [0.2.8] - 2026-02-02

### 变更

- **[frontend]**: 将新调题助手 UI 设为主页 `/`，并移除旧的 Jobs/Admin/Billing/Settings 前端路由（仅保留 `/login`、`/signup`）
  - 方案: [202602021229_assistant-homepage](archive/2026-02/202602021229_assistant-homepage/)
  - 决策: assistant-homepage#D001(删除旧路由文件)

## [0.2.7] - 2026-02-01

### 新增

- **[frontend]**: 新增 `/assistant` 新调题助手 UI（Portal/Cockpit），复用现有 Job + SSE + artifacts 链路（不在浏览器端直连 LLM）
  - 方案: [202602020619_assistant-ui-migration](archive/2026-02/202602020619_assistant-ui-migration/)
  - 决策: assistant-ui-migration#D001(落地为 Next.js /assistant), assistant-ui-migration#D002(testCases → tests.zip)

## [0.2.6] - 2026-02-01

### 新增

- **[designs]**: 新增全站 UI 设计稿 `designs/realmoi_chatgpt_ui.pen`（ChatGPT Web 风格 1:1 草稿）
  - 方案: [202602011701_chatgpt_ui_redesign](plan/202602011701_chatgpt_ui_redesign/)

### 改进

- **[designs]**: `/jobs` 默认右侧展示“新建题目/Job”表单，替换“选择一个 Job”的空态
- **[designs]**: New Job 表单精简：移除 Search mode / Max tokens / Temperature；测试数据默认手动输入，`tests.zip` 作为备选
- **[designs]**: New Job 表单结构调整：左侧分页（题面数据/代码）+ 顶部模型选择；样例输入/输出双栏并支持多条

## [0.2.5] - 2026-02-01

### 修复

- **[backend/docker]**: 修复 generate 容器 `tmpfs /codex_home` 导致 `auth.json/config.toml` 在容器启动后被覆盖隐藏的问题（最终表现为 Codex 401“未提供 Token”）
- **[backend/docker]**: `tmpfs /tmp` 显式开启 `exec`，修复 test 阶段运行编译产物时报 `PermissionError: ... /tmp/work/prog`
- **[backend/docker]**: generate/test 容器 name 增加 attempt 后缀（`*_a{attempt}`），修复质量重试时的容器命名冲突；同时增加 label `realmoi.attempt`
- **[scripts]**: `scripts/cleanup_jobs.py` 按 label `realmoi.job_id` 清理该 Job 的所有容器（兼容多 attempt）

### 改进

- **[runner]**: generate 阶段将 Codex 的 command execution / error / usage 摘要实时写入容器 stdout（前端 xterm 可见），同时仍保留完整 JSONL 到 artifacts
- **[runner]**: 生成提示词更新：自检 report 路径与实际 runner 行为一致，并引导通过 `status_update()` 写入 `agent_status.jsonl`

## [0.2.4] - 2026-02-01

### 新增

- **[scripts]**: 新增端到端实战脚本 `scripts/e2e_knapsack.py`：创建 01 背包模板题 Job（含 tests.zip）并等待跑完，断言 report 通过
- **[devx]**: 新增 `make e2e-knapsack` 便捷入口

### 修复

- **[backend]**: `/api/admin/upstream/models` 支持 `REALMOI_OPENAI_BASE_URL` 带 `/v1` 的场景，避免拼接出 `/v1/v1/models`

## [0.2.3] - 2026-02-01

### 修复

- **[backend]**: 修复 Docker bind mount 使用相对路径会被当作 volume name 的问题（统一使用绝对路径挂载 job 目录）
  - 影响：避免 Job 在 create container 阶段直接失败
- **[backend]**: generate/test 容器改为以宿主机 `uid:gid` 运行（仍保持 `cap_drop=ALL` + `no-new-privileges`）
  - 影响：避免无 `CAP_DAC_OVERRIDE` 时无法写入 bind mount（如 `/job/output`）
- **[runner/backend]**: test 阶段 `report.json` 落盘到 job 输出目录（避免 `/tmp` tmpfs 在容器退出后内容丢失），并由后端汇总复制为 `output/report.json`

## [0.2.2] - 2026-02-01

### 修复

- **[frontend]**: 补齐 `/settings/codex` 页面：每用户 Codex overrides 编辑 + effective config.toml 只读预览
  - 方案: [202601311605_oi_tuner_mvp](archive/2026-01/202601311605_oi_tuner_mvp/)
- **[devx]**: `make runner-build` 改为每次都执行 `docker build`（依赖缓存），避免 runner 代码更新后仍使用旧镜像
  - 方案: [202601311605_oi_tuner_mvp](archive/2026-01/202601311605_oi_tuner_mvp/)
- **[runner]**: 修正 Search 模式开关：`cached/disabled` 通过 `--config web_search=...` 显式控制（避免 full-access/yolo 默认 live）
  - 方案: [202601311605_oi_tuner_mvp](archive/2026-01/202601311605_oi_tuner_mvp/)
- **[runner]**: generate 阶段从 `CODEX_HOME/auth.json` 注入 `OPENAI_API_KEY`，确保 Codex CLI 在容器内非交互可用
  - 方案: [202601311605_oi_tuner_mvp](archive/2026-01/202601311605_oi_tuner_mvp/)
- **[backend]**: 修正 base `config.toml`：移除无效 key（避免 Codex CLI 解析异常）
  - 方案: [202601311605_oi_tuner_mvp](archive/2026-01/202601311605_oi_tuner_mvp/)

## [0.2.1] - 2026-02-01

### 新增

- **[devx]**: 新增 `Makefile`，支持 `make dev` 一键启动（后端 + 前端）与 `make test`
  - 方案: [202601311605_oi_tuner_mvp](archive/2026-01/202601311605_oi_tuner_mvp/)

## [0.2.0] - 2026-02-01

### 新增

- **[backend]**: FastAPI 后端（开放注册/JWT、Job 会话管理、Docker 两阶段编排、SSE 终端与状态流、用量计费、用户 Codex 配置）
  - 方案: [202601311605_oi_tuner_mvp](archive/2026-01/202601311605_oi_tuner_mvp/)
- **[runner]**: `realmoi-runner` 镜像（Codex CLI 0.92.0 + generate/test + MCP 状态回传）
  - 方案: [202601311605_oi_tuner_mvp](archive/2026-01/202601311605_oi_tuner_mvp/)
- **[frontend]**: Next.js 前端（Jobs/New/Detail、xterm.js 终端回放、Admin 面板、Billing、Codex Settings）
  - 方案: [202601311605_oi_tuner_mvp](archive/2026-01/202601311605_oi_tuner_mvp/)
- **[scripts]**: 自动清理脚本 `scripts/cleanup_jobs.py`（容器结束后保留 7 天；用于 system cron 每天 00:00 执行）
  - 方案: [202601311605_oi_tuner_mvp](archive/2026-01/202601311605_oi_tuner_mvp/)

### 修复

- **[backend]**: 固定 `bcrypt==4.2.0`，避免与 `passlib` 在 `bcrypt>=5` 上的兼容性问题
  - 方案: [202601311605_oi_tuner_mvp](archive/2026-01/202601311605_oi_tuner_mvp/)

## [0.1.0] - 2026-01-31

### 新增

- **[helloagents]**: 初始化 HelloAGENTS 知识库结构（INDEX/context/modules/archive）
  - 方案: [202601311605_oi_tuner_mvp](archive/2026-01/202601311605_oi_tuner_mvp/)
- **[helloagents]**: 形成 MVP 方案包（需求、技术栈、接口、Runner、计费、Admin、清理策略）
  - 方案: [202601311605_oi_tuner_mvp](archive/2026-01/202601311605_oi_tuner_mvp/)
