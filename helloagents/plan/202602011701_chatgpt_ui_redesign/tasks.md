# 任务清单：全站 UI 重设计（ChatGPT Web 风格 1:1）

## 阶段 A：设计稿（本阶段）

- [√] 收集 ChatGPT Web 参考（可访问来源的截图/布局特征）
- [√] 用 Pencil 产出全站设计稿（覆盖登录/注册/Jobs/New/Detail/Billing/Settings/Admin）
- [√] 调整默认主页：`/jobs` 右侧默认展示“新建题目/Job”表单（替换“选择一个 Job”空态）
- [√] 精简 New Job 表单：移除 Search mode / Max tokens / Temperature；测试数据默认手动输入，`tests.zip` 作为备选
- [√] New Job 表单信息架构：左侧分页（题面数据/代码）+ 顶部模型选择；样例输入/输出双栏并支持多条
- [ ] 你审批设计稿（确认是否按该设计进入前端重构）

## 阶段 B：前端重构（待你审批后执行）

- [ ] 重做全局布局（Sidebar / Topbar / Content / Composer 的统一结构）
- [ ] 登录/注册页重做（对齐卡片、输入、主按钮）
- [ ] Jobs Home 重做（侧栏、列表项、默认右侧新建、空列表态）
- [ ] New Job 表单重做（与 Jobs Home 复用同一套表单结构）
- [ ] Job Detail 重做（Tabs、聊天流、工具输出块、底部 Composer）
- [ ] Billing 重做（指标卡、用量列表）
- [ ] Settings/Codex 重做（chips、双 textarea、保存）
- [ ] Admin 重做（Overview cards、Users table、Models table + inputs/checkbox）
- [ ] 回归检查（所有路由/关键状态、深色模式对比设计稿）
