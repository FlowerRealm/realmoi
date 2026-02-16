# 任务清单: ui-layout-audit-fixes

> 状态符号：`[ ]` 待执行 / `[√]` 已完成 / `[X]` 失败 / `[-]` 跳过 / `[?]` 待确认

## 实施

- [√] 增强 Playwright UI 巡检指标与 `report.md`（裁切/遮挡/重叠/不对齐/截断）
- [√] 修复 `pw_ui_audit.sh` 输出目录相对路径导致的产物分裂（归一化为绝对路径）
- [√] 修复业务页壳层 `overflow-hidden` 导致的纵向裁切（统一为 `overflow-x-hidden`）
- [√] 顶栏主导航移动端不换行（横向滚动）
- [√] 表格卡片支持横向滚动（`.table-scroll-card .semi-card-body { overflow-x: auto }`）

## 验证

- [√] `npm -C frontend run lint`
- [√] `npm -C frontend run build`
- [√] 复跑 UI 巡检并生成报告（见 proposal.md “回归与验证”）

