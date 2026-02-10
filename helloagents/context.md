# 项目上下文：OI 调题助手（MVP）

## 背景

目标是为 OI/算法竞赛用户提供“调题”辅助：用户提供题面、数据与当前代码（可为空），系统在 Docker 容器内调用 Codex CLI 生成 C++ 解法，并把执行过程（终端输出）实时展示给用户。

## MVP 约束与偏好（已确认）

- 语言：仅支持 C++
- Agent：Codex CLI（非交互 `codex exec`）
- 上游：OpenAI Responses（OpenAI-compatible），由外部传入 `OPENAI_BASE_URL` 与 `CODEX_API_KEY/OPENAI_API_KEY`
- 搜索：Codex 官方 Search 工具可用，允许联网检索
- 后端：尽量极简，仅负责 Docker 镜像/容器管理与 Codex 交互、日志转发与产物回传
- 并发：可能有多个用户同时使用，需要支持多 job 并行与多容器管理（暂不做并发上限/排队）
- 保留与清理：容器结束后保留会话与对话日志 7 天，之后由系统 cron 自动清理（每天 00:00 执行）
- 用户体系：支持多用户管理；用户分为普通用户与管理员；默认开放注册；任务/会话需归属到用户并做访问控制
- 用量与计费：Token 从上游 usage 获取并缓存（含 cached_input/cached_output）；价格本地配置并计算成本（四类 tokens 独立单价）
- 模型选择：管理员从上游 models 列表中选择并配置本地价格/启用；用户创建 job 时仅从管理员启用的本地模型列表中选择

## 技术栈（当前实现，SSOT）

- 后端：Python 3.12 + FastAPI + Uvicorn + SQLAlchemy（SQLite）+ PyJWT + passlib(bcrypt) + docker SDK（容器管理）
- 前端：Next.js（App Router）+ React + TailwindCSS + xterm.js（终端渲染）
  - 入口：主页（新调题助手 UI，`/`）
- Runner 镜像：`runner/Dockerfile` 构建 `realmoi-runner:dev`（Node 22 + Codex CLI 0.98.0 + g++ C++20 + Python；内置 stdio MCP server）
- 部署与发版：`docker-compose.yml` + `Dockerfile.backend` + `Dockerfile.frontend`；GitHub Tag (`v*`) 触发 Docker 镜像发布
- 传输：
  - REST：`/api/*`
  - MCP：`GET /api/mcp/ws`（Job 创建/启动/取消/订阅通知；独立测评机也通过该入口与后端交互）
  - 实时输出：MCP notifications（`agent_status` 主流 + `terminal` 回退流）
- 存储：
  - 数据库：`data/realmoi.db`（用户、模型价格、用量记录）
  - Job 文件：`jobs/{job_id}/`（input/output/logs/state）

## 关键风险提示（待最终决策）

- “容器可全网访问”不等于安全：若同一容器既持有 Key 又编译运行生成代码，存在 Key 外泄与外联风险。
- 建议采用“两阶段同镜像”执行：阶段1（有网+有 Key）只跑 Codex；阶段2（无网+无 Key）只编译运行测试。
