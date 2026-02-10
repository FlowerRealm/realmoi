# 变更提案: full-ui-redesign-cockpit-style

## 元信息
```yaml
类型: 规划
方案类型: implementation
优先级: P0
状态: 已完成
创建: 2026-02-05
```

---

## 1. 需求定义

### 背景
当前项目已形成一套高完成度的核心视觉样式（主页 `Portal` 的 New Job 录入体验 + `Cockpit` 的 Job Detailed 运行体验），但其余页面（登录/注册、账单、设置、Admin）仍偏传统表单/表格风格，导致全站视觉语言和交互密度不一致。

### 用户目标（本次）
- 对项目进行“完整 UI 重新设计”规划。
- 全站样式对齐当前 `new job` 与 `job detailed` 的风格基线（以 `Portal/Cockpit` 为 SSOT）。
- 先完成可执行规划，再进入逐页实施。

### 范围（全站页面）
- 核心助手：`/`（Portal + Cockpit）
- 认证：`/login`、`/signup`
- 用户功能：`/billing`、`/settings/codex`
- Admin：`/admin/users`、`/admin/pricing`、`/admin/upstream-models`、`/admin/billing`
- 公共框架：`AppHeader`、`Form`、`AuthCard`、全局样式 `globals.css`

### 非目标（本方案不做）
- 不修改后端 API、鉴权语义、SSE 协议、任务执行链路。
- 不引入新的 UI 组件库。

---

## 2. 设计基线与原则

### 样式基线（SSOT）
- New Job 参考：`frontend/src/components/assistant/Portal.tsx` + `LiquidInput.tsx`
- Job Detailed 参考：`frontend/src/components/assistant/Cockpit.tsx`
- 玻璃容器基元：`frontend/src/components/assistant/GlassPanel.tsx`
- 背景氛围基元：`frontend/src/components/assistant/FluidBackground.tsx`

### 统一原则
- 视觉统一：颜色、圆角、阴影、边框透明度、排版密度统一。
- 交互统一：按钮/输入/表格/提示信息保持一致状态反馈（hover/active/disabled/error）。
- 可读优先：高信息密度区域（xterm、JSON、表格）在玻璃风格下确保对比度。
- 渐进重构：先抽象通用样式基元，再逐页替换，避免一次性大爆炸改动。

### 信息架构规划图（FigJam）
- 已生成规划图（可编辑）：<https://www.figma.com/online-whiteboard/create-diagram/aa8b7dea-684f-430e-9f82-ea09920a6af2?utm_source=other&utm_content=edit_in_figjam&oai_id=&request_id=619ee365-405b-4dd4-8bf5-31a013c09807>

---

## 3. 实施策略

### 3.1 设计系统层（Foundation）
1. 在 `globals.css` 建立全站 token（背景、文本、边框、玻璃面、强调色、状态色）。
2. 抽象通用 primitives：
   - `GlassSurface`（替代散落的玻璃 class）
   - `PageSection` / `MetricCard` / `DataTableShell`
   - `PrimaryButton` / `SecondaryButton` / `DangerButton`
   - `Field`（Input/Textarea/Select 的统一壳层）
3. `AppHeader` 重构为统一导航壳，保持权限控制逻辑不变。

### 3.2 页面层（Routes）
1. 认证页（`/login`、`/signup`）对齐 Portal 风格：背景层 + 玻璃卡片 + 统一输入反馈。
2. 用户页（`/billing`、`/settings/codex`）从“工具表单”升级为“信息面板 + 操作区”布局。
3. Admin 页（Users/Pricing/Upstream/Billing）统一为：
   - 顶部操作条
   - 过滤区卡片
   - 结果区玻璃表格/代码块
   - 错误与成功提示风格统一。
4. 首页 `/` 仅做一致性加固，不破坏现有 Portal/Cockpit 成熟交互。

### 3.3 验证层（Validation）
1. 路由覆盖：所有页面可访问、导航正确、权限可见性正确。
2. 核心交互：创建 Job、SSE 终端、状态流、产物读取不回归。
3. 工程质量：`npm -C frontend run lint` 与 `npm -C frontend run build` 通过。
4. 视觉验收：对照基线页面进行间距/对比/层级检查。

---

## 4. 风险与决策

### 风险 R1：玻璃效果过重导致性能下降
- 对策：限制大面积 blur 层级，优先复用单层背景与局部高亮。

### 风险 R2：高密度数据区可读性下降
- 对策：表格与代码区采用“低透明 + 高对比”子主题，不强行与表单区域同透明度。

### 风险 R3：导航与真实路由不一致
- 对策：在实施前先做导航审计，确认 `/jobs` 是否恢复独立路由或映射到 `/`。

### 风险 R4：Figma 设计上下文未绑定节点
- 对策：进入实现阶段前，用户提供目标 Figma Frame/Node 链接，按 Figma MCP 标准流执行 `get_design_context` + `get_screenshot` 做 1:1 对齐。

---

## 5. 验收标准

- [ ] 全站页面视觉风格与 `new job` / `job detailed` 基线一致。
- [ ] 保持现有业务能力不变（鉴权、SSE、Artifacts、Admin 操作）。
- [ ] 全局组件复用率提升，减少页面级重复样式。
- [ ] 构建与静态检查通过，且无阻断性回归。

---

## 6. 本阶段交付物

- `helloagents/plan/202602060616_full-ui-redesign-cockpit-style/proposal.md`
- `helloagents/plan/202602060616_full-ui-redesign-cockpit-style/tasks.md`
- FigJam 规划图（见上方链接）
