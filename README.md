# realmoi

OI/算法竞赛「调题助手」MVP：用户提交题面 +（可选）tests.zip +（可选）当前 C++ 代码，并可选择模型思考量（`low/medium/high/xhigh`）；后端默认在本机执行 generate/test（不经 Docker），也可切换为 Docker 模式；前端可实时观看终端输出与状态时间线。

## 1. 组件

- `backend/`：FastAPI（用户系统 / Job 执行编排 / 用量计费）
- `runner/`：Docker 镜像（Codex CLI + C++ 编译器 + runner 脚本）
- `backend/app/judge_daemon.py`：独立测评机守护进程（UOJ 风格“Web 后端 + Judge Worker”解耦）
- `frontend/`：Next.js（主页为新调题助手 UI：Portal/Cockpit；另含登录/注册）
- `scripts/cleanup_jobs.py`：清理已完成且过期（默认 7 天）的 job 与容器（用于 cron）

## 2. 快速开始（开发环境）

### 2.0 一键启动（推荐）

在项目根目录创建 `.env`（git 已忽略），推荐配置：

```bash
REALMOI_OPENAI_BASE_URL="https://api.openai.com"
# 可留空；也可以在管理后台按渠道配置
REALMOI_OPENAI_API_KEY=""
```

然后：

```bash
make dev
```

说明：
- `make dev` 只做本地启动（Python venv + npm dev），不会执行 Docker 构建。
- `make dev` 现在默认一键启动：后端 + 前端 + 独立测评机（`REALMOI_JUDGE_MODE=independent`）。
- Job 执行默认走本机 runner（`REALMOI_RUNNER_EXECUTOR=local`）。
- 若你希望回到后端内线程执行，可显式设置 `REALMOI_JUDGE_MODE=embedded` 再执行 `make dev`。
- 如需切换到 Docker runner，设置 `REALMOI_RUNNER_EXECUTOR=docker`，并确保 `REALMOI_RUNNER_IMAGE` 可用。
- 默认 `REALMOI_RUNNER_CODEX_TRANSPORT=appserver`，前端优先使用 `agent_status.sse` 展示真正的实时思考/执行增量；若 appserver 失败会自动回退 `exec`。
- `codex app-server` 的 `summaryTextDelta` 是流式增量（不保证天然按句子边界推送）；当前实现会结合 `summaryPartAdded + summaryIndex + 标点` 在前端做断句缓冲，保证思考行可读且持续实时。

启动后可在管理后台 `http://localhost:3000/admin/upstream-models` 直接新增/编辑上游渠道配置（持久化到数据库），并按渠道聚合查看上游模型列表。

### 2.1 （可选）本地构建 runner 镜像

```bash
docker build -t realmoi/realmoi-runner:latest runner
```

### 2.2 启动后端

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements.txt

export REALMOI_OPENAI_BASE_URL="https://api.openai.com"
# 可选：为空时可在管理后台新增上游渠道并填写 api_key
export REALMOI_OPENAI_API_KEY=""
# 可选：多上游渠道映射（按模型的 upstream_channel 路由）
# export REALMOI_UPSTREAM_CHANNELS_JSON='{"openai-cn":{"base_url":"https://api.openai.com/v1","api_key":"YOUR_CN_KEY","models_path":"/v1/models"}}'
export REALMOI_JWT_SECRET="change-me"
export REALMOI_ADMIN_USERNAME="admin"
export REALMOI_ADMIN_PASSWORD="admin-password-123"
export REALMOI_RUNNER_EXECUTOR="local"
export REALMOI_RUNNER_IMAGE="realmoi/realmoi-runner:latest"
export REALMOI_RUNNER_CODEX_TRANSPORT="appserver"

uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

### 2.3 启动前端

```bash
cd frontend
npm install
# 可选：显式指定后端地址（默认值为 http://0.0.0.0:8000/api）
export NEXT_PUBLIC_API_BASE_URL="http://0.0.0.0:8000/api"
npm run dev
```

说明：
- 若显式配置为 `localhost/127.0.0.1` 且前端为外网访问，前端会自动回退到“当前访问主机:8000/api”。

访问入口：
- 主页（新调题助手 UI）：`http://localhost:3000/`
- 登录：`http://localhost:3000/login`

### 2.4 （可选）启动独立测评机（参考 UOJ 的独立 Judge 进程）

当你希望把 Web API 与评测执行解耦时：

```bash
export REALMOI_JUDGE_MODE=independent
make judge
```

说明：
- `POST /api/jobs/{job_id}/start` 在该模式下会把 Job 置为 `queued`。
- 独立测评机进程会轮询并抢占 `queued` Job 执行。
- Codex 生成阶段不再负责自测；编译与测试统一由独立测评机执行。
- 现已提供外部自测接口，便于 Codex 按需调用：
  - `POST /api/jobs/{job_id}/self-test`
  - Header: `X-Job-Token`（来自 `jobs/{job_id}/input/job.json` 的 `judge.self_test_token`）
  - JSON Body: `{"main_cpp":"<完整 C++20 源码>"}`
  - 建议：Codex 先调用该接口，若 `status != succeeded` 则根据 `summary.first_failure_*` 循环修复后再输出最终答案
- 前端会显示 `已排队，等待测评机` 状态。

## 3. 生产运行要点（MVP）

### 3.1 system cron：每天 00:00 清理

示例（按实际部署路径调整）：

```cron
0 0 * * * /usr/bin/python3 -X utf8 "/opt/realmoi/scripts/cleanup_jobs.py" --jobs-root "/opt/realmoi/jobs" --ttl-days 7 >> "/opt/realmoi/logs/cleanup_jobs.log" 2>&1
```

## 4. 测试

```bash
. .venv/bin/activate
pip install -r backend/requirements-dev.txt
pytest
```

## 5. 实战测试：01 背包（E2E）

前提：已配置可用上游渠道（`REALMOI_OPENAI_API_KEY` 或管理后台渠道 `api_key`）与 Base URL，并已启动后端（推荐直接 `make dev`）。

然后在另一个终端执行：

```bash
make e2e-knapsack
```

说明：
- 默认使用 `gpt-5.2-codex`（可用 `REALMOI_E2E_MODEL` 覆盖）
- 默认 `search_mode=disabled`（避免不必要的检索开销）

## 6. Docker 部署（直接拉取镜像）

### 6.1 准备环境变量

```bash
cp .env.docker.example .env
# 编辑 .env（REALMOI_OPENAI_API_KEY 可留空）
```

### 6.2 拉取并启动

```bash
docker compose pull
docker compose up -d
```

### 6.3 本地构建并启动（不依赖镜像仓库）

方式 A（推荐，一条命令）：

```bash
make docker-up-local
```

方式 B（手动）：

```bash
# 先构建 runner（仅 Docker runner 模式需要）
docker build -t realmoi/realmoi-runner:latest runner

# 再构建 backend/frontend 并启动
docker compose build backend frontend
docker compose up -d --no-build
```

说明：
- `docker-compose.yml` 已支持 `build`（backend/frontend），因此可以直接本地构建。
- Docker 部署默认强制 `REALMOI_RUNNER_EXECUTOR=docker`（开发环境 `make dev` 仍默认 `local`）。
- `docker-compose.yml` 现在包含 `judge` 服务（独立测评机），其 `REALMOI_JUDGE_MODE` 固定为 `independent`；`backend` 默认仍可保持 `embedded` 或按环境变量切换。
- 若你希望使用自定义镜像名，可在 `.env` 设置：
  - `REALMOI_RUNNER_IMAGE=your-namespace/realmoi-runner:local`
  - `REALMOI_BACKEND_IMAGE=your-namespace/realmoi-backend`
  - `REALMOI_FRONTEND_IMAGE=your-namespace/realmoi-frontend`
  - `REALMOI_IMAGE_TAG=local`

### 6.4 构建内置国内源（可关闭/可覆盖）

项目已内置构建镜像源，无需手动 `export`：
- `pip` 默认：`https://mirrors.aliyun.com/pypi/simple`
- `npm` 默认：`https://registry.npmmirror.com`
- `apt` 默认：`http://mirrors.aliyun.com`

默认直接执行即可：

```bash
make docker-up-local
```

如需关闭国内源（回退官方源）：

```bash
REALMOI_BUILD_USE_CN_MIRROR=0 make docker-up-local
```

如需替换为你自己的镜像：

```bash
REALMOI_BUILD_PIP_INDEX_URL="https://mirrors.aliyun.com/pypi/simple" \
REALMOI_BUILD_NPM_REGISTRY="https://registry.npmmirror.com" \
REALMOI_BUILD_APT_MIRROR="http://mirrors.aliyun.com" \
make docker-build-local
```

默认访问：
- 前端：`http://localhost:3000`
- 后端 API：`http://localhost:8000/api`

说明：
- `backend` 容器会挂载 `/var/run/docker.sock`，用于在 `REALMOI_RUNNER_EXECUTOR=docker` 时创建 `REALMOI_RUNNER_IMAGE` 对应的 runner 容器。
- 若本地没有 runner 镜像，后端会在首次 Docker 任务创建时自动 pull `REALMOI_RUNNER_IMAGE`。
- 默认镜像名：
  - `realmoi/realmoi-backend:latest`
  - `realmoi/realmoi-frontend:latest`
  - `realmoi/realmoi-runner:latest`
  可通过 `.env` 覆盖为你自己的命名空间。

## 7. GitHub Tag 自动发布 Docker 镜像

仓库已提供工作流：`.github/workflows/docker-release.yml`

触发方式：
- 推送 tag（如 `v0.3.0`）自动构建并推送 3 个镜像（backend/frontend/runner）

需要在 GitHub Secrets 中配置：
- `DOCKERHUB_USERNAME`
- `DOCKERHUB_TOKEN`（Docker Hub Access Token）

可选 GitHub Variables：
- `DOCKERHUB_NAMESPACE`（不设置时默认使用 `DOCKERHUB_USERNAME` 作为命名空间）
