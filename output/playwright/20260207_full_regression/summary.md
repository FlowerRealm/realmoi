# Full Regression 回归记录（Playwright）

日期：2026-02-07

## 执行范围
- 登录（已有用户）
- New Job（A+B）创建与自动跳转
- Cockpit 运行态 + 失败态展示
- Runs 切换 URL 同步
- 返回大厅 URL 恢复
- 历史会话恢复 URL 同步
- `/jobs/{jobId}` 直达详情

## 发现并修复的问题

### 1) 历史会话恢复后 URL 停留在 `/`
- 现象：点击 RECENT SESSIONS 进入 Cockpit，但地址栏不变。
- 影响：刷新后无法保持当前 Job 上下文。
- 修复：`Cockpit` 增加 `activeJobId` -> URL 同步 effect。
- 证据：`resume_history_url_synced.yml`（恢复后 URL 为 `/jobs/{jobId}`）

### 2) `/jobs/[jobId]` 直达页读取 params 方式不兼容 Next 16
- 现象：动态路由把 `params` 当同步对象读取，导致直达页退回 Portal。
- 修复：改为 `async` 页面并 `await params`。
- 证据：`direct_job_readonly.yml`（直达页展示 Cockpit 且输入框只读）

### 3) 非 admin 用户进入助手首页会触发 `/api/admin/upstream/channels` 403
- 现象：Portal 先打 admin 接口再 fallback，普通用户持续出现 403 噪音。
- 修复：仅 admin 角色尝试 admin upstream 接口，普通用户直接走 `/api/models`。
- 证据：`console_clean.log`（仅保留登录前 `/auth/me` 401，不再有 admin 403）

### 4) Job 失败时前端仍请求 artifacts，产生 404 噪音且提示不明确
- 现象：失败后仍请求 `solution/main/report`，浏览器出现 404；消息只显示“未获取到 solution.json”。
- 修复：仅 `status=succeeded` 时拉取 artifacts；失败态直接展示 `state.error` 原因。
- 证据：
  - `network_no_artifact_404.log`（无 artifacts 404）
  - `failure_reason_message.yml`（显示“失败原因：failed: generate_failed”）

## 回归结果
- 创建 Job：单次点击仅创建 1 个 Job（`network_single_create.log`）
- URL 同步：
  - 创建后 `/jobs/{jobId}`
  - Runs 切换同步对应 Job
  - 返回大厅恢复 `/`
  - 历史恢复同步 `/jobs/{jobId}`
- 直达详情：`/jobs/{jobId}` 可正常加载 Cockpit（只读模式）

## 当前剩余问题（非前端逻辑）
- Job 仍会在生成阶段失败：上游返回“模型未启用”，最终 `generate_failed`。
- 该问题来自后端/模型配置，不是前端路由和交互流程故障。
