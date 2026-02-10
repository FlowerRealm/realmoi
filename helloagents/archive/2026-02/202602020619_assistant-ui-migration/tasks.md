# 任务清单: assistant-ui-migration

> **@status:** completed | 2026-02-02 06:39

目录: `helloagents/archive/2026-02/202602020619_assistant-ui-migration/`

---

## 任务状态符号说明

| 符号 | 状态 | 说明 |
|------|------|------|
| `[ ]` | pending | 待执行 |
| `[√]` | completed | 已完成 |
| `[X]` | failed | 执行失败 |
| `[-]` | skipped | 已跳过 |
| `[?]` | uncertain | 待确认 |

---

## 执行状态
```yaml
总任务: 13
已完成: 12
完成率: 92%
```

---

## 任务列表

### 1. UI 迁移（frontend）

- [√] 1.1 在 `frontend/src/app/assistant/page.tsx` 新增入口页面（RequireAuth + AssistantApp）
  - 验证: 登录后访问 `/assistant` 可进入 Portal

- [√] 1.2 将 `realm-oi---competitive-programming-assistant/` 的 UI 组件迁移到 `frontend/src/components/assistant/*`（Portal/Cockpit/通用组件/类型）
  - 验证: `frontend` TypeScript 编译通过，页面可正常渲染

- [√] 1.3 将 AI Studio `index.html` 中的必要全局样式迁移到 Next.js（`frontend/src/app/globals.css` 或新增 CSS），确保不依赖 tailwind CDN
  - 依赖: 1.2
  - 验证: `/assistant` 页面无外部 tailwind CDN 依赖，UI 样式与交互正常

### 2. 原有逻辑对接（jobs/models/auth + SSE）

- [√] 2.1 在新 UI 的 Portal 中接入模型列表：调用 `GET /api/models` 并提供 model 选择
  - 验证: Portal 可展示并选择模型；管理员未启用模型时有明确提示

- [√] 2.2 将“开始会话”映射为创建并启动 Job：`POST /api/jobs`（FormData）→ `POST /api/jobs/{job_id}/start`
  - 验证: 创建后进入 Cockpit，`GET /api/jobs/{job_id}` 状态进入 running_*

- [√] 2.3 适配 tests 输入：实现 testCases -> `tests_zip`（in/out pairs）的生成逻辑（JSZip），并设置 `tests_format=in_out_pairs`
  - 验证: 后端 state.json 中 `tests.present=true`；runner 能加载到 case 列表并产生 report.json

- [√] 2.4 在 Cockpit 中接入 SSE：复用 `frontend/src/lib/sse.ts` 订阅 `terminal.sse` 与 `agent_status.sse`，支持 offset 断线续传
  - 验证: 运行中可实时看到终端刷屏与状态时间线；断网重连后不丢失且不重复刷屏

- [√] 2.5 Job 完成后拉取 artifacts，并映射为 UI 状态：`solution.json`/`main.cpp`/`report.json`
  - 验证: UI 可展示解法思路、最终代码、测试摘要与首个失败信息（如有）

### 3. 会话与迭代（继续对话/修复语义）

- [√] 3.1 设计并实现“继续对话”的 MVP：用户发送消息 → 创建新 Job（seed 使用上一次 main.cpp + 追加指令），history 串联 job 链
  - 验证: 在同一会话内连续触发 2 个 job，UI 可切换查看每次产物与日志

- [-] 3.2 如前端侧 zip/seed 构造遇到阻碍，评估并实现后端增强接口（例如 `POST /api/jobs/from_testcases` 或 `POST /api/jobs/{job_id}/retry`）
  - 依赖: 3.1
  - 验证: 新接口有最小化测试覆盖，且不影响旧前端 `/jobs/new`
  > 备注: 已在前端实现 JSZip 打包与 seed/追加指令逻辑，当前无需新增后端接口

### 4. 回归与知识库同步

- [√] 4.1 回归测试：后端 `pytest` 通过；手动验证 `/assistant` 端到端闭环
  - 验证: `make test` 通过；`make dev` 下可完成一次真实 job（或 mock_mode）

- [√] 4.2 知识库同步：更新 `helloagents/modules/frontend.md`（新增 `/assistant`，说明迁移策略）；必要时新增模块文档（assistant UI）
  - 验证: 文档中的路径/接口与代码一致

- [√] 4.3 更新开发入口（可选）：在 `Makefile`/`README.md` 补充 `/assistant` 新入口说明（保留原 `/jobs`）
  - 验证: 新同事按 README 可在本地跑通并找到入口

---

## 执行备注

> 执行过程中的重要记录

| 任务 | 状态 | 备注 |
|------|------|------|
