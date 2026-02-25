# 任务清单: fix-make-dev

> **@status:** completed | 2026-02-24 18:37

目录: `helloagents/plan/202602241830_fix-make-dev/`

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
总任务: 3
已完成: 3
完成率: 100%
```

---

## 任务列表

### 1. Makefile/dev

- [√] 1.1 在 `Makefile` 中为 `make dev` 增加端口可用性预检查与后端就绪等待
  - 验证: `make dev` 在端口被占用时快速退出并提示；端口可用时不再出现“后端未起前端仍启动”的半启动行为

- [√] 1.2 在 `Makefile` 中启动 judge 时导出 `REALMOI_JUDGE_API_BASE_URL=http://127.0.0.1:${BACKEND_PORT}`
  - 依赖: 1.1
  - 验证: `BACKEND_PORT` 覆盖后，judge 仍能连到后端（不再固定 fallback 8000）

### 2. backend/judge

- [√] 2.1 修复 `backend/app/services/judge_mcp_client.py`：连接阶段捕获握手异常等“非预期异常”，避免 judge 守护进程崩溃
  - 验证: `python -m pytest -q backend/tests/test_judge_mcp_client.py`

---

## 执行备注

> 执行过程中的重要记录

| 任务 | 状态 | 备注 |
|------|------|------|
| 1.1 | completed | 端口占用时提示并快速退出；uvicorn 启动后等待端口监听，失败会触发 trap 清理 |
| 1.2 | completed | `make dev BACKEND_PORT=8001` 时 judge 连接 URL 跟随端口（`ws://127.0.0.1:8001/...`） |
| 2.1 | completed | 新增回归测试：`backend/tests/test_judge_mcp_client.py`（1 passed） |
