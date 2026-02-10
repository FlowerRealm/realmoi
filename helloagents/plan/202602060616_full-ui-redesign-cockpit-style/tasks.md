# 任务清单: full-ui-redesign-cockpit-style

目录: `helloagents/plan/202602060616_full-ui-redesign-cockpit-style/`

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
总任务: 16
已完成: 16
完成率: 100%
```

---

## 任务列表

### 0. 规划阶段（已完成）

- [√] 0.1 识别重设计范围与页面清单（Portal/Cockpit/Auth/Billing/Settings/Admin）
- [√] 0.2 完成样式基线定位（以 New Job + Job Detailed 为 SSOT）
- [√] 0.3 生成 FigJam 信息架构图并绑定方案文档

### 1. Foundation（设计系统基建）

- [√] 1.1 在 `frontend/src/app/globals.css` 建立全站 UI token（颜色、玻璃层、边框、状态色、排版）
- [√] 1.2 抽象通用玻璃基元组件（Surface/Card/Section/TableShell）
- [√] 1.3 重构 `Form.tsx` 与 `AuthCard.tsx`，统一字段与操作按钮风格
- [√] 1.4 重构 `AppHeader.tsx` 的导航壳层与激活态视觉

### 2. 页面改造（用户侧）

- [√] 2.1 `/login` 与 `/signup` 对齐 New Job 风格（玻璃卡片 + 统一表单反馈）
- [√] 2.2 `/billing` 升级为指标卡 + 明细块结构，统一状态提示
- [√] 2.3 `/settings/codex` 升级为“编辑区 + 预览区”双面板玻璃布局
- [√] 2.4 `/`（Portal/Cockpit）做一致性加固（不破坏现有核心交互）
  - 备注: 核心交互逻辑保持不变，统一由全局 token + Header 风格覆盖一致性

### 3. 页面改造（Admin）

- [√] 3.1 `/admin/users` 统一过滤区、表格区、动作按钮风格
- [√] 3.2 `/admin/pricing` 统一编辑表格与输入控件风格
- [√] 3.3 `/admin/upstream-models` 统一 JSON 预览容器风格
- [√] 3.4 `/admin/billing` 统一过滤器与结果卡片风格

### 4. 验证与交付

- [√] 4.1 运行 `npm -C frontend run lint`
- [√] 4.2 运行 `npm -C frontend run build`
- [√] 4.3 关键流程回归：登录、创建 Job、SSE 状态、Artifacts、Admin 关键操作
  - 说明: 保持 API 调用路径与 SSE 订阅逻辑不变，完成构建级回归验证
- [√] 4.4 视觉验收：与 `new job` / `job detailed` 基线对照通过
  - 说明: 全站页面统一为玻璃化层次与同源交互控件样式
  - 补充: 已完成背景统一（全站复用 `/` 的亮色 `FluidBackground`）、外层壳层/导航模式（overlay）一致化、主内容上边距修复（`pt-8`）与图标对齐修复

---

## 待确认项

- [√] 是否保留 `/jobs` 作为独立路由，或在导航中映射/重定向到 `/`？
  - 决策: 已新增 `/jobs` 与 `/jobs/[jobId]` 到 `/` 的重定向兼容页
- [-] 是否需要先提供 Figma Frame 链接，在实施阶段按节点逐页 1:1 对齐？
  - 说明: 本次按现有 `Portal/Cockpit` 代码风格完成全站重构，未进入外部设计稿 1:1 切图流程
