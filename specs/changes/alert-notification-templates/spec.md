# 告警中心自定义通知模板实施文档

状态：第一版已完成开发、本地自动化和浏览器配置闭环验证；告警操作通知内容改版与普通模板六渠道默认内容均已确认并实施。

日期：2026-09-09，内容方案补充：2026-09-10。

## 1. 目标与第一版边界

告警中心允许用户在页面维护可复用的通知模板组，并在告警分派策略中按通知渠道和生命周期场景选择模板组。模板组内按通知方式维护对应格式，发送时由 Alerts 根据实际渠道自动选择邮件 HTML、机器人 Markdown 等版本，填充告警变量并生成最终内容；SystemMgmt 继续负责渠道连接、认证、接收人解析及外部协议包装。

第一版覆盖单告警生命周期的四个场景：

- 告警分派 `assignment`
- 告警提醒 `reminder`
- 告警升级 `escalation`
- 告警恢复 `recovery`

第一版不改变相关性规则中的 `params.alert_template`。该字段负责生成告警事实，本功能只控制事实生成后的通知表现，不会写回 `Alert.title`、`Alert.content`、Event、聚合维度或告警状态。

未分派告警汇总仍沿用原有固定内容。数据模型和渲染器保留了 `unassigned_summary` 范围，供后续接入；本版页面固定创建 `single_alert` 模板，`UnDispatchService` 未接入自定义模板。

## 2. 产品与页面设计

在告警中心“配置”二级导航中新增“通知模板”页签，位置在“告警分派”之后。模板使用独立列表页和编辑页，不塞入“全局配置”，原因是它具有独立的增删改查、权限、组织范围、版本和引用关系。一个普通模板组代表一种业务用途，例如“生产严重告警”；组内可按需包含邮件 HTML、企业微信 Markdown 等多个渠道版本。告警分派策略才是选择模板组并让它生效的入口，列表页说明使用同一示例串起这三层关系。

列表页提供：

- 名称搜索、分页、新建、编辑、删除和“去告警分派”入口；
- 展示模板组名称、包含的渠道版本、适用范围、已绑定分派策略数和更新时间；
- 全局模板只读；服务端提供复制到当前团队的 API，页面复制入口列入后续交互完善；
- 被分派策略或活动升级任务引用的模板不可删除。

编辑页采用响应式双栏：宽屏左侧编辑、右侧预览；窄屏上下排列。页面能力包括：

- 新建时默认只选择邮件 HTML，避免无意创建六份渠道内容；用户可按需增加一个或多个渠道版本，每种版本保存独立标题和正文；
- 新增渠道版本时带入可直接使用的业务默认内容：标题体现通知场景、告警级别和告警标题，正文包含资源、监控来源、指标、发生时间、告警内容、告警 ID 和本次接收人；邮件使用结构化 HTML，机器人使用各自 Markdown，Webhook 与 OpsPilot 使用文本；
- 基本信息区解释“模板组—渠道版本—分派策略”的关系，编辑区明确显示当前正在编辑的渠道及格式；
- 配置导航名称为“通知模板”；编辑页返回按钮带明确目标文案，告警操作模板页头直接展示模板名称、内置标识和用途说明；
- 按方式切换 Ace Editor 的 HTML、Markdown 或 Text 模式；
- HTML 默认正文使用多行缩进源码并开启编辑器自动换行；已生成的一行式告警操作默认正文会在编辑时无损转换为多行源码；
- 点击变量标签插入变量；
- 350ms 防抖调用服务端预览，旧响应不会覆盖新内容；
- HTML/Markdown 预览经过 DOMPurify，并放入带 CSP 的 sandbox iframe；
- 预览区高度随视口在 520px 到 800px 之间调整，长内容在独立预览区内滚动；
- 保存已有模板时携带 `revision`，并发覆盖返回 409；
- 新建和编辑模板时都保留“测试发送”；用户必须从当前团队可见的告警中选择一条真实告警，再选择与模板渠道版本匹配且有权使用的具体通知渠道；
- 测试接收人支持多选并默认带入当前用户；后端解析并校验所有用户名，拒绝空列表和不存在的用户，重复用户名按首次出现顺序去重；
- 试发使用编辑器中的当前标题和正文，允许在保存前验证新建模板或尚未保存的修改，不创建临时模板，也不修改所选告警状态；邮件等定向渠道发送给所选用户，群机器人发送到所选群并使用所选用户填充接收人模板变量。

每个团队同时拥有一个系统自动建立的“告警操作通知”模板。它与用户新建的业务模板组分开，专门用于没有分派策略上下文的人工分派和转派：

- 模板名称、用途、组织和适用范围固定，不能删除、复制或绑定到分派策略；
- 只能选择一个具体通知渠道，并只保存与该渠道类型匹配的一份 HTML、Markdown 或 Text 内容；
- 用户可以切换这一具体渠道，也可以修改标题和正文；测试发送固定使用已选渠道；
- 所选渠道被删除、失效或不再属于当前团队时不静默切换到其他渠道，人工操作照常完成并记录通知未发送；
- 列表只展示当前团队的这一条内置模板，切换团队后分别维护各自配置。

告警分派编辑抽屉按已选通知渠道展示模板绑定卡片，每个渠道分别提供“默认（首次分派）、提醒、升级、恢复”四个场景。每个选择框只展示包含当前渠道版本的模板组，例如邮件渠道只展示带邮件 HTML 版本的模板组。场景未选择时继承当前渠道的默认绑定；默认绑定也未选择时使用系统默认内容。升级层使用同一渠道 ID 时继承策略顶层绑定。

## 3. 通知方式与格式

第一版按当前告警中心实际可发送的渠道支持六种格式：

| 渠道类型 | 页面格式 | 标题 | 底层职责 |
|---|---|---|---|
| `email` | HTML | 必填 | SMTP、邮箱解析、MIME `text/html` 包装 |
| `enterprise_wechat_bot` | Markdown | 无独立标题 | Webhook 与企微消息外壳 |
| `dingtalk_bot` | Markdown | 必填 | Webhook、签名与钉钉消息外壳 |
| `feishu_bot` | Markdown | 必填 | 固定卡片结构、Webhook 与签名 |
| `custom_webhook` | Text | 无独立标题 | 渠道自己的请求体 `body_template` 与认证 |
| OpsPilot 托管 `nats` | Text | 无独立标题 | `message/team/user_ids` 协议包装 |

普通内部 NATS 和 `enterprise_wechat` 应用消息不出现在模板绑定候选中。只有 `config.source == "opspilot"` 的 NATS 渠道允许绑定和试发。

告警模板和自定义 Webhook 的 `body_template` 是两层契约：Alerts 先把 `{{ alert.* }}` 渲染成业务正文，SystemMgmt 再把该正文写入 Webhook 的 `{{content}}`。模板引擎不接管请求结构、密钥或签名。

## 4. 数据模型

迁移 `alerts.0030_notification_templates` 新增三张表：

### 4.1 `NotificationTemplate`

- `name`、`description`：模板元数据；
- `team`：组织范围，保存时去重、转整数并排序；
- `scope_key`：组织集合 SHA-256 唯一键，避免 JSON 排列顺序绕过同范围同名约束；
- `scope`：当前页面使用 `single_alert`；`unassigned_summary` 为后续预留；
- `is_global`、`builtin_key`：全局及内置模板的稳定标识；普通内置模板只读，告警操作内置模板按受限字段编辑；
- `alert_operation`、`channel_id`：团队内置告警操作模板及其唯一具体渠道；
- `revision`：更新乐观锁版本。

数据库约束保证同一组织范围、同一适用范围内名称唯一，以及非空 `builtin_key` 唯一。

### 4.2 `NotificationTemplateContent`

每个模板按 `channel_type` 保存一份 `subject_template` 和 `body_template`，并以 `(template, channel_type)` 唯一。保存时主表和所有渠道内容处于同一事务。

### 4.3 `NotificationTemplateReference`

引用索引用于保护正在使用的模板：

- 分派策略保存后同步 `source_type=assignment` 引用；
- 创建升级任务时把实际层级渠道及模板绑定冻结到任务快照，并同步 `source_type=escalation_task` 引用；
- 升级任务停止、到达终态或清理时释放快照引用；
- 删除模板前最多返回 100 条引用详情；全局模板对非超级管理员只返回引用数量，避免跨组织信息泄露。

## 5. 配置契约与选择规则

页面按渠道和场景保存模板组 ID。绑定仍保存在现有渠道对象中，以兼容旧配置和已入队通知快照：

```json
{
  "id": 7,
  "name": "生产邮件",
  "channel_type": "email",
  "notification_templates": {
    "default": 11,
    "reminder": 12,
    "escalation": 13,
    "recovery": 14
  }
}
```

运行时选择规则：

1. 场景键存在且值为模板 ID：使用该模板；
2. 场景键存在且值为 `null`：显式使用系统默认内容；
3. 场景键缺失：继承当前渠道的 `default`；
4. `default` 也缺失：使用系统默认内容；
5. 升级层渠道先按相同渠道 ID 继承策略顶层绑定，再由层级自己的绑定覆盖；
6. 渠道 ID、类型、组织范围、NATS 来源和模板渠道内容均以数据库可信数据校验，不信任前端提交的名称或类型。

第一版页面暴露渠道级和场景级覆盖。只配置 `default` 时，提醒、升级和恢复自然复用该模板组；配置具体场景后，该场景使用覆盖模板。模板可使用 `notification.scene_name` 显示当前通知阶段。

运行时若模板被异常删除、组织不匹配或渲染失败，仅该渠道回退到既有固定格式。分派、提醒、升级或恢复的主业务状态不会因此回滚。成功渲染后，模板 ID、revision、场景和缺失字段写入 Outbox 参数快照，后续重试使用已入队内容，不重新读取模板。

自定义模板调用底层发送时设置 `append_receivers=false`，防止机器人渠道再次把接收人文本追加到用户正文；实际接收人参数仍完整传递。未绑定模板的旧调用保持原行为。

## 6. 生命周期接入

| 入口 | 场景 | 行为 |
|---|---|---|
| 自动分派 | `assignment` | 使用命中分派策略的顶层渠道和模板绑定 |
| 人工分派 | `assignment` | 使用告警所属团队的“告警操作通知”内置模板及其唯一渠道；执行人也是接收人时仍发送 |
| 人工转派 | `reassignment` | 使用同一内置模板和唯一渠道，场景名称渲染为“告警转派” |
| 周期提醒 | `reminder` | 使用当前有效接收人；渠道来自活动升级层快照或策略默认配置 |
| 告警升级 | `escalation` | 使用任务创建时冻结的层级渠道和模板绑定 |
| 告警恢复 | `recovery` | 通过既有提醒任务关联定位分派策略并应用恢复绑定 |

通知仍通过现有 `AlertNotificationOutbox` 和渠道级 `AlertNotificationDelivery` 投递、领取租约、失败退避与终态记录。模板功能没有新建发送队列，也不绕过原有告警 gating。

## 7. API 与权限

路由前缀：`/api/v1/alerts/api/notification_templates/`。

| API | 权限 | 说明 |
|---|---|---|
| `GET /`、`GET /{id}/` | `notification_templates-View` | 组织范围列表与详情 |
| `POST /` | `notification_templates-Add` | 当前团队创建模板 |
| `PUT/PATCH /{id}/` | `notification_templates-Edit` | 带 revision 更新；普通内置/全局不可改，告警操作内置模板仅可改渠道和内容 |
| `DELETE /{id}/` | `notification_templates-Delete` | 有引用、全局或内置模板拒绝 |
| `POST /preview/` | `notification_templates-View` | 使用内置或有界 sample 渲染，不发送 |
| `GET /options/` | View 或 `alert_assign-View` | 最多 200 条可用摘要，可按渠道类型过滤 |
| `GET /catalog/` | `notification_templates-View` | 返回可插入变量目录 |
| `GET /{id}/references/` | `notification_templates-View` | 分页查看引用，page_size 最大 100 |
| `POST /{id}/copy/` | `notification_templates-Add` | 复制到当前团队；告警操作内置模板不可复制 |
| `POST /test_send/` | View + Test + Alarms View | 使用当前编辑内容、真实告警和 1～50 个所选接收人同步试发；无需先保存模板 |
| `POST /{id}/test_send/` | View + Test + Alarms View | 已保存模板兼容试发接口；新版页面统一使用当前编辑内容接口 |

菜单和操作权限登记在 `server/support-files/system_mgmt/menus/alarm.json`，前端按钮继续使用现有 `PermissionWrapper`。

列表与详情响应包含 `assignment_count`，按不同分派策略 ID 去重计数。同一策略在多个渠道或多个场景引用同一模板组只计一次；活动升级任务的运行快照不计入该字段。

## 8. 受限模板语言与安全边界

模板只支持 `{{ path.to.value }}`，不使用 Jinja，不支持表达式、属性调用、循环、条件、过滤器、私有字段或模板注释。

可用根变量：

- `alert`：标题、内容、级别、状态、来源、资源、时间、负责人和组织；其中 `alert.level` 是按告警级别配置映射后的展示名称（如“警告”），`alert.level_id` 保留原始级别 ID；
- `labels`、`dimensions`、`enrichment`：告警已有结构化数据；
- `notification`：场景、场景名称、本次接收人和生成时间；`notification.receiver_names` 是用于正文展示的顿号分隔名称，`notification.receivers` 保留原始列表；
- `summary`：仅为后续汇总范围预留，单告警模板禁止使用。

`notification.action_summary`、`notification.actor_name`、`notification.previous_receiver_names` 和
`notification.action_time` 仅允许在 `alert_operation` 告警操作模板中使用，普通单告警模板即使手工输入也会被服务端拒绝。

缺失变量渲染为 `—` 并返回 `missing_fields`。变量值不会再次作为模板解析。

资源上限：模板 64KB、最多 200 个变量、单值 64KB、集合最多 100 项、嵌套最多 6 层、输出 256KB、标题 200 字符。标题源和渲染值均禁止 CR/LF。

邮件 HTML 禁止脚本、iframe、表单、事件属性、危险 URL、外部资源和危险 CSS；变量只能出现在文本位置，并在替换时 HTML 转义。Markdown 动态值转义语法字符并中和 `@all` 类提及。日志只记录对象、渠道、模板和错误类型等有界诊断字段，不记录模板正文、告警 payload、凭据或外部响应正文。

2026-09-11 审查修复：模板列表在初始化或升级内置模板前先验证当前团队；编辑/删除不可见或已删除模板返回 404。
邮件变量校验覆盖标签名、属性名、注释及未闭合标签；仅保留静态安全超链接，拒绝资源加载属性和 CSS 转义/注释混淆。
当前内置模板仅使用文本变量、表格和普通行内样式，继续兼容；不合规存量模板在运行时沿既有降级流程使用默认通知，编辑后需重新通过校验。
升级任务直接删除或随策略/告警级联删除时，在同一事务中释放其快照引用；删除回滚时引用一并恢复。
本次修复无数据库迁移，需同步部署 Alerts API 与通知 Worker；回滚修复会重新开放上述校验缺口。

## 9. 系统管理底层兼容

SystemMgmt 没有对告警通知模板施加业务格式限制，本次也不在该模块增加模板库。改动只扩展了两个兼容参数/查询能力：

- `send_msg_with_channel(..., append_receivers=True)`：默认值保证所有旧调用行为不变；Alerts 自定义模板显式传 `false`；
- `search_opspilot_nats_channels(...)`：只返回 OpsPilot 托管 NATS，并按请求组织在应用层过滤，兼容 PostgreSQL 和 SQLite 测试环境。

共享的 `dispatch_notification`、渠道连通测试、自定义 Webhook 请求体、SMTP/机器人协议均保持现有契约。详细代码探索记录见 [channel-analysis.md](./channel-analysis.md)。

## 10. 迁移、发布与回滚

发布顺序：

1. 执行 `alerts.0030_notification_templates`、`0031_alert_push_source_ids` 和 `0032_notification_template_operation`；
2. 初始化新增菜单及 View/Add/Edit/Delete/Test 权限；
3. 部署兼容 `append_receivers` 的 SystemMgmt/RPC；
4. 部署 Alerts 服务与 Worker；
5. 部署 Web；
6. 用受控邮件和机器人渠道完成真实效果验收。

旧分派策略没有 `notification_templates` 字段时自动走固定内容，不需要数据回填。回滚 Web 或 Alerts 前应先停止创建新模板绑定，并等待新版本入队通知完成；数据库表可保留，不影响旧代码读取策略 JSON。

## 11. 告警操作通知内容改版（已确认并实施）

2026-09-10 已按本节标题、正文和存量升级规则完成服务端、页面默认值与人工分派/转派通知链路实施。
邮件 HTML 采用多行结构化源码，机器人使用 Markdown，Webhook 与 OpsPilot 使用纯文本；页面切换唯一渠道时带入相应新版默认值。

“告警操作通知”继续保持团队内置、不可删除、只能选择一个具体渠道、允许修改标题和正文的产品约束。它的业务范围明确为：没有有效分派策略上下文时，人工分派或人工转派成功后，通知新的处理人认领告警。自动分派继续使用分派策略所选渠道及模板；认领、关闭和解决当前不触发该内置模板。

### 11.1 标题口径

有独立标题的渠道使用：

```text
【{{ notification.scene_name }}】【待认领】【{{ alert.level }}】{{ alert.title }}
```

示例：

```text
【告警分派】【待认领】【严重】CPU 使用率过高
【告警转派】【待认领】【严重】CPU 使用率过高
```

企业微信机器人等没有独立标题的渠道，在正文首行使用相同语义的 Markdown 标题。

### 11.2 正文信息结构

各渠道保持相同业务信息，仅分别使用邮件 HTML、机器人 Markdown 或纯文本格式：

```text
该告警已由 admin 从 lisi 转派给 zhangsan，请新的处理人及时认领并处理。

操作信息
操作类型：告警转派
操作人：admin
当前处理人：zhangsan
操作时间：2026-09-10 11:30:00
当前状态：待响应

告警信息
告警标题：CPU 使用率过高
告警级别：严重
告警资源：生产主机 01（host）
监控来源：Prometheus / cpu_usage
发生时间：2026-09-10 11:25:00

告警内容
CPU 使用率已达到 95%，并持续 5 分钟。

告警 ID：ALERT-20260910-001

请进入告警中心认领并处理该告警。
```

普通分派时首句改为“该告警已由 admin 分派给 zhangsan，请及时认领并处理”。模板语言不支持条件判断，因此默认正文使用服务端生成的 `notification.action_summary` 表达分派或转派差异，避免普通分派出现无意义的“原处理人：—”。

### 11.3 新增操作上下文变量

| 变量 | 含义 | 默认正文是否使用 |
|---|---|---|
| `notification.action_summary` | 按分派/转派、执行人、原处理人和新处理人生成完整操作说明 | 是 |
| `notification.actor_name` | 执行人工分派或转派的用户；系统身份显示为“系统” | 是 |
| `notification.previous_receiver_names` | 转派前处理人；普通分派为空 | 否，供用户自定义 |
| `notification.action_time` | 本次人工操作时间 | 是 |

实施时只向告警操作通知传入这些字段，不改变普通模板的生命周期场景。服务端变量白名单和页面变量目录同步增加对应条目。

### 11.4 存量升级规则

- 新团队首次建立告警操作通知时直接使用新版内容；
- 已存在模板的标题和正文同时等于旧内置默认值时，视为未编辑，可安全升级为新版；
- 任一字段已经被用户修改，则保留整份用户内容，不做局部覆盖；
- 切换唯一渠道时，使用该渠道对应的新版默认内容作为初始值；
- 升级不改变模板 ID、团队、所选渠道、revision 语义和历史 Outbox 快照。

存量升级和页面编辑共用模板主表行锁，并在更新正文时再次匹配旧标题与旧正文，避免并发编辑被自动升级覆盖；只有实际替换旧默认内容时 revision 才递增。

## 12. 新建普通模板的六渠道默认内容（已确认并实施）

2026-09-10 已在 Chrome 新建页面中使用统一测试告警逐个展示邮件 HTML、企业微信 Markdown、钉钉 Markdown、飞书 Markdown、自定义 Webhook 文本和 OpsPilot 文本，用户确认采用本节标题和正文作为新建普通模板的默认内容。该决定只影响后续新建页面带入的初始值，不回写或覆盖已保存模板。

本节记录用户点击“新建”普通通知模板时由页面带入的渠道版本默认值。普通模板可绑定告警分派、提醒、升级和恢复四个场景，因此已确认内容突出 `notification.scene_name`，不写死“待认领”或具体处置动作。用户新建模板时默认只选择邮件 HTML；其他五种内容在用户增加对应渠道版本时带入。

### 12.1 邮件 HTML

实施前标题：

```text
【{{ notification.scene_name }}】【{{ alert.level }}】{{ alert.title }}
```

实施前正文包含通知场景、告警标题，以及告警级别、资源、监控来源、发生时间、本次接收人组成的表格；表格后展示告警内容和告警 ID。

已确认标题：

```text
【{{ notification.scene_name }}·{{ alert.level }}】{{ alert.title }}（{{ alert.resource_name }}）
```

已确认正文：

```html
<div style="font-family:Arial,sans-serif;color:#1f2937;line-height:1.6;">
  <div style="padding:16px;background:#f5f7fa;border-radius:6px;">
    <div style="font-size:13px;color:#6b7280;">{{ notification.scene_name }}</div>
    <h2 style="margin:4px 0 0;font-size:20px;">{{ alert.title }}</h2>
  </div>
  <table style="width:100%;margin-top:16px;border-collapse:collapse;">
    <tr><td style="width:96px;padding:8px;border:1px solid #e5e7eb;">告警级别</td><td style="padding:8px;border:1px solid #e5e7eb;"><strong>{{ alert.level }}</strong></td></tr>
    <tr><td style="padding:8px;border:1px solid #e5e7eb;">告警资源</td><td style="padding:8px;border:1px solid #e5e7eb;">{{ alert.resource_name }}（{{ alert.resource_type }}）</td></tr>
    <tr><td style="padding:8px;border:1px solid #e5e7eb;">资源 ID</td><td style="padding:8px;border:1px solid #e5e7eb;">{{ alert.resource_id }}</td></tr>
    <tr><td style="padding:8px;border:1px solid #e5e7eb;">监控来源</td><td style="padding:8px;border:1px solid #e5e7eb;">{{ alert.source_name }}</td></tr>
    <tr><td style="padding:8px;border:1px solid #e5e7eb;">监控指标</td><td style="padding:8px;border:1px solid #e5e7eb;">{{ alert.item }}</td></tr>
    <tr><td style="padding:8px;border:1px solid #e5e7eb;">发生时间</td><td style="padding:8px;border:1px solid #e5e7eb;">{{ alert.created_at }}</td></tr>
    <tr><td style="padding:8px;border:1px solid #e5e7eb;">本次接收人</td><td style="padding:8px;border:1px solid #e5e7eb;">{{ notification.receiver_names }}</td></tr>
  </table>
  <div style="margin-top:16px;padding:12px;background:#f9fafb;border-left:4px solid #9ca3af;">
    <strong>告警内容</strong><br>
    {{ alert.content }}
  </div>
  <p style="margin-top:12px;color:#6b7280;font-size:12px;">告警 ID：{{ alert.alert_id }}｜通知时间：{{ notification.generated_at }}</p>
</div>
```

确认理由：邮件主题加入资源名称，正文把监控来源和监控指标拆开，并补充资源 ID 与通知生成时间，便于邮件检索和跨系统定位。

### 12.2 企业微信机器人 Markdown

实施前无独立标题。实施前正文以“通知场景｜告警标题”为三级标题，引用区展示级别、资源、来源和时间，随后展示告警内容、告警 ID 和接收人。

已确认标题：无独立标题，由正文首行承担标题语义。

已确认正文：

```markdown
### {{ notification.scene_name }}｜{{ alert.level }}

**{{ alert.title }}**

> {{ alert.content }}

- **告警资源：** {{ alert.resource_name }}（{{ alert.resource_type }}）
- **监控来源：** {{ alert.source_name }}
- **监控指标：** {{ alert.item }}
- **发生时间：** {{ alert.created_at }}
- **本次接收人：** {{ notification.receiver_names }}

告警 ID：{{ alert.alert_id }}
通知时间：{{ notification.generated_at }}
```

确认理由：企业微信主要在移动端查看，先展示级别、标题和内容，再展示定位字段，减少首屏被表格式信息占满。

### 12.3 钉钉机器人 Markdown

实施前标题：

```text
【{{ notification.scene_name }}】【{{ alert.level }}】{{ alert.title }}
```

实施前正文使用三级标题，依次展示级别、资源、来源、时间、告警内容、告警 ID 和接收人。

已确认标题：

```text
【{{ notification.scene_name }}·{{ alert.level }}】{{ alert.title }}
```

已确认正文：

```markdown
### {{ notification.scene_name }}｜{{ alert.title }}

> **{{ alert.level }}**｜{{ alert.resource_name }}（{{ alert.resource_type }}）

**告警内容**

> {{ alert.content }}

- **监控来源：** {{ alert.source_name }}
- **监控指标：** {{ alert.item }}
- **发生时间：** {{ alert.created_at }}
- **本次接收人：** {{ notification.receiver_names }}

告警 ID：{{ alert.alert_id }}
通知时间：{{ notification.generated_at }}
```

确认理由：标题保持短小，正文首屏把级别和资源放在同一行，适合钉钉机器人卡片快速浏览。

### 12.4 飞书机器人 Markdown

实施前标题：

```text
【{{ notification.scene_name }}】【{{ alert.level }}】{{ alert.title }}
```

实施前正文以加粗文本展示场景和标题，随后展示级别、资源、来源、时间、告警内容、告警 ID 和接收人。

已确认标题：

```text
【{{ notification.scene_name }}·{{ alert.level }}】{{ alert.title }}
```

已确认正文：

```markdown
**{{ notification.scene_name }}｜{{ alert.title }}**

**告警级别：** {{ alert.level }}
**告警资源：** {{ alert.resource_name }}（{{ alert.resource_type }}）
**监控来源：** {{ alert.source_name }}
**监控指标：** {{ alert.item }}
**发生时间：** {{ alert.created_at }}
**本次接收人：** {{ notification.receiver_names }}

**告警内容**

> {{ alert.content }}

告警 ID：{{ alert.alert_id }}
通知时间：{{ notification.generated_at }}
```

确认理由：保持飞书卡片的紧凑键值布局，同时把告警内容独立成块，避免正文与字段混在一起。

### 12.5 自定义 Webhook 文本

实施前无独立标题。实施前正文按行展示通知场景、级别、标题、内容、资源、监控来源、发生时间、告警 ID 和接收人。

已确认标题：无独立标题。

已确认正文：

```text
[告警通知]
通知场景：{{ notification.scene_name }}
告警级别：{{ alert.level }}
告警标题：{{ alert.title }}
告警 ID：{{ alert.alert_id }}
告警资源：{{ alert.resource_name }}（{{ alert.resource_type }}）
资源 ID：{{ alert.resource_id }}
监控来源：{{ alert.source_name }}
监控指标：{{ alert.item }}
发生时间：{{ alert.created_at }}
本次接收人：{{ notification.receiver_names }}
通知时间：{{ notification.generated_at }}

告警内容：
{{ alert.content }}
```

确认理由：保持纯文本契约，不默认生成可能被动态内容破坏的 JSON；字段顺序稳定，方便下游日志检索。Webhook 请求结构和认证仍由系统管理渠道配置负责。

### 12.6 OpsPilot 文本

实施前无独立标题。实施前正文以 `[通知场景][告警级别] 告警标题` 开头，随后展示资源、来源、内容、时间、告警 ID 和接收人。

已确认标题：无独立标题。

已确认正文：

```text
[WeOps 告警通知]
通知场景：{{ notification.scene_name }}
告警级别：{{ alert.level }}
告警标题：{{ alert.title }}

定位信息：
- 告警 ID：{{ alert.alert_id }}
- 告警资源：{{ alert.resource_name }}（{{ alert.resource_type }}）
- 资源 ID：{{ alert.resource_id }}
- 监控来源：{{ alert.source_name }}
- 监控指标：{{ alert.item }}
- 发生时间：{{ alert.created_at }}
- 本次接收人：{{ notification.receiver_names }}

告警内容：
{{ alert.content }}
```

确认理由：OpsPilot 收到的是 `message/team/user_ids` 协议中的文本消息，确认内容提供稳定的定位字段和清晰分段，不在模板中加入自动执行指令。

### 12.7 六渠道共同约束

- 有标题能力的邮件、钉钉和飞书分别保存独立标题；企业微信、Webhook 和 OpsPilot 不伪造独立标题字段；
- 默认内容只使用单告警范围已允许的变量，不依赖循环、条件或过滤器；
- `alert.level` 使用级别展示名称，`alert.level_id` 仅在用户确有原始值需求时自行插入；
- 页面变量入口包含 `notification.generated_at`、`alert.resource_id`，两者已在服务端模板白名单中；
- 四个生命周期场景共用同一渠道版本时，由 `notification.scene_name` 分别渲染为告警分派、告警提醒、告警升级或告警恢复；
- 用户调整后的标题和正文属于其模板内容，后续默认值升级不得覆盖已经保存的普通模板。

## 13. 已知限制与后续项

- 未分派汇总模板、系统全局配置绑定和汇总变量尚未接入；
- 测试发送是同步调用，没有独立试发任务、共享限流或幂等查询接口；下拉首版加载当前团队最近 50 条可见告警并在前端检索；
- 页面没有“离开未保存”确认、光标位置变量插入和完整 Storybook 场景；
- 本地自动化未连接真实 SMTP、企微、钉钉、飞书、Webhook 或 OpsPilot；
- 同名并发约束已落数据库，PostgreSQL 下真正的并发竞争仍需在 CI 或预发布环境验证。

以上项目不影响第一版核心验收：用户可在模板组中为不同通知方式维护对应格式，在分派策略中按渠道和场景选择模板组，四个单告警生命周期自动按实际渠道取对应版本，并继续走既有可靠投递链路与默认回退。
