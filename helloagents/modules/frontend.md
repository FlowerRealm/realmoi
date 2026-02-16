# 模块：frontend（Next.js）

## 职责

- 登录/注册、会话保持（localStorage token）
- 主页调题助手 UI（Portal/Cockpit）：创建 Job、实时终端回放（token 级流）、产物展示（solution/main/report）
- 会话历史：本地保存最近会话与 Job 链，支持“继续对话=新建 Job（seed + 追加指令）”

## 页面（App Router）

- `/`：主页（新一代调题助手 UI：Portal/Cockpit；以 Job + MCP WebSocket 为核心）
- `/jobs/[jobId]`：Job 详情页（与 Cockpit 同构，支持直接打开指定 Job 并追踪 MCP 通知流）
- `/billing`：我的用量与计费页（范围筛选 + KPI + 明细分页 + 费用拆解）
- `/settings/codex`：每用户 Codex overrides 编辑 + effective config 预览
- `/admin/users`：用户管理（admin）
- `/admin/pricing`：模型价格配置（admin，可编辑 `upstream_channel` 上游渠道字段）
- `/admin/upstream-models`：上游 `/v1/models` 多渠道聚合查看（admin，前端可新增/编辑/删除渠道并配置启用状态，默认全启用）
- `/admin/billing`：全站账单看板（KPI + Top 用户/模型 + 最近明细）（admin）
  - 首屏信息层级：KPI 优先，筛选区折叠为次级操作区
  - 筛选交互：草稿态编辑，点击“应用筛选”后才触发请求
- `/login`、`/signup`

## Billing 页信息架构（用户侧）

- 查询层：`start/end/limit` 筛选，快捷范围（今天/昨天/近7天），手动刷新 + 60 秒自动刷新
- 指标层：总费用、请求数、总 Tokens、缓存命中率、定价覆盖率
- 趋势层：双轴趋势图（daily tokens 柱状 + daily cost 折线）+ 缓存命中率
- 结构层：输入/输出/缓存 token 四类拆分
- 明细层：请求记录列表（时间、模型、stage、job、tokens、cost）+ 游标翻页
- 深挖层：单条记录可展开查看 pricing snapshot 与四段费用 breakdown
- 体验层：筛选参数持久化到 localStorage，刷新后保留上次查询范围
- 交互对齐：筛选区采用与 `/admin/billing` 一致的折叠区 + 草稿态 + 手动应用模式
- KPI 对齐：卡片分组与 `/admin/billing` 采用同层级顺序（费用→记录→覆盖/范围→总/交互/缓存 Tokens）

## 规划：Liquid Glass UI（设计先行）

- 方案包：`helloagents/plan/202602031250_liquid-glass-frontend-redesign/`
- 设计稿：`designs/realmoi_ui.pen`（覆盖全站路由页面的 Liquid Glass 视觉方案）
- 说明：当前阶段仅完成设计稿；前端代码尚未按 Liquid Glass 风格重构

## 当前执行规划（2026-02-05）

- 方案包：`helloagents/plan/202602060616_full-ui-redesign-cockpit-style/`
- 目标：以现有 `Portal/Cockpit`（New Job + Job Detailed）为全站视觉与交互基线，推进登录/账单/设置/Admin 的一致化重构
- 交付：已完成全量实施（全局 token、导航、认证、Billing、Settings、Admin 页面改造）并通过 `npm -C frontend run lint` + `npm -C frontend run build`
- 兼容：`/jobs` 继续重定向到 `/`；`/jobs/[jobId]` 作为 Job 详情直达路由保留
- 背景统一：所有页面均复用亮色 `FluidBackground`，与 `/` 主页视觉一致
- 外层一致：所有业务页统一采用 `/` 同款画布壳层与 `AppHeader mode="overlay"` 导航模式
- 间距修复：业务页主内容上边距统一为 `pt-8`，避免与顶栏边框视觉叠加
- 图标规范：新增 `icon-wrap`，统一按钮图标与符号图标的居中对齐
- 登录/注册：输入框前缀图标的左侧内边距固定为 `!pl-10`，避免图标与文字重叠（兼容被基础样式覆盖的情况）

## 终端与状态流

- 实时主流：通过后端 MCP 网关订阅 `agent_status` 通知，按结构化 `kind/delta` 聚合思考/执行/结果三段内容
- 兼容回退：仅当未收到 `agent_status` 通知时，才使用 MCP `terminal` 通知作为 token 流来源
- Job 完成收口：按“主流优先、回退兜底”策略结束 `job-token-*` 消息，避免假流式回放
- 思考样式（2026-02-09）：`【思考】` 片段会单独识别为 `thinking` 项，使用灰色轻量文本展示（更接近 TUI），执行/结果仍保留折叠详情样式
- 思考列表（2026-02-09）：思考增量按“单行条目”追加显示，默认展开且不截断，确保用户始终可见完整思考内容
- 分段策略（2026-02-09）：对 `reasoning_summary_delta` 采用“段落级缓冲”渲染（按空行分段），并结合 `reasoning_summary_boundary(summaryPartAdded)` 与 `summary_index` 强制刷出当前段
- 折叠交互（2026-02-09）：每个 `thinking` 段落改为独立可折叠条目，默认收起（段落完成后自动折叠），执行/结果条目维持原折叠样式
- 并列展示（2026-02-09）：实时渲染由“分组块”改为“时间线并列项”，`【编码】调用 Codex...` 仅是阶段事件之一，Codex 内部思考/执行项会逐条并列出现

## /（主页，新 UI）与后端对接方式（SSOT）

- UI 参考来源：`realm-oi---competitive-programming-assistant/`（Vite + React 原型），已迁移到 `frontend/src/components/assistant/*`
- 鉴权：复用现有 JWT（localStorage `realmoi_token`），由 `RequireAuth` 保护入口
- 启动一次调题：
  - MCP tools：
    - `job.create`（prompt + tests_zip_b64）
    - `job.start`（job_id）
- 实时输出：
  - MCP `job.subscribe`（随后以 JSON-RPC notifications 推送）
    - `method=agent_status`（主实时流）
    - `method=terminal`（回退流）
- 产物展示：
  - MCP `job.get_artifacts`（按需取 `solution.json/main.cpp/report.json`）
- 样例展示：
  - MCP `job.get_tests` / `job.get_test_preview`（展示用户上传的样例输入/输出；结果来自 `report.json`）
- 结构化样例输入：`testCases[{input, output}]` 会在浏览器端打包为 `tests.zip`（in/out pairs），并通过 MCP `tests_zip_b64` 传输
- “继续对话”（MVP 语义）：发送消息会创建新的 Job，并把消息追加到题面末尾作为“用户追加指令”，seed 使用上一轮的 `main.cpp`
- URL 行为：创建/切换 Job 时会同步更新浏览器地址为 `/jobs/{jobId}`；返回大厅会恢复到 `/`
- 顶栏高亮（2026-02-08）：在 `/jobs` 与 `/jobs/{jobId}` 路由下，`AppHeader` 的“助手”导航保持激活高亮
- 详情直达：若直接访问 `/jobs/{jobId}` 且无历史会话上下文，页面提供只读追踪视图（禁用继续对话输入）
- 防重入：New Job 首次启动增加前端防重入，避免开发态 effect 重入导致一次点击创建两个 Job
- 历史恢复：从 RECENT SESSIONS 恢复会话后，地址会自动同步到该会话当前 Job 的 `/jobs/{jobId}`
- 历史持久化修复（2026-02-08）：`AssistantApp` 增加 `historyHydrated` 写入门闩，避免首次渲染把空历史写回 localStorage 覆盖已有会话
- URL 直达恢复（2026-02-08）：访问 `/jobs/{jobId}` 时会在本地历史中按 `runs.jobId` 自动匹配并恢复 `sessionId/prompt/messages/runs`
- Chat 状态流移除（2026-02-08）：不再在 `CHAT` 页签渲染 `agent_status` 的阶段摘要消息，避免与 token 流重复
- Token 级流（2026-02-08）：MCP `terminal` chunk 会实时同步到 `CHAT` 消息卡片（`job-token-{jobId}`），用于展示更细粒度执行流
- Token 步骤去重（2026-02-08）：状态提取只认 `[status]` 真实日志，忽略 `status_update(...)` 脚本源码，修复每个阶段在「思考过程」中重复两次的问题
- Token 样式统一（2026-02-08）：`job-token-*` 消息卡片视觉改为普通 assistant 气泡（移除深色终端风与等宽字体），仅保留 token 流语义文案
- Token 对话化（2026-02-08）：`job-token-*` 日志按 `[codex] exit=...` 切分后逐条展示（不显示“片段 N”），并清理 `[codex]` 前缀
- Token 默认折叠（2026-02-08）：每条 token 日志默认折叠展示，条目之间使用分割线隔开，并同步清理 `[runner]` 前缀
- Token 卡片拆分（2026-02-08）：取消 token 日志的统一外层大框，每条折叠日志独立为单独卡片
- Token 外层去框（2026-02-08）：`job-token-*` 消息移除最外层聊天气泡边框，仅保留内部日志条目卡片
- Token 样式统一（2026-02-08）：`job-token-*` 重新对齐普通 assistant 气泡样式（外层白底边框 + 白底折叠条目）
- Token 外框回退（2026-02-08）：按最新交互要求再次移除 `job-token-*` 外层气泡，仅保留内部白底折叠条目与统一正文样式
- Token 文案精简（2026-02-08）：移除“已创建 Job/正在启动/Token级流式输出中/Job ... Token级流式输出”等提示，仅保留日志正文
- 历史文案过滤（2026-02-08）：对旧会话中的“已创建 Job / 正在启动并追踪终端输出 / 我会基于上一轮代码...”提示做渲染过滤
- 过程日志收敛（2026-02-08）：token 日志改为单个“过程日志（N条）”折叠入口，运行中展开、完成后默认折叠
- VSCode 风格对齐（2026-02-08）：过程日志面板切换为 Codex 扩展风格（`PROCESS (N)` + 等宽步骤摘要 + 代码风正文）
- 过程边框移除（2026-02-08）：按最新交互要求去掉思考过程面板和条目的边框线，仅保留层次与折叠交互
- 日志噪音清理（2026-02-08）：移除 `MODE=...`、`$ /bin/bash -lc ...`、`exit=...` 与 `status_update` here-doc 包装内容
- 思考摘要保留（2026-02-08）：在噪音清理后保留 `status_update(stage, summary)`，并转换为 `[ANALYSIS]/[PLAN]/[CODING]` 可读条目
- 过程分段修复（2026-02-08）：token 过程日志改为按“阶段状态/结果/Token统计/后端重试”事件边界切分，避免多轮日志被挤在单条“编码”项中
- 中文化与流式恢复（2026-02-08）：
  - Cockpit 关键文案统一中文（工作区/思考过程/代码/取消任务/前置假设/复杂度）
  - 过程日志新增解析 `[status] stage=... summary=...` 行，并映射为中文阶段标签（分析/方案/编码/修复等）
  - `PROCESS (N)` 标题切换为 `思考过程（N）`
- 历史兼容（2026-02-08）：旧会话中残留的 `job-stream-*` 消息会被前端过滤，不再显示“实时进展（已结束）”卡片
- Cockpit 标签精简（2026-02-08）：先移除 `TERMINAL` 页签，后续继续移除 `STATUS` 页签；终端增量日志仅作为 `CHAT` Token 流来源
- 样例面板（2026-02-10）：新增“样例 / 结果”栏（CPH 风格），与代码并列展示 input/expected/actual（stdout）、verdict/diff，并按 verdict 整卡变色；移除字节大小与 `exit=...` 字段，新增时间/内存展示（内存统一按 MB 单位展示；顶部展示总耗时/峰值内存，不再展示 TL/ML 限制）
- 顶栏避让（2026-02-08）：`AssistantApp` 主容器顶部留白提升为 `pt-16 md:pt-20`，消除页面主体与固定顶栏重叠
- Cockpit 双栏（2026-02-08）：移除左侧信息栏与 `STATUS` 页签，工作区改为 `CHAT`（左）+ `CODE`（右）并列布局，状态信息仅保留在顶部摘要与最终结果消息
- 失败态行为：Job 进入终态后会尽量拉取 `main.cpp/solution.json/report.json`，即使失败也方便用户查看失败详情与中间产物
- 用户反馈展示：Job 终态拉取到 `solution.json` 后，会在左侧新增一条 `assistant` 消息（`messageKey=job-feedback-*`）展示“解读与反馈”（含 `user_feedback_md/solution_idea/seed_code_*`）；右侧代码面板支持“最终代码/差异”切换，图形化 diff 视图优先渲染 `seed_code_full_diff`（seed→最终 `main.cpp` 的全量 diff），缺失时回退 `seed_code_fix_diff`（不再输出“Job 已结束...请查看右侧面板”提示）
- 模型列表加载：普通用户不再触发 admin upstream 接口探测，避免 403 噪音
- New Job 参数面板：已移除 `Search` 与 `Compare Mode` 字段，当前提供 `Model`、`思考量（low/medium/high/xhigh）`、`Time Limit`、`Memory`
- 模型下拉来源优先级：先读本地缓存（`realmoi_admin_upstream_models_cache_v1`，180 秒内直出）→ 优先 `GET /api/models/live` → 失败时回退 `GET /api/models`
- admin 用户在缓存过期时，会额外尝试按渠道实时拉取 `/api/admin/upstream/models` 更新本地缓存
- 模型下拉显示：统一按 `"[渠道] model_id"` 显示，并只展示有渠道归属的模型
- New Job 提交会附带 `upstream_channel`，确保使用缓存/实时模型时也能正确路由到指定渠道
- 样式基线（2026-02-07）：统一 `Geist + Noto Sans SC` 字体栈、面板圆角/边框/阴影与字号层级，避免“字体风格混杂、框不齐、视觉重叠”
- Cockpit 终端区在首次挂载时增加 `ResizeObserver + document.fonts.ready` 自动 `fit()`，降低终端文本截断和错位
- 工作区合并（2026-02-08）：Cockpit 的对话区与终端区合并为单面板标签页（`CHAT/TERMINAL/STATUS/CODE`），桌面端保留左侧运行信息栏，移动端改为“运行信息”抽屉，整体间距与对齐策略统一；对话输入栏位于 `CHAT` 页签内部底部（非页面级独立底栏）
- CHAT 底部锚定修复（2026-02-08）：`CHAT` 面板改为 `flex-col`，消息区 `flex-1`，输入栏增加 `mt-auto` 强制贴底，确保输入框始终在 chat 内容区最底部而非悬浮在中段

## Admin / Upstream Models 关键交互

- 查询模型不再提供“启用/禁用查询渠道”勾选，页面默认按“全部已启用渠道”自动拉取
- 查询结果支持本地缓存与默认值策略：默认自动刷新间隔为 180 秒，减少重复请求流量
- 支持手动刷新（强制拉取）与自动延迟刷新（可选 关闭/60/180/300/600 秒）
- 模型列表统一展示为 `"[渠道] 模型名"`，用于区分跨渠道同名模型
- 新增渠道入口改为右上角“图标+文字”按钮，点击后打开居中小窗进行填写
- 新增渠道小窗采用分组字段布局（channel/display_name/base_url/api_key/models_path）与独立底部操作区
- 新增渠道小窗使用更高不透明度的遮罩与面板，减少背景干扰
- 渠道编辑时 API Key 输入框默认留空；留空保存代表“保持原密钥不变”
- 渠道列表只显示脱敏密钥（`api_key_masked`），不显示明文密钥
- 非默认渠道支持删除；默认渠道仅展示只读信息
- 上游拉取失败提示按错误码转为中文可读文案（如 `upstream_unavailable` / `upstream_unauthorized`）
- 上游模型展示默认仅显示常见对话模型，可通过“显示全部模型”查看 embedding/tts/realtime 等完整返回

## Admin / Pricing 持久化行为

- 数据来源：自动聚合全部已启用渠道的实时 `model id`（`/admin/upstream/models`），并与已保存的价格配置做 union；实时发现的模型以 `INACTIVE` 卡片显示（可直接补齐字段后保存）
- 编辑行为：默认只读（字段以文本展示）；点击单条“编辑”进入编辑态（字段变为受控输入），点击“取消”会回滚到进入编辑态前的快照
- 展示优化：只读态不再使用“类似输入框的外框”展示数值，减少误导用户“当前可直接编辑”的视觉暗示
- 元信息收敛：只读态隐藏 `upstream_channel/currency/unit`，仅保留 `model/ACTIVE/4 个价格字段`；渠道修改移至编辑态“高级字段”
- 保存策略：按 `model` 逐条保存；编辑态下修改会标记为“待保存”，仅 dirty 时可点击“保存”；保存中展示 loading；保存成功会退出编辑态并清除 dirty（不触发全量 reload）
- 启用校验：当条目 `ACTIVE=true` 且缺失任一价格字段时，缺失输入会高亮并显示提示；点击保存会被前端拦截并提示“需填齐 4 个字段”，避免后端 422
- 交互表达：`ACTIVE` 在编辑态使用 switch；只读态仅展示“已启用/未启用”；币种/单位为固定概念不在卡片中冗余展示；头部提供总数/可见/active/待保存/实时发现/缺失定价等关键指标
- 拉取容错：按渠道并行拉取实时模型；单个渠道失败不阻断整体展示，仅提示“部分渠道拉取失败”
- 前缀显示：模型显示统一按 `"[channel] model"` 前缀化；空渠道显示为 `未分配`

## Admin / Users 页面风格

- 页面壳层与其它业务页一致：顶部 `glass-panel-strong` 标题区（含 KPI chips）+ `glass-panel` 筛选区 + 列表区
- 列表区为自绘 `glass-table`：列聚焦 `username/role/status/actions`；移动端隐藏“创建时间”列，避免窄屏裁切与按钮遮挡
- 管理弹窗：点击列表“管理”弹出小窗口，展示用户详情（id/创建时间/徽标），支持角色切换、启用/禁用、重置密码入口；并对“禁用自己”给出前端提示（后端亦会拦截）
- 弹窗：支持“新建用户”（随机生成密码）与“重置密码”（随机生成 + 一键复制）
- 分页条沿用同款组件组合（上一页/下一页 + 每页条数），与 `Admin / Pricing`、`Admin / Upstream Models` 的交互密度一致

## 配置

- `NEXT_PUBLIC_API_BASE_URL`：后端 API base（默认 `http://0.0.0.0:8000/api`）
- `NEXT_PUBLIC_API_PORT`：当 `NEXT_PUBLIC_API_BASE_URL` 被判定为外网不可用（如 `localhost`）并触发回退时，用于覆盖自动推断端口（默认 `8000`）
- 外网保护：若构建时 `NEXT_PUBLIC_API_BASE_URL` 被写成 `localhost/127.0.0.1`，前端在外网访问时会自动忽略该值并使用运行时推断地址

## 本地开发

- 推荐：项目根目录执行 `make dev`（会自动设置 `NEXT_PUBLIC_API_BASE_URL` 指向本地后端）

## UI 巡检（Playwright 截图）

- 目的：全站逐页截图（多视口），用于定位“按钮不对齐 / 内容裁切 / 布局错位”等 UI 问题；先输出 `report.md` + 截图，再按清单逐项修复回归（B 流程）。
- 一键运行：`bash scripts/pw_ui_audit.sh`（或传入自定义输出目录作为第 1 个参数）
- 输出目录：`output/playwright/ui-audit/<timestamp>/`
  - `report.md`：问题索引与截图路径
    - 自动信号（启发式）：水平溢出、overflow 裁切、点击目标遮挡/重叠、按钮行不对齐、文本截断
  - `screenshots/<project>/`：按视口（project）分组的 viewport/fullPage 截图
  - `playwright.log`、`dev_backend.log`、`dev_frontend.log`：运行日志
- 常用环境变量：
  - `REALMOI_BACKEND_PORT` / `REALMOI_FRONTEND_PORT`：端口
  - `REALMOI_PW_USERNAME` / `REALMOI_PW_PASSWORD`：用于登录（默认继承 `REALMOI_ADMIN_USERNAME` / `REALMOI_ADMIN_PASSWORD`）
  - `REALMOI_PW_JOB_ID`：覆盖 `/jobs/[jobId]` 的动态参数（未提供时脚本会尽量自动补齐：默认隔离的 `jobs_root` 会注入样例 Job，或通过 `/api/jobs` 自动解析）
  - `REALMOI_DB_PATH` / `REALMOI_JOBS_ROOT` / `REALMOI_CODEX_AUTH_JSON_PATH`：后端数据与产物路径（脚本默认隔离到本次 `out_dir` 下，避免污染已有本地数据）
    - 脚本默认隔离 `jobs_root=out_dir/jobs`，并会从仓库根目录 `jobs/` 复制 1 个样例 Job 进去，保证 `/jobs/[jobId]` 可被巡检覆盖
    - 如需用“真实数据”复现错位/裁切：可把 `REALMOI_DB_PATH` / `REALMOI_JOBS_ROOT` 指向一份带数据的拷贝（推荐先复制再跑），并确保登录账号具备 `admin` 权限

## 设计稿（Pencil）

- 全站设计稿：`designs/realmoi_ui.pen`（每个路由页面对应一个 Frame；`/` 额外拆分 Portal/Cockpit 两张屏，作为全站视觉基准）
