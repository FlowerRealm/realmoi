# 任务清单: liquid-glass-frontend-redesign

目录: `helloagents/plan/202602031250_liquid-glass-frontend-redesign/`

> 说明：按用户要求“先设计、暂不改代码”，本方案包当前仅完成 Pencil 设计稿与文档同步；所有前端代码重构相关任务已撤回并标记为 `skipped`。

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
已完成: 2
完成率: 15%
```

---

## 任务列表

### 1. 设计与样式基建（frontend）

- [-] 1.1 在 `frontend/src/app/globals.css` 中建立 Liquid Glass 设计 tokens（背景/玻璃面/按钮/输入/表格/滚动条），并提供降级策略
  - 原因: 按用户要求，暂不改代码
 
- [-] 1.2 在 `frontend/src/components/AppHeader.tsx` 中重做导航栏（主导航 + Admin 分组 + 用户菜单/退出）
  - 依赖: 1.1
  - 原因: 按用户要求，暂不改代码
 
- [-] 1.3 在 `frontend/src/components/Form.tsx`、`frontend/src/components/AuthCard.tsx` 中统一表单与认证页的 Liquid Glass 视觉
  - 依赖: 1.1
  - 原因: 按用户要求，暂不改代码

### 2. 页面逐页改造（frontend/src/app）

- [-] 2.1 改造主页 `/`（调题助手 Portal/Cockpit）：与全站背景/导航统一，并保证交互不回归
  - 原因: 按用户要求，暂不改代码
 
- [-] 2.2 改造主页 `/` 的会话列表（Recent Sessions）：列表/状态/动作统一为玻璃风格
  - 原因: 按用户要求，暂不改代码
 
- [-] 2.3 改造主页 `/` 的 Cockpit 状态：Tabs、终端面板、状态流与产物区统一；终端采用深色玻璃容器
  - 原因: 按用户要求，暂不改代码
 
- [-] 2.4 改造 `/billing` 账单页：卡片与统计块统一
  - 原因: 按用户要求，暂不改代码
 
- [-] 2.5 改造 `/settings/codex`：双栏编辑/预览布局统一，编辑区/只读区样式优化
  - 原因: 按用户要求，暂不改代码
 
- [-] 2.6 改造 Admin 页面：`/admin/users`、`/admin/pricing`、`/admin/upstream-models`、`/admin/billing`
  - 原因: 按用户要求，暂不改代码

### 3. 设计稿与验收（designs + KB）

- [√] 3.1 使用 Pencil 更新 `designs/realmoi_ui.pen`：为每个路由页面创建设计稿 Frame（逐页完成）
  - 验证: pen 文件包含上述页面对应 Frame，且具备统一 Liquid Glass 风格

- [-] 3.2 运行前端验收：`npm -C frontend run build`、`npm -C frontend run lint`
  - 原因: 本阶段不改前端代码，不做实现验收

- [√] 3.3 同步知识库与变更记录：更新 `helloagents/modules/frontend.md` 与 `helloagents/CHANGELOG.md`
  - 验证: 文档与当前代码一致；CHANGELOG 仅记录设计稿变更与方案链接

- [-] 3.4 迁移方案包至 `helloagents/archive/`（migrate_package.py）
  - 原因: 当前为“设计先行”阶段，方案包保留在 `plan/` 便于后续按设计落地实现

---

## 执行备注

> 执行过程中的重要记录

| 任务 | 状态 | 备注 |
|------|------|------|
