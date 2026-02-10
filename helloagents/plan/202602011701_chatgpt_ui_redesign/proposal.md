# 方案提案：全站 UI 重设计（ChatGPT Web 风格 1:1）

## 背景

当前 RealmOI 前端 UI 以功能为主，视觉与交互风格不统一。你希望整体重做，并在你审批设计稿后再进入前端代码改造。

## 目标

- 产出 **Pencil 设计稿**，整体观感与交互结构尽量 **1:1 复刻 ChatGPT 网页版**（以深色模式为主）。
- 覆盖全站核心路由与关键状态（空态、列表、详情、表单、管理后台）。
- 建立可复用的视觉规范：颜色、字体、间距、圆角、按钮与输入控件形态。
- **本阶段不改前端代码**；仅交付设计稿 + 任务清单，等待你审批。

## 范围（路由覆盖）

- `/login`：登录
- `/signup`：注册
- `/(home)`：默认进入 `/jobs`
- `/jobs`：Jobs 列表（左侧栏）+ 右侧默认“新建题目/Job”（不再是“选择一个 Job”的空态）
- `/jobs/new`：New Job 表单（与 `/jobs` 右侧新建一致，用于直达/分享）
- `/jobs/[jobId]`：Job Detail（聊天式时间线 + Composer + Tabs）
- `/billing`：计费与用量
- `/settings/codex`：Codex 配置（Allowed Keys / Overrides / Effective）
- `/admin`：Admin Overview
- `/admin/users`：Users 表格
- `/admin/models`：Models & Pricing（输入框 + checkbox）

## 设计规范（草案）

### 颜色（Dark）

- BG：`#0B0F14`
- Sidebar：`#0F172A`
- Surface：`#111827`
- Text primary：`#E5E7EB`
- Text secondary：`#9CA3AF`
- Text muted：`#6B7280`
- Accent：`#10A37F`
- Warning：`#F59E0B`
- Danger：`#EF4444`

### 字体

- UI：`Inter`
- Code：`JetBrains Mono`

### 关键组件形态（与 ChatGPT 视觉对齐）

- 左侧 Sidebar：New button / Search / 列表项 / 底部用户区
- 顶部 Topbar：页面标题 + 右侧 pill actions
- Tabs：圆角 pill（选中为 Surface，未选中为 Sidebar 色）
- 卡片 Card：`Surface + radius 16`
- 输入 Input / Textarea：`BG` 色块内嵌于 Card，圆角 10~12
- Table：卡片容器内的行列布局（每列独立 cell frame）
- 聊天流：User 右侧气泡 + Assistant 左侧头像 + 工具输出块（等宽）
- Composer：底部固定输入条 + Send button
- New Job：仅保留 Model；移除 Search mode / Max tokens / Temperature；测试数据默认手动输入，`tests.zip` 作为备选
- New Job：左侧分页（题面数据/代码）承载信息分组；样例输入/输出双栏并可添加多条

## 交付物

- `designs/realmoi_chatgpt_ui.pen`：全站 UI 设计稿（深色模式优先）
- `helloagents/plan/202602011701_chatgpt_ui_redesign/tasks.md`：执行任务清单（含审批后代码改造计划）

## 验收标准（本阶段）

- 设计稿已覆盖上述全部路由（每个路由至少 1 个主屏）。
- 视觉层级、间距、圆角与组件形态与 ChatGPT 网页版风格一致（以深色模式为基准）。
- 你确认“可以开始改前端代码”后，才进入下一阶段（前端重构实施）。
