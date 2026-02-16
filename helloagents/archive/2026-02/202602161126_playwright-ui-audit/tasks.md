# 任务清单: playwright-ui-audit

> **@status:** completed | 2026-02-16 11:55

目录: `helloagents/plan/{YYYYMMDDHHMM}_playwright-ui-audit/`

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
总任务: 14
已完成: 11
完成率: 79%
```

---

## 任务列表

### 1. Playwright UI 巡检基建（frontend）

- [√] 1.1 增加 Playwright 依赖与脚本
  - 位置: `frontend/package.json`
  - 内容: 添加 `@playwright/test`；新增 `pw:install`、`pw:ui-audit` 等 scripts
  - 验证: `npm -C frontend run pw:ui-audit -- --help` 可运行

- [√] 1.2 新增 Playwright 配置（仅 Chromium + 多视口）
  - 位置: `frontend/playwright.config.ts`
  - 内容: projects=代表性视口集合；workers=1；输出目录由 `REALMOI_PW_OUT_DIR` 控制
  - 验证: `npx -C frontend playwright test --list` 可列出用例/项目

- [√] 1.3 实现 globalSetup：登录并保存 storageState
  - 位置: `frontend/pw/global-setup.ts`
  - 内容: 默认使用 dev 自举 admin（可 env 覆盖）；登录成功后保存到 `.pw/auth.json`
  - 验证: 跑任意需要鉴权的页面不再被重定向到 `/login`

- [√] 1.4 路由发现：自动枚举所有 `page.tsx` 对应的路由
  - 位置: `frontend/pw/routes.ts`（或同等实现）
  - 内容: 扫描 `frontend/src/app/**/page.tsx`，转换为 URL path；忽略 route group 段 `(xxx)`
  - 验证: 路由列表覆盖当前已知页面（含 `/admin/*`、`/settings/codex`）

- [√] 1.5 截图执行器：逐路由 × 逐视口截图（viewport + fullPage）
  - 位置: `frontend/pw/ui-audit.spec.ts`
  - 内容: 访问页面→等待稳定→截图→写入结果记录
  - 验证: 输出目录存在并包含截图文件

- [√] 1.6 指标采集：自动检测水平溢出并给出 Top offenders
  - 位置: `frontend/pw/audit-metrics.ts`（或同等实现）
  - 内容: 记录 `clientWidth/scrollWidth`、水平溢出布尔值、offender 元素摘要
  - 验证: 报告中能看到每页的 metrics

- [√] 1.7 报告生成：聚合生成 `report.jsonl` 与 `report.md`
  - 位置: `frontend/pw/report.ts`（或同等实现）
  - 内容: 逐页写入 JSONL；结束时渲染 Markdown（页面索引 + 问题清单 + 截图路径）
  - 验证: `report.md` 非空且可直接定位截图

- [√] 1.8 动态路由支持：/jobs/[jobId] 自动解析或可配置
  - 位置: `frontend/pw/routes.ts` / `frontend/pw/ui-audit.spec.ts`
  - 内容: 优先读取 `REALMOI_PW_JOB_ID`；否则尝试从 `/api/jobs` 取最新 job_id；失败则标记 skipped
  - 验证: 有 job 时可截图 `/jobs/<id>`；无 job 时报告明确提示如何补齐

### 2. 一键运行脚本（scripts）

- [√] 2.1 新增 `scripts/pw_ui_audit.sh`：启动服务 + 跑巡检 + 收集日志
  - 内容: 启动 backend/frontend（端口可配置）→等待就绪→执行 Playwright→输出 `dev_*.log`
  - 验证: 仅运行该脚本即可得到报告与截图

### 3. 验证与交付（开发实施阶段）

- [√] 3.1 运行前端质量门禁
  - 命令: `npm -C frontend run lint`、`npm -C frontend run build`
  - 验证: 通过

- [√] 3.2 生成首份基线报告（B 流程的第一步）
  - 命令: `scripts/pw_ui_audit.sh`
  - 验证: 产出 `report.md` + 截图目录，并将“问题清单”回传给你确认后再进入修复
  - 产出: `output/playwright/ui-audit/20260216_115233/report.md`

### 4. 修复与回归（需你确认后执行）

- [?] 4.1 基于 `report.md` 拆分 Top 问题页面的修复任务（每项绑定页面/组件/原因）
  - 验证: 形成可执行修复清单

- [?] 4.2 逐项修复 UI 对齐/裁切/布局错位问题
  - 验证: 修复项在截图对比中消失

- [?] 4.3 回归复测：重新运行 UI 巡检并对比前后截图
  - 验证: 关键页面在各视口下布局稳定、无明显溢出与裁切

---

## 执行备注

> 执行过程中的重要记录

| 任务 | 状态 | 备注 |
|------|------|------|
