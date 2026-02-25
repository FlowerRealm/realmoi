# 任务清单: fix-make-dev-start-judge

> **@status:** completed | 2026-02-24 19:01

目录: `helloagents/plan/202602241900_fix-make-dev-start-judge/`

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
总任务: 2
已完成: 2
完成率: 100%
```

---

## 任务列表

### 1. Makefile/dev

- [√] 1.1 在 `Makefile` 中实现“端口不可 bind 但可连接则复用监听”，并确保 judge 仍会自动启动（或检测到已运行）
  - 验证: `timeout 12 make dev`（backend:8000 已有监听时仍可启动 frontend，并输出 judge 状态）

- [√] 1.2 更新文档：`README.md`、`helloagents/modules/backend.md` 同步说明端口占用时的复用行为与排障路径
  - 依赖: 1.1

---

## 执行备注

> 执行过程中的重要记录

| 任务 | 状态 | 备注 |
|------|------|------|
| 1.1 | completed | 端口被占用但已有监听时不再阻断；judge 启动增加“已运行检测”，`wait` 仅等待本次启动的进程 |
| 1.2 | completed | 文档已同步更新 |
