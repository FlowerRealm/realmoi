# 方案提案：前端样式对齐 new-api（内容区作用域）

## 背景与目标

用户希望将本项目（`realmoi`）的前端**内容与样式**对齐 `QuantumNous/new-api`，并要求“逐细节对齐”。同时存在硬约束：**原来的导航栏（`AppHeader`）不要变**，只调整页面内部样式，并用 Playwright 做截图对比验证。

因此本提案将“对齐”拆分为两层：

1. **全局层（不变）**：保留原 Liquid Glass 全局基线（`body`/`.realm-bg`/全局 `glass-*`）+ 现有 `AppHeader` 视觉与交互。
2. **内容区（对齐）**：引入 Semi UI，并通过 `.newapi-scope` 作用域把 `glass-*` 视觉映射为 Semi tokens，使页面内部呈现 new-api 风格，同时避免影响导航栏。

## 参考基线（new-api）

- 仓库：`https://github.com/QuantumNous/new-api`
- 前端目录：`web/`
- 关键技术栈：Vite + React + `@douyinfe/semi-ui`（Semi Design）+ Tailwind
- 样式关键点：
  - `src/index.css`：`body` 字体栈（Lato）、`bg-gray-100` 登录背景、`blur-ball` 模糊球、以及大量 Semi 组件微调
  - 登录/注册页：Semi `Card/Form` + prefix icons + 圆角按钮风格

## 实施策略（本项目）

- 保持 Next.js 架构不动，仅在样式层与页面内部布局做对齐。
- `frontend/src/app/globals.css`：
  - 以相对路径导入 Semi CSS（规避 package exports 限制）
  - 保留原 Liquid Glass 全局样式
  - 新增 `.newapi-scope`（内容区作用域映射：`glass-*` → Semi tokens）
  - 引入 `blur-ball` 样式用于 `/login`、`/signup`
- 页面接入：
  - `/billing`、`/settings/codex`、`/admin/*`：`<main>` 增加 `newapi-scope`
  - `/`、`/jobs/[jobId]`：`AssistantApp` 内部包裹 `newapi-scope`（外层继续 `FluidBackground` + 顶栏避让）
  - `/login`、`/signup`：按 new-api 登录/注册页面布局重构（灰底 + blur balls + Semi `Card/Form`）
- 验收与验证：
  - `npm -C frontend run lint` + `npm -C frontend run build`
  - Playwright 双项目截图对比（输出到 `output/playwright/20260211_align-new-api/`，含 diff 与 `metrics.json`）

## 风险与规避

- **Semi CSS 引入的 exports 限制**：使用 `globals.css` 相对路径导入 node_modules 文件规避。
- **导航栏样式被污染风险**：通过 `.newapi-scope` 做作用域隔离，避免全局覆盖 `body` 字体/背景与 `glass-*` 基线。
