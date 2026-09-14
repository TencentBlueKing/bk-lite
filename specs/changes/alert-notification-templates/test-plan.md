# 告警中心自定义通知模板测试与验收记录

状态：本地自动化与浏览器新增流程已通过；普通模板六渠道默认内容和告警操作通知改版均已完成实施；真实渠道、PostgreSQL 并发和部署验收待执行。

日期：2026-09-09。

## 1. 验证原则

测试覆盖模板渲染、组织权限、配置绑定、四类生命周期、Outbox 快照和 SystemMgmt 渠道兼容。外部 SMTP、HTTP、NATS、目录查询均在自动化中替换为可控边界；模板选择、渲染、绑定继承和投递状态机使用真实实现。

本轮不把未分派汇总列为第一版通过项。相关 `summary` 范围只保留设计入口，待接入 `UnDispatchService` 后单独补齐 0/1/10/11 条汇总、排序和组织边界测试。

## 2. 自动化覆盖

### 2.1 渲染与安全

文件：`server/apps/alerts/tests/test_notification_template_render_pure.py`

- 邮件 HTML 保留模板结构，动态值按文本转义；
- Markdown 保留模板语法，动态值转义并中和提及；
- 缺失字段显示 `—` 并返回诊断；
- 拒绝调用、私有属性、过滤器、循环和未闭合标记；
- 拒绝 script、事件属性、危险 URL、外部 CSS 资源及属性位置变量；
- 变量内容不二次求值；
- 标题源和动态值的换行注入均被拒绝；
- 大集合、深结构、单值、占位符和输出均受限。

### 2.2 API、组织与并发更新

文件：`server/apps/alerts/tests/test_notification_template_views.py`

- 多渠道内容原子创建并可读取；
- 团队 ID 规范化，同组织范围同名模板受数据库约束；
- PUT/PATCH 必须携带当前 revision，陈旧版本返回 409；
- PostgreSQL 行锁查询的外层不携带 `DISTINCT`，避免编辑、删除返回 500；
- 渠道与格式不匹配时拒绝保存；
- 团队模板隔离，全局模板只读可见；
- 每个当前团队只自动建立并展示一个“告警操作通知”内置模板；其他团队的操作模板不可见；
- 告警操作模板只接受当前团队的一个具体渠道和一份匹配内容，允许修改渠道/内容，拒绝删除和复制；
- 告警操作模板不会出现在普通分派策略的模板候选中，测试发送只能使用页面当前选择的唯一渠道；
- 列表按不同分派策略去重返回 `assignment_count`，同策略多场景引用和活动升级快照不会重复计数；
- 预览只调用渲染器，不发送；
- 预览中的 `alert.level` 使用“警告”等展示名称，同时保留 `alert.level_id` 原始值；
- 新版告警操作邮件默认内容能够通过真实预览 API 渲染，标题、操作说明和待响应状态正确；
- 操作专用变量只允许用于 `alert_operation`，普通模板手工输入时返回 400；
- 未编辑的旧内置默认内容自动升级并递增 revision，用户自定义内容保持不变；
- 被引用模板删除返回 409；
- 新建页和编辑页都可测试发送，使用页面当前未保存的标题、正文和所选渠道版本；
- 测试发送必须选择当前团队可见的真实告警，实际告警字段进入渲染上下文；跨团队或不存在的告警被拒绝；
- 测试接收人默认当前用户并支持多选；接收人进入渲染上下文和实际投递参数，重复项去重，不存在的用户名被拒绝；
- 测试发送使用有权限的真实渠道、关闭接收人正文追加；
- sample 超过 64KB 时拒绝。

### 2.3 绑定、可信渠道与引用

文件：`server/apps/alerts/tests/test_notification_template_binding_service.py`

- 模板必须包含渠道对应内容；
- 保存策略同步引用索引；
- 前端伪造渠道类型时按数据库渠道拒绝；
- 场景模板优先，缺失时继承 default；
- 运行时模板与告警组织不相交时回退。

文件：`server/apps/alerts/tests/test_escalation_service.py`

- 创建升级任务时冻结渠道模板绑定；
- 活动任务建立快照引用，策略后续修改不改变任务；
- 停止或清理任务后释放快照引用。

### 2.4 渲染、Outbox 与渠道投递

文件：

- `server/apps/alerts/tests/test_notification_template_delivery_service.py`
- `server/apps/alerts/tests/test_notify_dispatcher.py`
- `server/apps/alerts/tests/test_notification_delivery_service.py`

已覆盖：

- 同一告警按渠道分别生成标题和正文；
- 运行时按 `Level(level_type=alert)` 将数字级别映射为展示名称，并通过 `alert.level_id` 暴露原始值；
- 模板 ID、revision、scene、missing fields 随内容冻结到 Outbox；
- 运行时模板异常只让当前渠道回退固定内容；
- OpsPilot NATS 维持 `message/team/user_ids` 包装，无单一组织时跳过；
- 多渠道独立投递和重试，一个渠道失败不影响其他渠道；
- Broker 失败保留持久意图；租约过期后旧 Worker 不能覆盖新结果；
- 历史已成功记录不重新解释或重放。

### 2.5 告警生命周期相关性回归

文件：

- `server/apps/alerts/tests/test_auto_assignment_chain.py`
- `server/apps/alerts/tests/test_reminder_service.py`
- `server/apps/alerts/tests/test_escalation_service.py`
- `server/apps/alerts/tests/test_escalation_assignment_flow.py`
- `server/apps/alerts/tests/test_recovery_notify.py`
- `server/apps/alerts/tests/test_un_dispatch_and_reminder_extra.py`
- `server/apps/alerts/tests/test_un_dispatch_nats_guard.py`

这些测试共同验证聚合后的告警进入自动分派、提醒、升级和恢复时，原告警状态、接收人选择、提醒计数、升级层和恢复条件不被模板接入改变；未分派通知保持原固定内容和 NATS 组织保护。

文件：`server/apps/alerts/tests/test_alert_operator.py`

- 人工分派和转派使用告警所属团队唯一的“告警操作通知”模板及已选渠道；
- 人工分派场景渲染为“告警分派”，转派场景渲染为“告警转派”；
- 所选渠道缺失、失效、格式不匹配或不属于告警团队时不改用其他渠道，操作成功但不发送通知；
- 当执行分派的人同时是接收人时不会再被过滤，通知会正常进入统一 Outbox。

### 2.6 SystemMgmt/RPC 兼容

文件：

- `server/apps/alerts/tests/test_notification_template_channel_compat.py`
- `server/apps/alerts/tests/test_get_channel_list_views.py`
- `server/apps/system_mgmt/tests/test_slice_channel_utils.py`
- `server/apps/rpc/tests/test_system_mgmt_forwarding.py`

已覆盖：

- 自定义模板关闭机器人接收人正文追加，但接收人参数仍保留；
- 旧调用默认继续追加；
- 告警渠道候选排除普通 NATS 和应用企微，并入当前组织可用的 OpsPilot NATS；
- RPC 新参数与默认值正确透传；
- 邮件、机器人和自定义 Webhook 原有包装契约保持兼容。

### 2.7 Web 行为与静态检查

文件：

- `web/src/app/alarm/utils/__tests__/notificationTemplateChannels.test.ts`
- `web/src/app/alarm/(pages)/settings/alertAssign/components/__tests__/notificationTemplateBinding.test.ts`
- `web/src/app/alarm/(pages)/settings/alertAssign/components/__tests__/operateModal.channels.test.tsx`

- 六类渠道的编辑模式、预览模式和标题能力映射正确；
- 未支持的渠道不会被误识别为可编辑模板格式。
- 告警操作内置模板页面只有一个具体渠道选择框，保存保留 `alert_operation` 作用域和唯一 `channel_id`；
- 名称与用途不可编辑，标题和正文可编辑，测试发送的渠道选择固定为已选渠道；
- 旧版一行式告警操作邮件正文载入后转换为多行缩进 HTML，Ace 自动换行且预览内容不变；
- 页头提供带文案的返回按钮、简化标题、内置标识和用途说明，操作模板不再展示重复的只读名称与用途输入框；
- 效果预览使用 520px 最小高度、800px 最大高度和视口自适应高度，超长内容在 iframe 内滚动；
- 六类渠道都有可直接使用的业务默认正文；邮件、钉钉和飞书标题包含通知场景、映射后的告警级别与告警标题；
- 默认正文覆盖告警内容、资源、监控来源、指标、发生时间、告警 ID 和本次接收人。
- 多个通知渠道分别展示模板绑定卡片，每个渠道包含默认、提醒、升级和恢复四个场景；
- 每个场景只提供包含当前渠道版本的模板组，保存时按渠道保留独立绑定；
- 编辑已有策略时逐渠道、逐场景回填已有绑定；
- 渠道和模板选项分别加载，模板加载失败不会破坏通知渠道选择。

TypeScript 类型检查覆盖模板 API、列表/编辑路由和分派抽屉绑定结构；目标 ESLint 覆盖本次所有新增及修改的 Web 文件。

## 3. 本次执行结果

| 检查 | 结果 | 证据 |
|---|---|---|
| 后端模板与设置聚焦回归 | 通过 | 85 passed |
| 后端完整相关回归 | 通过 | 267 passed in 5.91s |
| 本轮级别映射、人工分派及通知链路回归 | 通过 | 294 passed in 7.32s |
| 告警操作内置模板完整相关回归 | 通过 | 299 passed in 8.17s |
| 告警操作模板最终聚焦回归 | 通过 | 66 passed in 3.15s |
| 后端 Flake8 | 通过 | exit code 0 |
| Django 迁移遗漏检查 | 通过 | `No changes detected in app 'alerts'` |
| `alerts.0030` SQL 展开 | 通过 | 三张表、索引及唯一约束均成功生成 |
| `alerts.0032` SQL 展开 | 通过 | 唯一渠道字段、作用域及同组织同范围名称约束均成功生成 |
| Web 分派模板及编辑删除聚焦 Vitest | 通过 | 4 files、11 tests passed |
| Web 六渠道业务默认模板聚焦 Vitest | 通过 | 2 files、4 tests passed |
| 普通模板六渠道默认内容评审 | 通过 | Chrome 新建页逐渠道渲染通过；用户确认采用评审稿作为默认值 |
| Web 告警操作模板与分派交互 Vitest | 通过 | 5 files、14 tests passed；最终聚焦 2 files、8 tests passed |
| Web 目标 ESLint | 通过 | exit code 0 |
| Web TypeScript | 通过 | `next typegen` 与 `tsc --noEmit` exit code 0 |
| Chrome 新增页运行时 | 通过 | Next.js 16.3/Turbopack 下 Ace 按客户端动态加载，无 `ace is not defined` |
| Chrome 模板新增、编辑与回显 | 通过 | 邮件 HTML、企业微信 Markdown 独立保存、预览、编辑并刷新列表更新时间 |
| Chrome 分派场景绑定 | 通过 | 邮件与企微分别展示默认、提醒、升级和恢复四个模板组字段；邮件提醒与企微恢复分别保存并重开回显 |
| 分派持久化结构 | 通过 | 每个渠道只保存本渠道已选择的场景绑定，空场景按运行时规则回退 |
| Chrome 模板编辑 | 通过 | 详情加载期间保存、预览和测试发送均禁用；加载完成后修改用途说明成功，列表更新时间刷新 |
| Chrome 模板删除 | 通过 | 已绑定模板删除禁用；新建一次性未绑定模板后确认删除成功，列表由 4 项恢复为 3 项 |
| PostgreSQL 行锁查询 | 通过 | 当前部署数据库中事务加锁命中模板并回滚，无 `DISTINCT + FOR UPDATE` 异常 |

后端回归使用 SQLite 和 `--nomigrations`，环境变量限定安装 `system_mgmt,alerts`，未启动本机 PostgreSQL、Redis 或 NATS。完整相关回归包含 19 个测试文件，覆盖模板新增测试及受影响的既有告警、SystemMgmt、RPC 测试。

使用真实迁移链建库时，仓库既有的早期迁移在当前代码状态下会因 `NewSessionEventRelation` 缺少 `event` 字段失败，发生在 `alerts.0030` 之前。该问题不是本次迁移引入；本次已通过模型迁移一致性检查，`0030` 仍需在现有部署数据库或修复后的完整迁移链上演练。

### 3.1 2026-09-10 普通模板六渠道默认内容实施

| 检查 | 结果 | 证据 |
|---|---|---|
| 默认内容 TDD 回归 | 通过 | 旧默认值触发预期失败；替换后目标 Vitest 2 tests passed |
| 通知模板相关 Web 回归 | 通过 | 3 files、7 tests passed |
| 目标 ESLint | 通过 | 默认内容、回归测试和编辑器接线无告警 |
| TypeScript | 通过 | `next typegen` 与 `tsc --noEmit` exit code 0 |
| Chrome 干净新建页 | 通过 | 初始仅邮件 HTML；增加其余渠道后六套确认内容自动带入，预览无应用错误，未保存 |
| Web 全量 ESLint | 基线失败 | 本次文件无错误；工作区其他 APM、Log、Monitor、System Manager 文件已有 38 个错误，本次未扩大范围修复 |

### 3.2 2026-09-10 告警操作通知内容改版实施

| 检查 | 结果 | 证据 |
|---|---|---|
| 告警操作模板最终聚焦回归 | 通过 | 88 passed in 3.34s |
| 模板及受影响生命周期完整回归 | 通过 | 190 passed in 6.01s |
| 告警操作默认邮件 API 预览 | 通过 | 标题、操作说明、待响应状态和 HTML 结构均成功渲染，无缺失变量 |
| 操作变量作用域 | 通过 | 普通模板使用操作变量返回 400；操作模板四个变量均正常渲染 |
| 存量默认升级 | 通过 | 旧默认内容升级到新版且 revision 递增；修改过的用户内容不覆盖；升级和页面编辑共用行锁 |
| 人工分派与转派 | 通过 | 唯一渠道、执行人、原处理人、新处理人和本地操作时间进入模板，操作者也是接收人时仍通知 |
| Web 通知模板相关回归 | 通过 | 5 files、12 tests passed |
| 后端 Flake8 / Web 目标 ESLint | 通过 | exit code 0 |
| Web TypeScript | 通过 | `next typegen` 与 `tsc --noEmit` exit code 0 |

Chrome 已确认“通知模板”入口、内置标识、唯一渠道选择、编辑入口和删除禁用状态。当前 API 由 PyCharm 以 `runserver --noreload` 启动，仍返回改动前的旧正文；新版内容、操作变量和存量自动升级的浏览器检查需在该进程重启后继续。检查过程未保存页面内容，也未触发真实测试发送。真实邮件、机器人和 OpsPilot 的最终外部呈现仍按第 5 节在受控渠道验收。

### 3.3 2026-09-10 真实告警测试发送

| 检查 | 结果 | 证据 |
|---|---|---|
| 草稿试发 API | 通过 | 新建和编辑均提交当前标题、正文、渠道类型、渠道 ID 和真实告警 ID，无需先保存 |
| 告警数据、接收人与组织边界 | 通过 | 真实告警和多选接收人进入渲染；重复接收人去重；不存在的接收人及跨团队告警返回 400；后端视图 22 tests passed |
| 通知模板与生命周期回归 | 通过 | 132 tests passed |
| Web 试发交互 | 通过 | 新建页入口、真实告警与接收人选择及草稿参数提交；通知模板相关 6 files、20 tests passed |
| 后端 Flake8 / Web 目标 ESLint | 通过 | exit code 0 |
| Web TypeScript | 通过 | `next typegen` 与 `tsc --noEmit` exit code 0 |

Chrome 已确认试发弹窗默认选中当前用户，接收人下拉可检索并追加其他用户，且保留真实告警和渠道选择。不执行最终“确定”按钮，避免向真实邮件或机器人渠道产生未经确认的外部消息。

## 4. 部署前人工验收

至少准备一个测试用户、一个邮件渠道、一个企业微信机器人渠道，并使用不含生产敏感信息的测试告警。

1. 进入“告警中心 → 配置 → 通知模板”，确认权限控制、空态、使用状态和“去告警分派”入口；
2. 新建一个模板组，确认默认只包含邮件 HTML；再增加企业微信 Markdown，并分别插入告警标题、内容、级别和时间变量；
3. 切换两种通知方式，确认各自内容保持；检查宽屏双栏和窄屏上下布局；
4. 输入脚本、事件属性、危险 URL、标题换行和非法模板表达式，确认保存/预览被拒绝；
5. 在新建页先不保存，选择一条当前团队告警、一个或多个测试接收人和邮件渠道试发；修改正文但仍不保存，再选择企微渠道试发，确认两次分别使用各自渠道版本、当前编辑内容和所选接收人；
6. 检查邮件主题、HTML 结构和动态值；检查企微标题、引用、加粗和换行；确认正文没有系统追加的接收人行；
7. 在分派策略同时选择邮件与企微渠道，分别为两个渠道的默认、提醒、升级和恢复选择模板组并保存；
8. 依次触发自动分派、提醒、升级和恢复，确认每个场景取得对应模板，并各自按渠道取得 HTML 或 Markdown；
9. 在活动升级任务存在时修改策略，确认旧任务仍用原快照，新任务使用新绑定；
10. 尝试删除正在引用的模板，确认返回引用冲突；解绑并终止活动任务后可删除；
11. 让一个机器人渠道发送失败，确认邮件仍成功且只重试失败渠道；
12. 用无权组织用户直接访问模板 ID、渠道 ID 和引用接口，确认不泄露正文或引用来源。

已在用户当前 Chrome 会话完成模板入口、新增、格式切换、服务端预览、保存和编辑回显。本轮恢复按渠道、按场景绑定交互：邮件提醒与企业微信恢复分别选择模板后提交成功，再次编辑能够逐项回显。模板编辑在详情返回前禁用保存、预览和试发，加载后修改成功。已绑定模板删除按钮禁用；另建一次性未绑定模板完成真实删除，页面提示“删除成功”且列表记录消失。

## 5. 待补验证

| 项目 | 环境 | 通过标准 |
|---|---|---|
| 真实邮件/企微效果 | 预发布受控渠道 | HTML、Markdown、主题、接收人和换行与预览一致 |
| 钉钉、飞书、Webhook、OpsPilot | 各自可用测试渠道 | 格式和底层协议均符合渠道实际限制 |
| PostgreSQL 迁移 | 预发布数据库副本 | `0030` 成功执行，约束和索引存在，旧策略无需回填 |
| PostgreSQL 并发 | 事务测试环境 | 同范围并发同名只有一个成功；revision 并发更新只有一个成功 |
| 菜单权限初始化 | 完整初始化环境 | View/Add/Edit/Delete/Test 与页面、API 一致 |
| 浏览器视觉 | 1440/1024/736/360，亮暗主题 | 无遮挡、溢出、主题硬编码或不可达操作 |
| 告警操作内置模板浏览器闭环 | 当前部署迁移并重启 API/Worker 后 | 当前团队仅一条内置模板；单选渠道；可改内容；删除禁用；人工分派与转派按所选渠道入队 |

真实渠道验收不得在自动化中写入 Webhook、SMTP 密码、Token、私人消息正文或生产告警 payload。
