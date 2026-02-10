# 任务清单: assistant-homepage

> **@status:** completed | 2026-02-02 12:33

目录: `helloagents/archive/2026-02/202602021229_assistant-homepage/`

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
总任务: 7
已完成: 7
完成率: 100%
```

---

## 任务列表

### 1. 路由重构（frontend）

- [√] 1.1 将新调题助手 UI 挂载到主页：更新 `frontend/src/app/page.tsx` 渲染 `AssistantApp`
  - 验证: 访问 `/` 进入 Portal（未登录会跳转到 `/login`）

- [√] 1.2 移除 `/assistant` 路由入口（删除 `frontend/src/app/assistant/page.tsx`）
  - 依赖: 1.1
  - 验证: `npm run build` 路由列表不再包含 `/assistant`

- [√] 1.3 删除旧前端路由：移除 `frontend/src/app/jobs/*`、`frontend/src/app/admin/*`、`frontend/src/app/billing/*`、`frontend/src/app/settings/*`
  - 验证: `npm run build` 路由列表不再包含 `/jobs`、`/admin`、`/billing`、`/settings/*`

- [√] 1.4 去掉 Shell：更新 `frontend/src/app/layout.tsx` 不再使用 `Shell`，并删除 `frontend/src/components/Shell.tsx`
  - 依赖: 1.3
  - 验证: 主页 UI 全屏渲染，无顶部导航条

- [√] 1.5 更新登录/注册跳转：`frontend/src/app/login/page.tsx`、`frontend/src/app/signup/page.tsx` 登录成功后跳转到 `/`
  - 验证: 登录后进入主页 UI

### 2. 验证与文档同步

- [√] 2.1 验证前端构建：`cd frontend && npm run build`
  - 验证: 构建通过

- [√] 2.2 知识库与 README 同步：更新 `helloagents/modules/frontend.md`、`helloagents/context.md`、`README.md`；并追加 `helloagents/CHANGELOG.md` 记录
  - 验证: 文档与代码一致，且不包含已移除路由
---

## 执行备注

> 执行过程中的重要记录

| 任务 | 状态 | 备注 |
|------|------|------|
