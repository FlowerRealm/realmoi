# 任务清单：前端样式对齐 new-api（内容区作用域）

- [√] 拉取并定位 new-api 前端目录（`web/`）
- [√] 梳理 new-api 样式体系（Semi UI + `src/index.css`）
- [√] 引入 Semi UI 依赖到 `frontend/package.json`
- [√] 保持原导航栏不变（`AppHeader.tsx` 不改），恢复/保留 Liquid Glass 全局基线（`body`/`.realm-bg`/全局 `glass-*`）
- [√] 在 `frontend/src/app/globals.css` 中：
  - [√] 以相对路径导入 Semi CSS（规避 Next exports 限制）
  - [√] 新增 `.newapi-scope`（内容区作用域映射：`glass-*` → Semi tokens）
  - [√] 引入 `blur-ball`（用于登录/注册页背景对齐）
- [√] 页面接入（全量页面内部）：
  - [√] `AssistantApp` 内部包裹 `.newapi-scope`
  - [√] `/billing`、`/settings/codex`、`/admin/*` 的 `<main>` 增加 `newapi-scope`
  - [√] `/login`、`/signup` 按 new-api 登录/注册布局重构（Semi `Card/Form` + blur balls）
- [-]（已回滚）全站壳层方案：`AppShell` + `(app)/(auth)` 路由分组
- [√] Playwright 对比验证：双项目启动 + 截图 + diff + `metrics.json`
- [√] 验收：
  - [√] `npm -C frontend run lint`
  - [√] `npm -C frontend run build`
