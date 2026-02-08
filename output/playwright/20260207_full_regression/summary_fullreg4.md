# Full Regression (Playwright) - fullreg4

日期: 2026-02-07
会话: `PLAYWRIGHT_CLI_SESSION=fullreg4`
账号: `abflow_0817`

## 1) 首轮回归（修复前）

- 登录后参数页模型下拉可见实时模型：`[Realms] gpt-5.2`, `gpt-5.2-codex`, `gpt-5.3-codex`
- 选择 `gpt-5.2-codex` 提交 A+B 后：URL 正确跳转到 `/jobs/{jobId}`
- 仅发起 1 次 `POST /api/jobs`（无重复创建）
- 失败态展示：`Job 已结束（status=failed）。失败原因：failed: generate_failed`

证据文件:
- `fullreg4_models_live_dropdown.yml`
- `fullreg4_redirect_after_submit.yml`
- `fullreg4_failure_reason_generate_failed.yml`
- `fullreg4_failure_network.log`
- `fullreg4_failure_console.log`

### 根因（不是“模型未启用”）

失败 job: `9801bd9947364d4e8604374a56b0680b`
容器: `87af15af5b8d66de53ac9e5f0bf9f4dfb05d7f7dc4dce09fb8894842e051572b`

从容器日志确认失败原因为：
- `invalid_json_schema`
- `Invalid schema for response_format 'codex_output_schema'`
- `Missing 'assumptions'`

证据文件:
- `fullreg4_generate_container_schema_error.log`

## 2) 修复后回归

修复内容:
- `runner/schemas/codex_output_schema.json`
- 将 `assumptions` 与 `complexity` 加入 `required`，满足上游 JSON Schema 规则（required 覆盖 properties 全键）

重建镜像:
- `docker build -t realmoi-runner:dev runner`

再次提交 A+B（同会话）:
- 新 job: `8a2e7411ba244c7ea13bc06be7fb9e6c`
- 状态流转：`running_generate -> running_test -> succeeded`
- URL 跳转正常，结果面板显示成功产物
- 网络仅 1 次 `POST /api/jobs`
- 成功后产物请求均 200：`solution.json / main.cpp / report.json`

证据文件:
- `fullreg4_success_after_schema_fix.yml`
- `fullreg4_success_network.log`
- `fullreg4_success_console.log`
- `fullreg4_success_viewport.png`

## 3) 额外回归点

- 历史会话恢复后 URL 同步到 `/jobs/{jobId}`：
  - `fullreg4_resume_history_url_synced.yml`
- 直接访问 `/jobs/{jobId}` 为只读追踪态（输入框禁用）：
  - `fullreg4_direct_job_readonly.yml`

## 4) 创建前模型校验验证（API）

通过 API 直接提交不存在模型（带 upstream channel）：
- 返回 `422 invalid_model`
- message: `Model not enabled on upstream channel`

结论：
- “模型未启用”路径已被创建前校验阻断。
- 本次真实失败根因已切换并修复为 schema 不合法问题；修复后 A+B 流程可成功跑通。
