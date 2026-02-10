# 变更提案: assistant-ui-migration

## 元信息
```yaml
类型: 重构/新功能
方案类型: implementation
优先级: P0
状态: ✅完成
创建: 2026-02-02
```

---

## 1. 需求

### 背景
当前项目已有 `frontend/`（Next.js）用于登录/创建 Job/查看终端与状态流；你新增了一个前端原型 `realm-oi---competitive-programming-assistant/`（Vite + React，来源于 AI Studio 导出），其 UI/交互更贴近“调题助手”的核心体验。

但该前端目前直接在浏览器里调用 `@google/genai`（依赖 `GEMINI_API_KEY`），与本项目的后端 Job 体系（FastAPI + Docker runner + SSE）不一致，也存在把上游 Key 暴露到浏览器的风险。因此需要把它迁移为“调用现有后端 API”的实现，并逐步替换/融合现有 Next.js 前端能力。

### 目标
1) 以 `realm-oi---competitive-programming-assistant` 的 UI/信息架构为基础，在现有 Next.js 前端中提供新的“调题助手”入口（建议 `/assistant`）。
2) 将原有逻辑（模型列表、创建 Job、启动 Job、SSE 实时终端/状态、产物展示、鉴权）迁移并接入新 UI，移除浏览器端直连 LLM。
3) 在不破坏现有 `/jobs/*`、`/admin/*` 能力的前提下，支持逐步替换与回滚（feature flag / 并行入口）。

### 约束条件
```yaml
时间约束: MVP 优先跑通“创建->流式->产物”闭环，再做“继续对话/修复”能力
性能约束: SSE 前端需支持断线重连与 offset 续传（避免重复刷屏）
兼容性约束: 复用现有后端 API（/api/auth, /api/models, /api/jobs*），尽量不改协议；如需扩展需保持向后兼容
业务约束: 上游密钥只存在于后端/runner 环境中，禁止在浏览器端配置与调用
```

### 验收标准
- [ ] 登录后访问 `/assistant` 可进入新 UI（Portal/Cockpit），无需 `GEMINI_API_KEY`
- [ ] 新 UI 可选择模型并创建 Job（`POST /api/jobs`），自动 `start`，并能实时看到终端输出与 agent_status 时间线（SSE）
- [ ] Job 结束后可在新 UI 内查看 `solution.json`（思路/错误原因）、`main.cpp`、`report.json` 摘要
- [ ] 现有 `/jobs/*` 页面功能不回归（仍可正常创建/查看 Job）

---

## 2. 方案

### 技术方案
推荐做法：将 `realm-oi---competitive-programming-assistant/` 的 UI 组件迁移到 `frontend/src/components/assistant/*`，在 Next.js 内新增路由 `/assistant` 承载 UI，并复用现有 `frontend/src/lib/*`（`apiFetch`、`connectSse`、token 管理）对接后端。

核心替换点：把原 Cockpit 中的 `GoogleGenAI` 调用替换为“创建并追踪 Job”的流程。

最小可行闭环（MVP）：
1) Portal：收集题面/代码/测试（tests.zip 上传或结构化测试用例）+ 选择 model/search/limits
2) 创建 Job：`POST /api/jobs`（FormData）→ `POST /api/jobs/{job_id}/start`
3) Cockpit：订阅 `terminal.sse` 与 `agent_status.sse`（offset 续传），并在 Job 完成后拉取 artifacts：
   - `GET /api/jobs/{job_id}/artifacts/solution.json`
   - `GET /api/jobs/{job_id}/artifacts/main.cpp`
   - `GET /api/jobs/{job_id}/artifacts/report.json`

“继续对话/修复”语义（后续迭代）：
- 先按 MVP 方式把每次用户追问视作“创建新 Job”（seed 为上一次 `main.cpp` + 追加指令），并在前端 history 中串联 job 链。
- 若前端侧难以构造 tests.zip/seed，可再考虑后端新增专用接口（见任务清单）。

### 影响范围
```yaml
涉及模块:
  - frontend（Next.js）: 新增 `/assistant` 路由、迁移 UI 组件、对接 jobs/models/auth/SSE
  - backend（FastAPI）: 原则上不改；如需要增强“继续对话/重试/从 testcases 生成 tests”再新增小接口
预计变更文件: 10-25（主要集中在 frontend/src 下）
```

### 风险评估
| 风险 | 等级 | 应对 |
|------|------|------|
| 新 UI 是“聊天式”，而后端 Job 是“非交互一次性执行”，语义不一致 | 中 | MVP 先跑通单次 Job；后续把“发送消息”映射为“新 Job（seed + repair 指令）”并串联历史 |
| tests 目前以 `tests.zip` 输入为主，新 UI 是结构化 testCases | 中 | 方案 A：前端 JSZip 生成 in/out pairs zip；方案 B：后端新增 `from_testcases` 转换接口 |
| SSE 断线/重复消费导致终端显示错乱 | 中 | 复用现有 offset 续传策略（localStorage offset + reconnect） |
| UI 样式依赖 AI Studio `index.html` 的 tailwind CDN 与自定义 CSS | 低 | 将必要 CSS 迁移到 Next.js `globals.css`，确保不依赖外部 CDN |

---

## 3. 技术设计（可选）

> 涉及架构变更、API设计、数据模型变更时填写

### 架构设计
```mermaid
flowchart TD
    U[Browser: /assistant (Next.js)] -->|REST| B[FastAPI /api]
    U -->|SSE terminal/agent_status| B
    B --> D[(SQLite: data/realmoi.db)]
    B --> J[jobs/{job_id}/... 文件树]
    B -->|Docker API| R[runner containers]
    R -->|write logs/artifacts| J
```

### API设计
#### POST /api/auth/login
- **请求**: `{ username, password }`
- **响应**: `{ access_token, user }`

#### GET /api/models
- **请求**: (无)
- **响应**: `[{ model, ...pricing }]`

#### POST /api/jobs
- **请求**: `multipart/form-data`
  - `model`: string
  - `statement_md`: string
  - `current_code_cpp`: string（可空）
  - `tests_zip`: file（可选）
  - `tests_format`: "auto" | "in_out_pairs" | "manifest"（可选）
  - `compare_mode`: "tokens" | "trim_ws" | "exact"（可选）
  - `search_mode`: "disabled" | "cached" | "live"
  - `time_limit_ms` / `memory_limit_mb`
- **响应**: `{ job_id, status, created_at }`

#### POST /api/jobs/{job_id}/start
- **请求**: (无)
- **响应**: `{ job_id, status }`

#### GET /api/jobs/{job_id}/terminal.sse?offset={n}
- **事件**: `terminal`，data: `{ offset, chunk_b64 }`

#### GET /api/jobs/{job_id}/agent_status.sse?offset={n}
- **事件**: `agent_status`，data: `{ offset, item }`

### 数据模型
本次迁移不新增后端数据模型；前端侧新增的“会话/历史”继续保存在 localStorage（与现有 token 存储策略一致）。

---

## 4. 核心场景

> 执行完成后同步到对应模块文档

### 场景: 在新 UI 中发起一次调题 Job
**模块**: frontend
**条件**: 用户已登录；至少填写题面；已选择模型
**行为**: Portal 提交 → 创建 Job → start → Cockpit 订阅 SSE → 完成后拉取 artifacts
**结果**: 用户可在同一 UI 中看到终端与状态时间线，并查看最终思路、代码与测试摘要

---

## 5. 技术决策

> 本方案涉及的技术决策，归档后成为决策的唯一完整记录

### assistant-ui-migration#D001: 迁移落地形态（新 UI 挂载位置）
**日期**: 2026-02-02
**状态**: ✅采纳
**背景**: 新 UI 目前是 Vite 单页应用且包含浏览器直连 LLM 逻辑；项目现有前端为 Next.js，并已实现鉴权、SSE、jobs 管理与管理员面板。需要选择落地方式以最小成本复用现有能力并避免双前端分裂。
**选项分析**:
| 选项 | 优点 | 缺点 |
|------|------|------|
| A: 保持 Vite 独立前端（`realm-oi---...` 单独跑） | 迁移 UI 组件最少；保留 AI Studio 结构 | 需要额外的鉴权/SSE/部署/CORS 处理；重复维护 API 封装；与现有 Next 前端割裂 |
| B: 迁移 UI 组件进入现有 Next.js（新增 `/assistant`） | 复用 token 管理、`apiFetch`、`connectSse`、现有页面与部署；统一 Tailwind 与构建链 | 需要把组件路径/资源/少量样式做适配（一次性成本） |
**决策**: 选择方案 B
**理由**: 本项目“原有逻辑”主要沉淀在现有 Next.js 的鉴权与 SSE 可靠性实现中，迁入后可最大化复用，且便于与 `/admin` 等页面共存。
**影响**: frontend（Next.js）新增路由与组件迁移；`realm-oi---...` 目录可作为设计参考，后续决定是否保留/归档

### assistant-ui-migration#D002: tests 结构化输入的承载方式
**日期**: 2026-02-02
**状态**: ⏸搁置
**背景**: 新 UI 以 `testCases: [{input, output}]` 收集测试；后端当前以 `tests_zip` 为主，runner 支持 `in_out_pairs`/`manifest`。
**选项分析**:
| 选项 | 优点 | 缺点 |
|------|------|------|
| A: 前端用 JSZip 生成 `tests_zip`（in/out 文件对） | 不改后端；与现有协议完全一致 | 需要引入 JSZip 与 zip 生成逻辑；浏览器端大文件可能慢 |
| B: 后端新增 `from_testcases` 接口（JSON -> zip/目录） | 前端最简单；可统一校验与限制 | 需要新增后端 API 与测试；需考虑配额/安全 |
**决策**: MVP 先做 A；若遇到复杂用例/性能问题再切到 B
**理由**: 先保证最小改动跑通闭环
**影响**: frontend 增加 zip 生成；backend 暂不变更
