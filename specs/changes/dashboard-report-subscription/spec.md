# 仪表盘报告订阅 MVP

Status: in_progress

## Phase 1A 实现状态（2026-07-28）

已实现且验证：

- `DashboardReportSubscription` 配置模型及 migration；
- 当前用户自己的订阅 CRUD API；
- 创建、更新时复用 Dashboard `View` 实例权限；
- 删除仅要求创建者身份，不因 Dashboard 权限变化而阻断；
- `active` / `paused` 对外状态，`terminated` 仅保留为后续删除联动语义；
- Dashboard 内报告订阅入口，以及创建、列表、编辑、删除交互；
- DRF API 与 Dashboard Subscription Modal 用户行为回归测试。

本阶段明确未实现：Execution、Schedule、Scheduler、PDF、Chromium Worker、
Email Delivery、Retry、Render Token 与 Snapshot。后续章节描述完整 MVP
目标，不代表这些能力已在 Phase 1A 落地。

已知边界：Phase 1A 在 Model 校验和 CRUD 序列化边界禁止写入
`active + dashboard=null`，但按本阶段约束不实现 Dashboard 删除联动。
因此 Dashboard 的 `SET_NULL` 删除路径在 Phase 1B 接入 Execution 前仍需补充
将关联订阅终止为 `terminated` 的事务性处理。

## Phase 1B-1 实现状态（2026-07-28）

已实现且验证：

- `DashboardReportExecution` 基础模型及 migration；
- `pending/running/succeeded/failed/unknown` 状态集合与显式合法流转；
- `manual` 手动触发类型；
- Subscription detail action `POST /execute/`；
- 当前用户自己的 Execution 详情查询；
- 手动触发实时复用创建者与 Dashboard View 权限；
- Dashboard Subscription Modal 的“立即测试”入口及成功、失败反馈；
- DRF execute/retrieve API 与 Modal 用户行为回归测试。

Phase 1B-1 的同步实验执行严格经过
`pending → running → succeeded`，但不执行任何报告工作。本阶段仍未实现
Scheduler、Celery Task、PDF、Chromium Worker、Email、完整 Snapshot、Retry
或 Render Token。

## Phase 1B-2A 实现状态（2026-07-29）

已实现且验证：

- 独立的一对一 `DashboardReportExecutionSnapshot` 输入快照模型；
- 执行创建时冻结 `dashboard_id`、`subscription_id`、`creator_id` 与
  Subscription 已保存的 `config.filter_values`；
- Snapshot 创建成功后 Execution 保持 `pending`，等待后续 Worker 消费；
- Snapshot 创建失败时直接经过 `pending → failed`，并记录
  `failure_stage=snapshot`；
- Execution 详情 API 只读返回 Snapshot，后续订阅配置修改不改变已有快照；
- Snapshot 模型拒绝通过实例 `save()`、QuerySet `update()` 或
  `bulk_update()` 修改已持久化快照；
- Execution 状态转换的公开入口统一为
  `DashboardReportExecutionService.transition()`，API、未来 Task 与 Worker
  不直接赋值 `status`。

Phase 1B-2A 不从 Dashboard 页面临时 state 读取筛选值。当前 Subscription
尚未开放筛选配置写入，因此既有 Phase 1A Subscription 通常冻结空
`filter_values`；浏览器当前 applied filters、namespace、Dashboard 布局与
Widget/DataSource 配置分别留待后续 Subscription 输入和 Render Snapshot
阶段。本阶段仍未接入 Celery、Chromium、PDF、Email、Retry、Render Token、
完整权限 Snapshot 或 DataSource Runtime Snapshot。

## Problem Statement

运营分析仪表盘已经支持用户在浏览器中手工导出 PDF，但现有实现依赖当前页面 DOM、`html-to-image`、`jsPDF.save()` 和用户登录会话，只能下载到用户本机，不能由后台周期任务无会话生成并作为邮件附件发送。

用户需要为某个仪表盘配置稳定的报告订阅：系统按每天、每周或每月的计划时间，以订阅创建者的实时权限和订阅保存的筛选语义加载最新仪表盘，生成完整 PDF，并通过指定邮件渠道发送到一个邮箱。报告接收者不要求是平台用户；数据边界由创建者权限、执行时重新鉴权、完整性检查和可审计的执行记录保证。

MVP 只支持运营分析 `Dashboard`，只输出 PDF，只支持一个收件邮箱，不扩展到其他画布、其他附件格式或全局订阅中心。

## Goals

- 用户可在当前仪表盘内创建、编辑、暂停、恢复、测试和删除自己的报告订阅。
- 系统按订阅时区正确计算每日、每周和每月计划，覆盖月末回退、DST、停机补偿和编辑重排。
- 每次执行以创建者当前身份重新校验仪表盘、数据源及下游业务数据权限。
- 后台使用独立 Chromium Worker 和显式页面就绪协议生成完整 PDF。
- 任一参与报告的 Widget 权限、数据加载或渲染失败时不发送部分报告。
- 系统内部避免重复创建和重复执行，并完整记录最终状态、失败阶段、尝试次数和输入版本。
- PDF 仅在当前发送与重试窗口内临时保留；执行及 Snapshot 默认保留 180 天。

## Ubiquitous Language

| 术语 | 定义 |
| --- | --- |
| 报告订阅（Subscription） | 绑定一个 Dashboard、创建者、筛选快照、调度、邮件渠道和单个收件邮箱的持续分发规则。 |
| 订阅执行（Execution） | 一次计划执行或手工测试产生的独立生成与投递单元，是状态、幂等、重试与审计边界。 |
| Execution Input Snapshot | 执行开始时冻结的本次业务输入；后续订阅编辑不影响当前执行。 |
| Render Snapshot | 执行开始时冻结的 Dashboard 布局、Widget、数据源引用和展示配置；不是复制出来的新 Dashboard。 |
| Data Source Runtime Snapshot | 本次执行冻结的非敏感数据源运行配置及版本引用；不包含凭据或用户权限。 |
| Render Token | 每次渲染 attempt 使用的短时、一次性、仅限内部渲染会话的凭据；不是数据授权凭据。 |
| 计划执行（scheduled） | 由统一扫描器针对某个 `scheduled_time_utc` 创建的执行。 |
| 测试执行（manual_test） | 用户显式请求、基于已保存订阅创建且不影响调度计划的执行。 |
| Render Snapshot 边界 | Snapshot 成功冻结的时点；之后的 Dashboard 编辑或删除不改变当前执行输入。 |

## User Stories

1. 作为具有 Dashboard 查看权限的用户，我可以为当前仪表盘创建报告订阅，以便定期把报告发送给平台外的管理层或财务人员。
2. 作为订阅创建者，我可以固定筛选口径，同时让后续报告自动采用仪表盘最新布局与 Widget 配置。
3. 作为订阅创建者，我可以在保存订阅后手工测试发送，以便在等待下一个计划周期前验证权限、渲染和邮件配置。
4. 作为订阅创建者，我可以暂停、恢复、编辑或删除自己的订阅，并清楚看到下一次执行和最近执行结果。
5. 作为审计人员，我可以从执行记录判断某次报告使用了哪个订阅版本、画布版本、数据源版本、计划时间和创建者身份。
6. 作为平台运维人员，我可以限制 Chromium 并发、执行时长、PDF 大小、扫描批量和审计保留期，避免报告任务拖垮普通业务任务。

## Behaviour Contract

### 1. MVP 范围

- 只支持运营分析 `Dashboard`，不支持 Report、Screen、Topology、Architecture 或 NetworkTopology。
- 只生成 PDF，不生成 PNG、JPEG 或其他附件。
- 一个 Subscription 只绑定一个收件邮箱。
- 收件邮箱可以是任意合法邮箱地址，不要求属于平台用户。
- Subscription 显式绑定一个 `email_channel_id`。
- 用户不能自定义邮件标题、正文、HTML、模板变量或语言模板。
- 不提供全局订阅管理中心；所有普通用户入口均位于当前 Dashboard。

### 2. 创建与筛选快照

创建 Subscription 时必须保存：

- `canvas_id`；
- 创建者稳定身份；
- 订阅名称；
- 一个收件邮箱；
- `email_channel_id`；
- 周期类型与周期参数；
- IANA 时区；
- 当前已应用筛选条件的快照；
- 初始 `next_run_at`；
- 订阅版本。

创建时：

- 自动绑定当前 Dashboard，不允许从请求中越权绑定其他不可见 Dashboard。
- 校验创建者具备运营分析 `view-View` 功能权限，且对该 Dashboard 实例具备 `View` 权限。
- 不要求 `EditChart` 或实例 `Operate`。
- 扫描当前 Dashboard 引用的全部数据源，校验已知的 `data_source-View`、数据源实例可见性和组织范围。
- 不要求完全模拟一次报告执行；临时网络故障不能阻止保存 Subscription。
- 校验所选渠道类型为 `email`，且在当前组织范围内可用。
- 创建后只等待下一次未来计划时间，不立即补发或自动测试。

筛选快照分为：

- 静态筛选：保存具体值。
- 动态时间筛选：保存语义，例如 `last_month`、`last_7_days`，执行时按计划时间和订阅时区重新解析。

筛选条件失效时，本次执行失败，不回退 Dashboard 默认值。

### 3. 调度规则

周期只允许：

- 每天：指定时分。
- 每周：指定星期和时分。
- 每月：指定 1–31 日和时分。

不支持：

- Cron 表达式；
- 每隔 N 分钟；
- 自定义复杂周期。

每月目标日期在当月不存在时，按当月最后一天执行，不跳过。

Subscription 创建时保存 IANA 时区，之后不随用户时区变化。所有本地计划时间由标准时区库转换为 UTC：

- 春季跳时导致目标本地时间不存在时，在该日期第一个有效时间执行。
- 秋季回拨导致本地时间重复时，只在第一次出现的时间点执行。
- Execution 保存 UTC `scheduled_time`、原始本地计划时间和时区。

固定 Celery Beat 任务每分钟触发统一扫描器：

- 查询 `active`、未逻辑删除且 `next_run_at <= now` 的 Subscription。
- 不为每个 Subscription 创建独立 `PeriodicTask`。
- 使用事务、行锁和唯一约束领取计划执行。
- 成功创建 scheduled Execution 后立即推进 `next_run_at`，再异步派发执行。
- 扫描器限制每批领取数量；剩余到期 Subscription 等待后续扫描，不无限创建 `pending`。
- `batch_init` 不创建订阅任务，也不依赖 Worker、Beat、NATS 或 Chromium。

### 4. 漏执行与补偿

补偿仅适用于系统停机、调度异常或执行并发占用导致的漏执行：

- 恢复后只补最近一期。
- 更早的多个漏期不逐期补发。
- 同一计划时间最多创建一个 scheduled Execution。

以下业务失败不创建新的补偿 Execution：

- 创建者账号无效；
- Dashboard 权限失效；
- Dashboard 或数据源不存在；
- 数据源或下游业务权限失败；
- 筛选条件失效。

暂停期间不属于漏执行，不进入补偿。

### 5. 暂停、恢复与编辑

Subscription 状态：

- `active`：参与调度。
- `paused`：用户主动暂停，可恢复。
- `terminated`：源 Dashboard 删除导致终止，不可恢复。

暂停：

- 不参与调度，不创建 Execution。
- 不补发暂停期间的计划。
- 已经进入 `pending/running` 的 Execution 继续完成。
- 保存操作者、操作时间和操作类型。

恢复：

- 从恢复时刻和当前有效配置重新计算未来 `next_run_at`。
- `next_run_at` 必须晚于恢复时刻。
- 不立即执行，不补发暂停期间计划。

编辑：

- 周期、执行时间或时区变化时，旧计划立即失效，并从保存时刻重新计算未来 `next_run_at`。
- 订阅名称、收件邮箱、邮件渠道或筛选快照变化时，保留现有 `next_run_at`。
- 采用版本号和乐观锁防止并发编辑静默覆盖。
- 已进入 `pending/running` 的 Execution 使用已冻结输入，不受编辑影响。

### 6. 权限模型

MVP 不新增“仪表盘管理员”或“订阅管理员”角色。

创建者管理自己的 Subscription：

- 可以查看、停用和删除。
- 编辑或重新启用时，必须仍具备 Dashboard `View` 功能权限和实例权限。
- 失去 Dashboard `View` 后，不允许编辑或重新启用，但仍允许停用和删除。

管理他人的 Subscription：

- 仅超级用户可以。
- `EditChart + Operate` 不自动授予管理他人邮件分发配置的权限。

每次 Execution 必须实时校验创建者：

- 账号存在且有效；
- 仍具有 Dashboard `view-View` 功能权限；
- 仍具有该 Dashboard 实例 `View` 权限；
- 具有所引用数据源的功能、实例和组织权限；
- 具有各下游业务模块对实际数据查询要求的当前权限。

Execution 不使用系统账号、不回退其他用户、不使用创建时权限快照。任何权限校验失败均不生成、不发送报告。

### 7. 双 Snapshot 与执行一致性

Execution 开始时冻结 `Execution Input Snapshot`：

- `subscription_version`；
- `subscription_name`；
- `recipient_email`；
- `email_channel_id`；
- `scheduled_time_utc`（manual_test 为空）；
- 本地计划时间；
- 时区；
- `trigger_type`；
- `creator_id`；
- 筛选语义；
- 本次解析后的筛选具体值。

Execution 开始时冻结 `Render Snapshot`：

- 当前 Dashboard 布局；
- Widget 配置；
- 数据源引用；
- 展示配置；
- Dashboard `updated_at` 或版本标识；
- Snapshot 创建时间。

按 Render Snapshot 引用解析并冻结 `Data Source Runtime Snapshot`：

- `datasource_id`；
- `datasource_type`；
- 配置版本；
- 查询路径与参数定义；
- namespace 等运行引用。

任何 Snapshot 均不得保存密码、Token、Secret 或用户权限。

数据查询时：

- 根据 `creator_id` 获取当前用户上下文。
- 沿用现有 `user_info` 权限链路向下游传递当前组织、用户、权限和组织树。
- 从安全存储读取当前有效凭据。

数据源在冻结前不存在或不可访问时执行失败。冻结后修改数据源配置不影响当前执行；凭据无法取得时按 `data_load` 失败。

### 8. Dashboard 编辑与删除竞态

Render Snapshot 成功冻结是当前执行的一致性边界：

- Snapshot 冻结前 Dashboard 不存在：执行失败，不发送。
- Snapshot 冻结后 Dashboard 编辑：当前执行继续使用冻结配置，下一次执行使用新配置。
- Snapshot 冻结后 Dashboard 删除：当前执行继续生成并发送。

Dashboard 删除时：

- 所有关联、未删除 Subscription 改为 `terminated`。
- 保存终止时间和原因。
- 不再参与后续调度，且不可重新启用。
- 保留 Subscription 和 Execution 历史。

若 Dashboard 在某个 Execution 期间删除：

- Subscription 终止只影响后续计划执行。
- 当前 Execution 标记 `source_canvas_deleted_during_execution` 并继续完成。
- 不在 PDF 生成前或邮件发送前再次以 Dashboard 存在性阻断已冻结执行。

### 9. Widget 完整性

参与报告的 Widget 是最新 Render Snapshot 布局中的所有可见 Widget：

- 已删除 Widget 不参与。
- 明确隐藏的 Widget 不参与。
- 折叠状态不影响参与范围；渲染时强制加载所有可见 Widget。
- 静态 Widget 不查询数据，但必须渲染成功。

MVP 不增加关键性配置，所有参与 Widget 都是关键 Widget：

- 任一 Widget 权限失败；
- 任一 Widget 数据查询失败；
- 任一 Widget 渲染失败；
- 任一 Widget 超时；

均使整个 Execution 失败，不生成、不发送部分 Dashboard。空数据是合法业务结果，应显示正常空态并继续生成。

### 10. 显式渲染状态协议

专用内部渲染页为每个参与 Widget 维护：

- `loading`
- `ready`
- `empty`
- `failed`

页面聚合状态：

- 全部 Widget 为 `ready/empty` 时发布 `report-ready`。
- 任一 Widget 为 `failed` 时发布 `report-failed`，并提供 `widgetId`、`errorCode` 和脱敏错误信息。

Chromium Worker：

- 只等待显式页面状态。
- 收到 `report-failed` 立即失败。
- 超时仍未就绪时失败。
- 不使用固定 `sleep`、`networkidle` 或 DOM 存在性猜测完成状态。

Widget 自身负责在数据和绘制满足导出条件后声明 `ready`。MVP 不额外检测 Canvas 像素或动画。

### 11. Chromium 与 PDF

订阅渲染使用独立 Celery 队列与独立 Worker，不与普通业务任务共享资源池。

固定渲染规则：

- 亮色主题；
- 1440px 桌面视口；
- 横向 A4；
- 完整画布展开；
- 所有分组展开；
- 隐藏工具栏、筛选操作按钮、编辑控件等交互元素；
- 使用 Chromium 默认打印分页。

MVP 只保证内容完整、不丢失 Widget 内容、不因分页失败；不实现 Widget 边界分页、分组标题保持、自定义分页、页眉页脚或页码。

固定默认资源边界：

- 单次 Execution 总超时 5 分钟；
- 页面与 Widget 加载阶段最多 2 分钟；
- PDF 生成阶段最多 2 分钟；
- PDF 最大 20 MB；
- Chromium Worker 并发默认 2，可配置。

固定主题、视口和 PDF 格式是实现约定，不逐条保存到 Snapshot。

### 12. 内部 Render Token

Chromium 不复用用户 Cookie、登录 Session 或公开分享 Token。

每个渲染 attempt 签发一个新 Render Token，并绑定：

- `execution_id`；
- `attempt_no`；
- `render_snapshot_id`。

Token：

- 默认有效期 10 分钟，可系统级配置。
- 仅允许访问该 Execution 的内部渲染页。
- 首次成功建立渲染会话后记录 `consumed_at`。
- 同一会话内 Widget 数据请求继续有效。
- 已消费 Token 不能再次建立新会话。
- 同一 Execution 同一时刻只允许一个有效 Render Session。
- 新 attempt 签发 Token 时废止上一 attempt 尚未过期的 Token。
- 数据库只保存 hash、`expires_at`、`consumed_at`、`revoked_at`，不保存明文。
- 不包含用户权限，不作为数据授权凭证，不进入普通日志。

首次尝试的 `attempt_no=1`，最多两次自动重试，因此单次 Execution 最多三个 attempt。

### 13. 邮件投递

用户必须从当前组织可用的 `email` 类型渠道中显式选择 `email_channel_id`。若只有一个可用渠道，UI 可以默认选中，但后端仍保存明确 ID。

Execution 使用 Input Snapshot 中冻结的 `email_channel_id`，并在发送时动态读取当前渠道配置与凭据。渠道删除、组织范围失效或配置失效时：

- 不自动切换其他渠道；
- 在 `email` 阶段失败并记录原因。

固定邮件标题：

`[BK-Lite] {订阅名称} - {本地计划时间}`

固定邮件正文包含：

- Dashboard 名称；
- 报告计划时间；
- 实际生成时间；
- 订阅时区；
- “由 BK-Lite 自动生成”的说明。

PDF 文件名：

`{仪表盘名称}_{本地计划时间}.pdf`

文件名必须清理非法字符。

### 14. 执行状态、失败与重试

Execution 状态：

- `pending`
- `running`
- `succeeded`：SMTP 明确接受。
- `failed`
- `unknown`：SMTP 提交结果未知。

失败阶段 `failure_stage`：

- `schedule`
- `permission_check`
- `snapshot`
- `data_load`
- `render`
- `email`

具体原因使用稳定 `error_code` 和脱敏失败信息表达，不为每种错误新增状态。

不重试：

- 创建者账号或权限失效；
- Dashboard 或数据源不存在；
- 数据源或下游业务权限失败；
- 筛选条件失效；
- 其他明确业务失败。

最多自动重试两次：

- Chromium 页面加载失败；
- PDF 生成失败；
- 临时网络异常；
- SMTP 明确的可重试失败。

SMTP 已提交但结果未知时：

- 状态为 `unknown`；
- 不自动重发，避免重复邮件。

`attempt_count` 独立记录。MVP 不增加 `retrying` 状态。系统只保证内部避免重复执行，不承诺邮件端严格一次投递。

### 15. 幂等与串行执行

scheduled Execution 使用唯一约束：

`(subscription_id, scheduled_time_utc, trigger_type)`

manual_test Execution 使用唯一约束：

`(subscription_id, request_id, trigger_type)`

manual_test：

- 前端每次主动点击生成新的 `request_id`。
- 同一 `request_id` 重复请求返回既有 Execution。
- 新 `request_id` 允许再次测试。
- `scheduled_time_utc` 为空。
- 不修改 `next_run_at`，不参与漏期补偿。

同一 Subscription 同一时刻最多存在一个 `pending/running` Execution，不区分 trigger type：

- 后端用事务、行锁或数据库约束保证最终一致。
- 前端按钮禁用只改善体验。
- 已有执行时，扫描器不创建新的 scheduled Execution。
- 到期计划保留在 `next_run_at`，待当前执行结束后按“只补最近一期”规则领取。
- scheduled 运行时不能测试；manual_test 运行时计划执行暂缓但不丢失计划语义。

### 16. 手工测试发送

测试发送必须基于已保存 Subscription，不支持未保存配置直接发送。

测试发送复用正式执行链路：

- 权限校验；
- 双 Snapshot 与数据源运行 Snapshot；
- Widget 完整性检查；
- Chromium PDF；
- 邮件发送；
- 相同状态和失败模型；
- 相同的单次执行内分级重试。

测试接口异步创建 Execution 并返回 `execution_id`；前端查询最终状态，不保持长 HTTP 请求。

manual_test：

- `trigger_type=manual_test`；
- 不占用 scheduled Execution；
- 不改变 `next_run_at`；
- 不进入扫描器漏期补偿；
- 失败后不由后台重新创建新的测试 Execution；
- 不自动停用 Subscription。

### 17. 生命周期与逻辑删除

用户删除 Subscription 采用逻辑删除：

- 保存 `deleted_at`、`deleted_by`。
- 不新增 `deleted` 状态。
- 删除后默认不展示、不参与调度、不可恢复。
- 如需再次订阅，创建新的 Subscription。
- 保留 Subscription、Execution 和 Snapshot 审计历史。
- 已经进入 `pending/running` 的 Execution 按冻结输入继续完成。

`terminated` 与逻辑删除不同：

- `terminated` 是 Dashboard 删除导致的业务终止，可在普通生命周期视图中展示原因。
- 逻辑删除是用户主动移除，默认隐藏，只供授权审计查询。

### 18. PDF 临时文件与审计保留

PDF：

- 生成后只用于当前邮件发送及本次 Execution 的必要重试。
- 按受控临时目录和 `execution_id` 隔离。
- 重试窗口结束后自动清理。
- SMTP `unknown` 同样按短期策略清理。
- 不提供历史下载、报告归档中心或外部访问链接。

Execution 保存：

- Subscription ID；
- 计划时间和实际执行时间；
- trigger type；
- 状态、失败阶段、错误码和失败原因；
- attempt count；
- 使用的订阅版本；
- Dashboard 版本或 `updated_at`；
- 数据源版本信息；
- 文件名、大小、内容哈希和生成时间；
- Dashboard 在执行期间删除等审计标记。

默认保留 180 天且只允许系统级配置调整：

- Execution；
- Execution Input Snapshot；
- Render Snapshot；
- Data Source Runtime Snapshot；
- Render Token 审计数据按其安全生命周期清理。

独立运行期清理任务分批、幂等删除过期 Execution，并级联清理关联 Snapshot。清理失败不得影响 Server 启动。

Subscription 本体及 `deleted_at/deleted_by`、终止时间和原因等生命周期审计信息长期保留。

### 19. 安全与日志

- Snapshot 和日志不得包含 SMTP 密码、Token、Secret、Render Token 明文或数据源凭据。
- 筛选语义和值按敏感信息处理。
- 普通日志中的邮箱必须脱敏；数据库授权审计记录保存完整收件邮箱。
- 普通用户只能读取自己的 Subscription、Execution 和筛选详情。
- 超级用户按平台管理能力读取和管理。
- 内部渲染接口只允许内部访问，并记录 Execution 审计。
- 错误返回与日志保留定位所需的 execution ID、阶段、错误码、Widget ID、数据源 ID、attempt 和耗时，但不记录报告内容或敏感筛选值。

## UI Contract

入口位于 Dashboard 工具栏，与“导出 PDF”并列。点击后打开当前 Dashboard 的订阅抽屉。

普通用户只看到自己创建的 Subscription；超级用户可按平台权限查看和管理当前 Dashboard 的 Subscription。

抽屉支持：

- 新增；
- 编辑；
- 暂停；
- 恢复；
- 删除；
- 测试发送。

Subscription 列表展示：

- 名称；
- 收件邮箱；
- 邮件渠道；
- 周期摘要；
- 时区；
- 状态；
- `next_run_at`；
- 最近 scheduled 状态；
- 最近 manual_test 状态。

最近测试结果不能覆盖用户对最近计划执行结果的判断。

Execution 记录分层展示：

- 计划时间；
- 实际时间；
- trigger type；
- 状态；
- failure stage；
- attempt count；
- 用户可理解的失败原因。

Snapshot ID、版本、error code 等技术字段放在详情中，不挤占列表。

测试按钮在同一 Subscription 已有 `pending/running` Execution 时禁用。前端禁用不能替代后端并发控制。

## Deep Module Boundaries

实现应收敛为以下高杠杆模块，调用方不得穿透内部状态：

1. **Subscription Service**
   - 负责创建、编辑、暂停、恢复、逻辑删除、Dashboard 删除终止、权限与乐观锁。
   - 隐藏调度字段校验、筛选快照规范化、渠道范围校验和 `next_run_at` 重算规则。

2. **Schedule Calculator**
   - 输入结构化周期、IANA 时区和基准时刻，输出唯一下一次 UTC 计划时间及本地审计表达。
   - 统一封装月末、DST、暂停恢复、编辑重排和最近一期补偿语义。

3. **Due Subscription Scanner**
   - 负责有界扫描、行锁领取、串行约束、scheduled 幂等、推进 `next_run_at` 和异步派发。
   - 不执行权限查询、Chromium 或邮件发送。

4. **Execution Orchestrator**
   - 负责 Execution 状态机、实时权限校验、双 Snapshot、数据源运行 Snapshot、attempt、分级重试、临时文件和最终审计。
   - scheduled 与 manual_test 共用该模块。

5. **Dashboard Render Contract**
   - 渲染页与 Worker 只通过 `report-ready/report-failed`、Render Token 和冻结 Snapshot 协作。
   - Widget 自身只报告状态，不理解调度、邮件或重试。

6. **Mail Delivery Adapter**
   - 输入冻结渠道 ID、固定模板数据和 PDF 字节。
   - 复用现有系统管理邮件附件能力，隐藏渠道解密、SMTP 结果分类和 `unknown` 判定。

删除任一模块时，其规则会散落到多个 API、任务或组件，因而这些边界都应保持小接口和高行为杠杆。

## Failure Matrix

| 场景 | 阶段 | 是否重试 | 最终行为 |
| --- | --- | --- | --- |
| 创建者账号无效 | permission_check | 否 | failed，不生成、不发送 |
| Dashboard View 失效 | permission_check | 否 | failed，不生成、不发送 |
| 数据源或下游 401/403 | permission_check/data_load | 否 | failed，不发送部分报告 |
| 筛选值失效 | snapshot | 否 | failed，不回退默认值 |
| Widget 空数据 | data_load | 不适用 | 合法 empty，继续生成 |
| Widget 查询临时超时 | data_load | 最多 2 次 | 耗尽后 failed |
| Widget 明确失败 | data_load/render | 按错误分类 | 不发送部分报告 |
| report-ready 超时 | data_load/render | 最多 2 次 | 耗尽后 failed |
| Chromium/PDF 失败 | render | 最多 2 次 | 耗尽后 failed |
| PDF 超过 20 MB | render | 否 | failed，不发送 |
| 邮件渠道删除或越出组织 | email | 否 | failed，不切换渠道 |
| SMTP 明确临时失败 | email | 最多 2 次 | 耗尽后 failed |
| SMTP 结果未知 | email | 否 | unknown，不重发 |
| Dashboard 在 Snapshot 前删除 | snapshot | 否 | failed |
| Dashboard 在 Snapshot 后删除 | 不阻断 | 不适用 | 当前执行继续；Subscription terminated |
| 清理任务失败 | cleanup | 后续周期重试 | 不影响 Server 启动 |

## Testing Decisions

### 测试接缝

- Schedule Calculator 使用纯函数表驱动测试覆盖周期、月末、DST 和补偿。
- Subscription Service 使用真实 ORM 与权限 fixture 覆盖权限、状态、乐观锁、逻辑删除和 Dashboard 删除终止。
- Scanner 使用真实数据库事务验证行锁、批量限制、串行执行、幂等唯一约束和 `next_run_at` 推进。
- Execution Orchestrator 在 Chromium、数据查询和邮件适配器边界替换外部依赖，验证状态机、Snapshot、attempt 和重试分类。
- 内部 Render Token 使用真实签发与校验逻辑测试 hash、TTL、消费、废止、attempt 和跨 Execution 拒绝。
- 渲染页使用组件级测试与真实浏览器集成测试验证 Widget 状态聚合、完整展开、显式 ready/failed 和 PDF 生成。
- 邮件适配器复用现有附件发送测试风格，并覆盖固定标题、正文、文件名清理、20 MB 限制和 SMTP 结果分类。
- UI 通过现有 Ant Design/Storybook 或页面测试覆盖列表、抽屉、权限、状态、禁用、错误和执行详情。

### 必须覆盖的验收场景

1. 具有 Dashboard 功能与实例 View、但没有 EditChart/Operate 的用户可以创建自己的 Subscription；无 View 用户不能创建。
2. 任意合法外部邮箱可保存；每个 Subscription 只能有一个收件邮箱和一个当前组织可用的 email 渠道。
3. 创建后不立即发送；每天、每周、每月计划正确计算，29–31 日在短月回退最后一天。
4. IANA 时区正确转换 UTC；春季不存在时间移到首个有效时间；秋季重复时间只执行一次。
5. Scanner 并发运行只为同一 Subscription 和计划时间创建一个 Execution，并在创建后推进 `next_run_at`。
6. 系统停机跨过多个周期后只补最近一期；业务权限失败、暂停期间和 manual_test 不进入补偿。
7. 修改调度字段重算未来计划；修改名称、邮箱、渠道或筛选保留当前计划；乐观锁拒绝旧版本覆盖。
8. 暂停不补发，恢复从恢复时刻计算未来计划；运行中执行不受暂停、编辑或逻辑删除影响。
9. Dashboard 删除使关联 Subscription terminated；Snapshot 前删除使当前执行失败，Snapshot 后删除使当前执行继续并记录标记。
10. 静态筛选固定具体值；动态时间筛选按本次计划时间重新解析；失效筛选不回退默认值。
11. Execution Input、Render、Data Source Runtime 三类 Snapshot 冻结正确字段，且不含密码、Token、Secret 或权限快照。
12. 创建者权限在每次查询时实时获取；Dashboard View、数据源权限或下游业务权限失效均阻止发送。
13. 所有可见 Widget 均参与；折叠 Widget 被加载；隐藏和已删除 Widget 不参与；任一关键 Widget 失败不发送部分报告。
14. 空数据 Widget 发布 empty 并成功生成 PDF；静态 Widget 不查询数据但必须渲染成功。
15. 渲染页只通过显式 report-ready/report-failed 驱动；固定 sleep、networkidle 和 DOM 存在不构成成功条件。
16. Chromium 使用亮色、1440px、横向 A4 和完整展开页面生成 PDF；默认分页不丢内容；超时和 20 MB 上限生效。
17. 每个 attempt 使用新 Render Token；明文不落库；消费、过期、废止、跨任务和重复建立会话均按契约处理。
18. 权限类错误不重试；临时加载、PDF、网络及明确 SMTP 临时失败最多重试两次；SMTP 未知不重发。
19. scheduled 与 manual_test 分别按各自幂等键去重；同一 Subscription 不能同时存在多个 pending/running Execution。
20. manual_test 只基于已保存 Subscription，异步返回 execution ID，不影响 next_run_at，不进入漏期补偿。
21. 固定邮件标题、正文和文件名符合契约；发送使用冻结渠道 ID和当前安全存储凭据；渠道失效不 fallback。
22. PDF 在重试窗口后清理，不提供历史下载；Execution 保存文件元数据和内容哈希。
23. 逻辑删除隐藏并停止调度，但保留 Subscription、Execution 和 Snapshot；terminated 仍可展示原因且不可恢复。
24. 180 天清理任务分批、幂等删除 Execution 及 Snapshot，失败不阻断启动，Subscription 生命周期审计长期保留。
25. 普通日志邮箱脱敏，筛选详情受权限保护，Render Token 和报告内容不进入日志。
26. UI 分别展示最近 scheduled 与 manual_test 状态，测试结果不覆盖计划任务判断。

## Out of Scope

- Report、Screen、Topology、Architecture、NetworkTopology 等其他画布。
- PNG、JPEG、Word 等其他报告格式。
- 多收件人、抄送、密送、收件人组和平台用户选择器。
- 用户自定义邮件标题、正文、HTML、模板变量或多语言邮件模板。
- Cron、每隔 N 分钟、自定义复杂周期和显式“月末”周期选项。
- 创建后自动首发、暂停期间补发、历史漏期逐期追发。
- 多邮件渠道轮询、自动 fallback 或默认渠道猜测。
- Widget 关键性配置、允许部分报告、复杂分页、页眉页脚和页码。
- 长期 PDF 归档、历史下载、报告中心和外部下载链接。
- 全局 Subscription 管理菜单。
- 创建者转交、连续失败自动停用或自动更换执行身份。
- 非超级用户管理他人 Subscription。
- 邮件端严格一次投递保证。
- 用户级保留期配置。

## Compatibility, Rollout and Operations

- 现有手工“导出 PDF”继续保持当前行为；MVP 不要求把手工导出改为 Chromium，也不要求订阅渲染反向复用 `jsPDF.save()`。
- 复用现有 Dashboard 页面、Widget、统一筛选、数据查询权限链路、导出隐藏标记和系统管理邮件附件能力。
- 新 Chromium Worker、队列和运行配置属于运行期服务；不得加入 `batch_init` 的同步依赖。
- 非关键扫描、临时文件清理和审计清理失败不得阻断 Server 启动。
- 上线前必须验证部署镜像具备受支持的 Chromium、字体和打印依赖；Worker 缺失时 Execution 明确进入 render 失败，不影响普通 API 与 Dashboard。
- 回滚应用版本前停止新的扫描与 Chromium Worker；保留 Subscription 与 Execution 表不会影响现有 Dashboard。临时文件可由独立清理任务或运维流程回收。

## Further Notes

- 现有浏览器导出位于 `web/src/app/ops-analysis/utils/exportPdf.ts`，可复用其导出区域与隐藏/展开约定，但不能直接作为后台周期生成器。
- 现有 Dashboard 权限由运营分析功能权限（View/AddChart/EditChart/DeleteChart）与实例 View/Operate、组织范围共同决定；创建 Subscription 只使用 View 语义。
- 现有 NATS 数据源查询会把当前用户、组织、权限和组织树放入 `user_info`，本功能必须沿用该实时授权链路。
- 现有系统管理邮件发送能力已经支持原始 bytes 或 Base64 附件；本功能应通过适配器复用，不复制 SMTP 实现。
