# realmoi

OI/算法竞赛「调题助手」MVP：用户提交题面 +（可选）tests.zip +（可选）当前 C++ 代码，并可选择模型思考量（`low/medium/high/xhigh`）；后端启动 Docker 容器在容器内调用 Codex CLI 生成 `main.cpp`，并在隔离的 test 容器内编译/跑完全部 tests，前端可实时观看终端输出与状态时间线。

## 1. 组件

- `backend/`：FastAPI（用户系统 / Job / Docker 管理 / 用量计费）
- `runner/`：Docker 镜像（Codex CLI + C++ 编译器 + runner 脚本）
- `frontend/`：Next.js（主页为新调题助手 UI：Portal/Cockpit；另含登录/注册）
- `scripts/cleanup_jobs.py`：清理已完成且过期（默认 7 天）的 job 与容器（用于 cron）

## 2. 快速开始（开发环境）

### 2.0 一键启动（推荐）

在项目根目录创建 `.env`（git 已忽略），至少配置：

```bash
REALMOI_OPENAI_API_KEY="YOUR_KEY"
REALMOI_OPENAI_BASE_URL="https://api.openai.com"
```

然后：

```bash
make dev
```

启动后可在管理后台 `http://localhost:3000/admin/upstream-models` 直接新增/编辑上游渠道配置（持久化到数据库），并按渠道聚合查看上游模型列表。

### 2.1 构建 runner 镜像

```bash
docker build -t realmoi-runner:dev runner
```

### 2.2 启动后端

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements.txt

export REALMOI_OPENAI_BASE_URL="https://api.openai.com"
export REALMOI_OPENAI_API_KEY="YOUR_KEY"
# 可选：多上游渠道映射（按模型的 upstream_channel 路由）
# export REALMOI_UPSTREAM_CHANNELS_JSON='{"openai-cn":{"base_url":"https://api.openai.com/v1","api_key":"YOUR_CN_KEY","models_path":"/v1/models"}}'
export REALMOI_JWT_SECRET="change-me"
export REALMOI_ADMIN_USERNAME="admin"
export REALMOI_ADMIN_PASSWORD="admin-password-123"
export REALMOI_RUNNER_IMAGE="realmoi-runner:dev"

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

前提：已配置上游 Key（`REALMOI_OPENAI_API_KEY`）与 Base URL，并已启动后端（推荐直接 `make dev`）。

然后在另一个终端执行：

```bash
make e2e-knapsack
```

说明：
- 默认使用 `gpt-5.2-codex`（可用 `REALMOI_E2E_MODEL` 覆盖）
- 默认 `search_mode=disabled`（避免不必要的检索开销）
