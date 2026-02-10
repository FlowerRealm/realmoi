# 模块：deployment（Docker 部署与发版）

## 目标

- 同时支持两种部署方式：拉取预构建镜像 / 本地构建镜像
- 支持将上游 Key 从“环境变量必填”调整为“可留空，管理员后台配置”
- GitHub 在发布 tag 时自动构建并推送 Docker 镜像

## 关键文件

- `Dockerfile.backend`：后端运行镜像
- `Dockerfile.frontend`：前端运行镜像（Next.js 生产构建）
- `docker-compose.yml`：一键拉起 `backend + judge + frontend`
- `.env.docker.example`：Docker 部署环境变量模板
- `.github/workflows/docker-release.yml`：Tag 触发镜像构建/推送

## 运行方式（拉取镜像）

1. `cp .env.docker.example .env`
2. 在 `.env` 中配置基础项（`REALMOI_OPENAI_API_KEY` 可留空）
3. 执行：
   - `docker compose pull`
   - `docker compose up -d`

## 运行方式（本地构建）

方式 A（推荐）：
- `make docker-up-local`

方式 B（手动）：
1. 构建 runner：
   - `docker build -t realmoi/realmoi-runner:latest runner`
2. 构建 backend/frontend：
   - `docker compose build backend frontend`
3. 启动：
   - `docker compose up -d --no-build`

说明：
- `docker-compose.yml` 已为 `backend/frontend` 增加 `build` 字段，可直接本地构建。
- `docker-compose.yml` 包含独立 `judge` 服务，默认 `REALMOI_JUDGE_MODE=independent`。
- `judge` 服务通过 `REALMOI_JUDGE_MCP_TOKEN` 鉴权连接 `GET /api/mcp/ws`，生产部署必须覆盖默认值。
- `Makefile` 新增：
  - `docker-build-local`
  - `docker-up-local`
  - `judge`（本地单独启动独立测评机）

默认镜像：
- `realmoi/realmoi-backend:latest`
- `realmoi/realmoi-frontend:latest`
- `realmoi/realmoi-runner:latest`

可通过 `.env` 覆盖为自定义镜像地址。

## GitHub 自动发布

触发条件：
- `push` 到 `v*` tag（如 `v0.3.0`）
- 手动 `workflow_dispatch`

Secrets（必需）：
- `DOCKERHUB_USERNAME`
- `DOCKERHUB_TOKEN`

Variable（可选）：
- `DOCKERHUB_NAMESPACE`（默认回退到 `DOCKERHUB_USERNAME`）

发布产物：
- `{namespace}/realmoi-backend:{tag,latest}`
- `{namespace}/realmoi-frontend:{tag,latest}`
- `{namespace}/realmoi-runner:{tag,latest}`
