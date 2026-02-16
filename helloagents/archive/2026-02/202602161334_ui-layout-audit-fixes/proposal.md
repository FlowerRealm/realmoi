# 变更提案: ui-layout-audit-fixes

## 元信息
```yaml
类型: 修复
方案类型: implementation
优先级: P0
状态: 已完成
创建: 2026-02-16
```

---

## 1. 需求

### 背景
你近期对前端做了较多样式与布局调整，出现了“按钮对不齐、内容显示不齐、东一块西一块”的现象。之前已落地 Playwright 的“全站 UI 巡检（截图 + 报告）”作为回归手段，但报告自动信号较少，且顶栏/页面壳层的布局约束不稳定，导致移动端更容易出现错位与裁切。

### 目标
1. 增强 UI 巡检报告的自动信号：除水平溢出外，补充裁切/遮挡/重叠/按钮行不对齐/文本截断等启发式指标，便于快速定位问题页。
2. 修复全站最容易引发“错位/裁切”的基础布局问题：
   - 顶栏导航在窄屏不再换行（避免顶栏高度抖动压住内容）。
   - 业务页外层不再使用 `overflow-hidden`（避免纵向内容被裁切），保留 `overflow-x` 的保护。
   - 表格卡片在移动端可横向滚动（避免表格被卡片裁切）。
3. 保持可回归：修复后能复跑 UI 巡检与前端构建，作为后续逐页细修的基线。

### 验收标准
- [ ] `scripts/pw_ui_audit.sh` 支持传入相对/绝对输出目录且 Playwright 输出稳定落在同一 `out_dir` 下。
- [ ] `report.md` 汇总新增自动信号：overflow 裁切、点击目标遮挡/重叠、按钮行不对齐、文本截断。
- [ ] `npm -C frontend run lint` 与 `npm -C frontend run build` 通过。
- [ ] 复跑 UI 巡检覆盖所有页面与多视口（Chromium），无错误记录。

---

## 2. 实施与变更点

### 2.1 UI 巡检增强（Playwright）
- 指标采集增强：`frontend/pw/audit-metrics.ts`
  - 新增：overflow 裁切（`overflow:hidden/clip`）、点击目标遮挡（`elementFromPoint`）、点击热区重叠、按钮行不对齐（同 flex row）、文本截断（`scrollWidth > clientWidth`）。
  - 降噪：给 `AppHeader` 增加 `data-app-header` 标记，巡检默认忽略顶栏内元素，避免导航滚动导致的误报。
- 报告增强：`frontend/pw/report.ts`
  - 新增摘要统计与按类型分组的小节表格，便于“先看问题页，再开截图”。

### 2.2 一键脚本稳定性
- 输出目录绝对化：`scripts/pw_ui_audit.sh`
  - 将 `out_dir` 归一化为绝对路径，避免在 `npm -C frontend` 运行时相对路径被解析到 `frontend/` 下导致产物分裂。

### 2.3 全站布局修复（对齐/裁切）
- 页面壳层：`frontend/src/app/**/page.tsx`
  - 将业务页外层从 `w-screen ... overflow-hidden` 调整为 `w-full ... overflow-x-hidden`，避免纵向滚动被裁切，保留横向溢出保护。
- 顶栏导航：`frontend/src/components/AppHeader.tsx`
  - 主导航改为 `flex-nowrap + overflow-x-auto`，窄屏不再 wrap；并为滚动条使用 `custom-scrollbar`。
- 表格卡片横向滚动：`frontend/src/app/globals.css`
  - `.table-scroll-card .semi-card-body` 增加 `overflow-x: auto`，移动端宽表格可横向滚动而不是被卡片裁切。
- 管理端用户表格：`frontend/src/app/admin/users/page.tsx`
  - `CardTable` wrapper 改为 `overflow-x-auto`，与卡片 body 横向滚动策略一致。

---

## 3. 回归与验证

- UI 巡检（示例输出）：
  - `output/playwright/ui-audit/20260216_133109/report.md`
- 前端质量门禁：
  - `npm -C frontend run lint`
  - `npm -C frontend run build`

---

## 4. 技术决策

### ui-layout-audit-fixes#D001: 顶栏主导航移动端不换行，改为横向滚动
**日期**: 2026-02-16
**状态**: ✅采纳
**背景**: admin 角色下顶栏链接数量较多，`flex-wrap` 会显著抬高顶栏高度；配合 `overlay(fixed)` 模式时易出现内容被顶栏压住/按钮错位。
**决策**: 顶栏主导航使用 `flex-nowrap + overflow-x-auto`，让高度稳定，窄屏通过横向滚动浏览全部入口。
**影响**: 顶栏在手机上保持单行高度；巡检报告默认忽略顶栏元素以避免滚动导致的误报。

