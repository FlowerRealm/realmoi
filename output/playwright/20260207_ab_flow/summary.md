# Playwright A+B 流程复现（2026-02-07）

## 测试目标
验证「提交 A+B 题目后的端到端流程」是否可用。

## 环境
- 前端: http://localhost:3000
- 后端: http://localhost:8000/api
- 自动化: `npx --yes --package @playwright/cli playwright-cli -s=abflow ...`

## 复现步骤（用户视角）
1. 打开 `/signup`，注册新用户 `abflow_0817`。
2. 登录后进入 `/`。
3. 在 New Job 输入 A+B 题面，点击「开始调试」。

## 结果（首次）
- 页面确实跳转到 `/jobs/{jobId}`（URL 变更正常）。
- 但一次点击触发了两个 job：
  - `0cc9e7ebc5544c57a000c8e63eec0205`
  - `2be3532d313e42f6a3acf0df116f536b`
- 两个 job 都最终 `failed`。

证据:
- `network_before_fix.log`
- `after_submit_snapshot.yml`
- `first_run_failed_snapshot.yml`

## 已修复项
- 在 `frontend/src/components/assistant/Cockpit.tsx` 增加 `initialRunStartedRef` 防重入。
- 修复后再次从 `/` 提交 A+B：只创建 1 个 job（`eea01227120d4596bd017885e31fabc7`）。

证据:
- `network_after_fix.log`（只看到 1 次 `/api/jobs` + 1 次 `/start`）
- `after_fix_second_submit_snapshot.yml`

## 当前剩余问题（后端/模型配置）
- job 仍然会失败，容器日志显示：
  - `http 400 Bad Request: 模型未启用`
  - `[generate] failed: codex_exit_1`
- 对应 job：`eea01227120d4596bd017885e31fabc7`

证据:
- `generate_container_eea012.log`
- `second_run_failed_snapshot.yml`
- `failure_viewport.png`
