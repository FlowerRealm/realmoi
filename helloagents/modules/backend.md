# 模块：backend（FastAPI）

## 职责

- 提供用户系统（开放注册、JWT 登录、`user/admin` 角色）与管理员接口
- Job 会话管理：创建/启动/取消/列表/详情；落盘 job 目录；重启后 reconcile
- Docker 容器编排：两阶段（generate/test）创建、日志采集、产物回传
- 用量与计费：从 runner 输出的 `usage.json` 写入 `usage_records`，按本地 `model_pricing` 计算成本

## 目录结构（关键路径）

- `backend/app/main.py`：应用入口（FastAPI）、bootstrap admin、同步 `auth.json`、初始化 JobManager
- `backend/app/judge_daemon.py`：独立测评机守护进程（轮询 `queued` 任务并抢占执行；全程通过 MCP 与 backend 交互）
- `backend/app/routers/*`：
  - `auth.py`：`/api/auth/*`
  - `jobs.py`：`/api/jobs/*`（REST Job 管理接口；实时输出以 MCP notifications 为准）
  - `mcp.py`：`/api/mcp/ws`（WebSocket MCP 网关：用户侧 tools + judge worker tools，共用单一入口）
  - `models.py`：`/api/models`（用户可选模型；仅返回绑定“已启用渠道”的模型，并附 `display_name` 渠道前缀）
  - `settings.py`：`/api/settings/codex`（每用户配置）
  - `admin.py`：`/api/admin/*`（用户管理、上游 channels/models 配置、模型价格、全站账单看板聚合）
  - `billing.py`：用户账单接口（`/api/billing/summary` + `/api/billing/windows` + `/api/billing/events` + `/api/billing/events/{record_id}/detail`）
- `backend/app/services/*`：
  - `job_manager.py`：Job 调度与执行（embedded 模式内线程 / independent 模式队列+抢占）、generate/test 串联、质量重试、用量入库
  - `mcp_judge.py`：独立测评机 MCP tools（`judge.*` 数据面 + 控制面），供 `routers/mcp.py` 注入到统一网关
  - `docker_service.py`：容器创建（含资源限额）、日志采集、容器文件拷贝
  - `zip_safe.py`：tests.zip 安全解包
  - `codex_config.py`：base config + 用户 overrides 合成 `config.toml`（内置 realmoi MCP server）
  - `pricing.py`：四类 token 成本计算（microusd）

## 生成链路通道控制

- 新增配置：`REALMOI_RUNNER_CODEX_TRANSPORT`（`appserver/exec/auto`，默认 `appserver`）
- `job_manager._run_generate()` 会将该配置透传为容器/本地 runner 环境变量 `REALMOI_CODEX_TRANSPORT`
- 当 runner 走 appserver 时，前端通过 MCP `job.subscribe` 接收 `agent_status` 通知即可展示结构化增量（无需新增 API）

## 环境变量（前缀 REALMOI_）

- Upstream：
  - `REALMOI_OPENAI_BASE_URL`：上游 Base URL（默认 `https://api.openai.com`）
    - 兼容两种写法：`https://host` 或 `https://host/v1`（`/api/admin/upstream/models` 会自动去重 `/v1`）
  - `REALMOI_OPENAI_API_KEY`：上游 Key（写入 `data/secrets/codex/auth.json`，并注入 generate 容器）
  - `REALMOI_UPSTREAM_MODELS_PATH`：默认 `/v1/models`
  - `REALMOI_UPSTREAM_CHANNELS_JSON`：可选，多上游渠道映射（JSON）
    - 示例：`{"openai-cn":{"base_url":"https://api.openai.com/v1","api_key":"sk-...","models_path":"/v1/models"}}`
    - 行为：当模型配置了 `upstream_channel` 时，generate 阶段按该渠道覆盖 `OPENAI_BASE_URL` 和 `OPENAI_API_KEY`
- Auth：
  - `REALMOI_JWT_SECRET`
  - `REALMOI_JWT_TTL_SECONDS`（默认 86400）
  - `REALMOI_ALLOW_SIGNUP`（默认 true）
  - `REALMOI_ADMIN_USERNAME`/`REALMOI_ADMIN_PASSWORD`（首次启动 bootstrap admin）
- Paths：
  - `REALMOI_DB_PATH`（默认 `data/realmoi.db`）
  - `REALMOI_JOBS_ROOT`（默认 `jobs/`）
  - `REALMOI_CODEX_AUTH_JSON_PATH`（默认 `data/secrets/codex/auth.json`）
- Runner / Docker：
  - `REALMOI_RUNNER_IMAGE`（默认 `realmoi/realmoi-runner:latest`）
  - `REALMOI_DOCKER_API_TIMEOUT_SECONDS`
  - `REALMOI_JUDGE_MODE`（`embedded` / `independent`，默认 `embedded`）
  - `REALMOI_JUDGE_MACHINE_ID`（独立测评机标识，默认 hostname+pid）
  - `REALMOI_JUDGE_POLL_INTERVAL_MS`（独立测评机轮询间隔，默认 1000）
  - `REALMOI_JUDGE_LOCK_STALE_SECONDS`（抢占锁过期秒数，默认 120）
  - `REALMOI_JUDGE_MCP_TOKEN`（独立测评机 MCP 连接鉴权 token；backend 与 judge 必须一致）
  - `REALMOI_JUDGE_WORK_ROOT`（judge 的本地 job 临时工作目录；默认：
    - local runner：`/tmp/realmoi-judge-work`
    - docker runner：`{REALMOI_JOBS_ROOT}/.judge-work`）
  - 运行行为：创建 generate/test 容器前会先检查 `REALMOI_RUNNER_IMAGE` 是否存在，本地缺失时自动 pull

## 独立测评机模式（UOJ 风格）

- `POST /api/jobs/{job_id}/start`：
  - `embedded`：立即进入 `running_generate`，由 API 进程内线程执行
  - `independent`：进入 `queued`，等待外部 judge worker 抢占
- 抢占协议：judge worker 通过 MCP 与 backend 协作抢占/释放锁（worker 不直接操作锁文件）
  - WebSocket：`GET /api/mcp/ws`（使用 `REALMOI_JUDGE_MCP_TOKEN` 鉴权）
  - tools（抢占锁）：`judge.claim_next` / `judge.release_claim`
  - tools（输入/状态/日志/产物）：`judge.input.list` / `judge.input.read_chunk` / `judge.job.get_state` / `judge.job.patch_state` / `judge.job.append_terminal` / `judge.job.append_agent_status` / `judge.job.put_artifacts`
  - tools（generate 配置/计费）：`judge.prepare_generate` / `judge.usage.ingest`
  - 锁文件：backend 仍在 `jobs/{job_id}/logs/judge.lock` 落盘原子锁（O_EXCL 创建，支持 stale lock 自动回收）
- 取消任务：独立模式下本地执行支持按 `state.json` 记录的 PID 进行跨进程终止（不依赖同进程内存态）
- MCP 自测工具（推荐，Codex 生成阶段调用）：`judge.self_test`
  - 入参：`{"main_cpp":"<完整源码>","timeout_seconds":90}`（timeout 可选）
  - 返回重点：`ok/status/first_failure_*`
  - 返回：`status + compile_ok + summary + report`

## 核心数据

- DB（SQLite）：
  - `users`
  - `model_pricing`（含 `upstream_channel`、价格字段、启用状态）
  - `upstream_channels`（渠道配置：base_url/api_key/models_path/is_enabled）
  - `usage_records`
  - `user_codex_settings`
- Job 落盘目录：`jobs/{job_id}/`
  - `input/job.json`：题面、模型、search_mode、tests 配置与 limits
  - `state.json`：状态机、容器 id/name/exit_code、expires_at
  - `output/*`：`main.cpp/solution.json/report.json` 与 attempt artifacts
  - `logs/terminal.log`：实时终端落盘（MCP `terminal` 通知源）
  - `logs/agent_status.jsonl`：生成/测试阶段状态流（MCP `agent_status` 通知源；由 runner 通过 MCP 工具写入）

## 本地开发

- 推荐：项目根目录执行 `make dev`（本地安装依赖并启动后端/前端，不会触发 Docker 构建）
- 若 `8000/3000` 端口被占用但检测到已运行的 realmoi backend 在监听：`make dev` 会复用该 backend 并继续启动剩余组件；否则会失败并打印诊断信息。也可使用 `make dev BACKEND_PORT=8001 FRONTEND_PORT=3001` 显式覆盖
- 任务执行阶段仍会使用 `REALMOI_RUNNER_IMAGE` 创建容器（默认镜像按需自动拉取）
- 单独启动后端：`uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000`

## 用户管理接口（admin）

- 路由：
  - `GET /api/admin/users`：用户列表（分页）
    - 参数：`q`（username like）、`role`（`user/admin`）、`is_disabled`（bool）、`limit`、`offset`
  - `POST /api/admin/users`：创建用户
    - body：`username/password/role/is_disabled`
  - `PATCH /api/admin/users/{user_id}`：更新用户
    - body：`role` / `is_disabled`
    - 约束：不能禁用自己；必须保留至少 1 个启用的 `admin`
  - `POST /api/admin/users/{user_id}/reset_password`：重置密码
    - body：`new_password`（8–72）

## 账单看板接口（admin）

- 路由：`GET /api/admin/billing/summary`
- 可选参数：`owner_user_id`、`model`、`range_days`、`top_limit`、`recent_limit`
- 返回结构：
  - `total`：全局 token/记录/活跃用户模型/费用覆盖率
  - `top_users`：按费用与 token 聚合的用户榜单（含用户名映射）
  - `top_models`：模型维度榜单
  - `recent_records`：最近 usage 明细（时间、用户、模型、job、stage、cost）

## 上游模型接口（admin）

- 路由：
  - `GET /api/admin/upstream/channels`
  - `PUT /api/admin/upstream/channels/{channel}`
  - `DELETE /api/admin/upstream/channels/{channel}`
  - `GET /api/admin/upstream/models`
- 展示策略：
  - `GET /api/admin/upstream/channels` 仅返回“可管理的命名渠道”（DB/env 渠道）
  - 不再返回默认伪渠道（`channel=""`），避免前端出现不可删除的 default 入口
- 可选参数：`channel`
  - 留空：走默认上游（`REALMOI_OPENAI_BASE_URL` + `REALMOI_OPENAI_API_KEY`）
  - 非空：按 `REALMOI_UPSTREAM_CHANNELS_JSON` 中同名渠道请求
  - 若 DB 中存在同名渠道配置，则优先使用 DB 配置
- 连通性策略：
  - `GET /api/admin/upstream/models` 请求上游时固定 `trust_env=False`，避免被宿主机 `HTTP_PROXY/HTTPS_PROXY/ALL_PROXY` 环境变量干扰
  - 上游网络异常时返回 `upstream_unavailable` 并附带异常类型信息，便于排查
- 渠道列表字段：
  - `GET /api/admin/upstream/channels` 仅返回脱敏密钥字段：`api_key_masked` + `has_api_key`
  - 不返回明文 `api_key`，避免前端直接暴露真实密钥
- 渠道更新规则：
  - `PUT /api/admin/upstream/channels/{channel}` 中 `api_key` 可省略
  - 省略或传空时，若该渠道已有密钥则保持不变；新增渠道仍必须提供 `api_key`
- 渠道删除规则：
  - `default` 渠道不可删除
  - 渠道不存在返回 404
  - 若渠道被 `model_pricing.upstream_channel` 引用，返回 409（冲突）
- 用户模型列表规则（`GET /api/models`）：
  - 仅返回 `is_active=true` 且四个价格字段完整的模型
  - 仅返回 `upstream_channel` 非空，且该渠道当前处于启用状态的模型
  - `display_name` 统一格式为 `"[channel] model"`
- 实时模型接口（`GET /api/models/live`）：
  - 按“已启用渠道”实时请求上游模型列表并返回 `model_id + upstream_channel`
  - 与本地 `model_pricing` 按 `(channel, model)` 叠加，缺失价格时价格字段置 0（`USD/1M_TOKENS`）
- Job 创建兼容实时模型（`POST /api/jobs`）：
  - 新增可选字段 `upstream_channel`
  - 新增可选字段 `reasoning_effort`（`low/medium/high/xhigh`，默认 `medium`）
  - 当模型在价格表中不存在或未激活时，只要提供有效且启用的 `upstream_channel` 也允许创建 Job
  - 创建前会校验 `model` 是否存在于该 `upstream_channel` 的实时模型列表
  - 不存在时直接返回 `422 invalid_model`（`Model not enabled on upstream channel`）
  - `state.json` 与 `job.json` 会持久化 `upstream_channel` 与 `reasoning_effort`，generate 阶段优先按渠道路由上游，并将思考量传给 Codex CLI

## 用户账单接口（billing）

- 路由：
  - `GET /api/billing/summary`（兼容旧版累计汇总）
  - `GET /api/billing/windows`（按 `start/end` 时间范围聚合）
  - `GET /api/billing/daily`（按天趋势聚合，补齐空白日期）
  - `GET /api/billing/events`（时间范围 + `limit` + `before_id` 游标分页）
  - `GET /api/billing/events/{record_id}/detail`（单条记录价格快照与费用拆解）
- 数据特性：
  - 仅返回当前登录用户的 usage 记录
  - 明细按 `created_at desc, id desc` 排序，支持稳定翻页
  - detail 接口对跨用户记录返回 404（权限隔离）
  - 成本拆解拆分为 `non_cached_input/output` 与 `cached_input/output` 四条线
