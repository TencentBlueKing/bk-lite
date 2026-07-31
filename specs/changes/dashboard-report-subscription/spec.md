# 仪表盘报告订阅 MVP

Status: mvp_closure_aligned

## Current MVP Closure Status（2026-07-30）

手动主链路已落地并可诚实宣告成功，不再依赖 `not_ready` / placeholder 假成功：

`Subscription → Execution → Input Snapshot → Render Snapshot → Claim → Render Worker → PDF Artifact → Email Delivery → succeeded`

Scheduler 阶段已接入计划执行创建边界（不含 missed-run compensation）：

`Subscription(active + schedule) → Due Scanner → create_scheduled → on_commit(_dispatch_render) → Render Worker → Orchestrator → Email`

当前已交付：

- Subscription CRUD（`terminated` 不可由 API 直接写入）；
- Manual Execute（`request_id` 幂等 + 在途串行）；
- 双 Snapshot、Claim、Render Token、Chromium PDF、Email Delivery；
- Render Snapshot 写入非敏感 `datasource_snapshots` **审计冻结**；
- ScheduleCalculator、调度字段（可空，旧数据不回填）、DueSubscriptionScanner、
  每分钟 Beat、`create_scheduled` 专用入口；
- 邮件计划时间使用 `scheduled_time_utc` + 订阅时区；手动测试邮件无时间语义。

明确未交付 / 非本 Closure 宣称能力：

- Retry/Attempt 代码实现、Cleanup Worker、软删除生命周期、missed-run compensation；
- **DataSource Runtime Snapshot 消费链路未接入**：渲染取数仍走实时 DataSource；
  MVP **不保证**「DataSource 配置修改不影响历史 / 在途 Execution」；
- 完整权限 Snapshot、对象存储长期归档、历史 PDF 下载。

Retry 执行语义已对齐（尚未编码）：见第 14 节修正版 Resume Matrix 与 Orphan/in-flight 边界；
不新增 `retrying` 状态，不产生新 Execution，不接管 orphan；orphan `running` 仍占用 in-flight。

以下 Phase 1A–1D 小节为历史推进记录，其中“Email 未实现”“`not_ready` placeholder”
等表述已被本段覆盖；以本节与代码/测试为当前事实。

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

## Phase 1C 实现状态（2026-07-29）

已实现且验证：

- `ExecutionOrchestrator.execute(execution_id)` 作为手工执行与未来计划执行
  共用的唯一编排入口；
- 固定步骤顺序：
  `PermissionStep → SnapshotStep → RenderStep → DeliveryStep`；
- Orchestrator 只通过 `DashboardReportExecutionService.transition()` 推进
  `pending → running → succeeded/failed`；
- PermissionStep 使用创建者当前有效账号及当前组织列表，逐组织复用
  Dashboard 实例 View 权限检查，失败记录
  `failure_stage=permission_check`；
- SnapshotStep 校验 Snapshot 存在，且 Dashboard、Subscription、创建者
  标识及筛选 JSON 与 Execution 一致，失败记录
  `failure_stage=snapshot`；
- Manual Execute API 创建 Execution/Snapshot 后委托 Orchestrator，View
  不直接修改状态；
- RenderStep 与 DeliveryStep 仅返回 `placeholder`，不调用 Chromium、不生成
  PDF、不发送邮件。本阶段正常流程的 `succeeded` 仅表示基础编排步骤按顺序
  完成，不表示报告已生成或投递。

当前 Execution 只保存 username，尚未冻结 creator domain 和执行组织。
PermissionStep 对同 username 存在多个有效账号的情况 fail closed，并在创建者
当前组织中逐一校验 Dashboard 权限。正式 Scheduler 接入前应把稳定用户身份和
组织引用补入 Execution Input Snapshot；这不是完整权限 Snapshot。

Phase 1C 未新增 operation_analysis Celery Task，也未实现 Scheduler、Celery
Beat、Chromium、PDF、Email、SMTP、Retry、Render Token、Share Token 或
DataSource Runtime Snapshot。

## Phase 1C.1 实现状态（2026-07-29）

Phase 1C.1 已修正上述占位步骤导致的假成功语义：

- `POST /dashboard_subscription/{id}/execute/` 只同步创建 Execution 与
  Execution Input Snapshot，立即返回 `{execution_id, status}`；
- 正常创建结果为 `pending`，HTTP View 不调用 Orchestrator，不等待未来 Render
  或 Delivery 长流程；
- Execution 详情继续通过 `GET /dashboard_execution/{id}/` 查询；
- `pending → succeeded` 继续由状态机禁止；
- Orchestrator 启动时仍通过 Service 推进 `pending → running`，但
  `RenderStep`/`DeliveryStep` 在未实现时返回 `not_ready`；
- 任一步骤为 `not_ready` 时 Orchestrator 停止后续步骤并保持 `running`，
  只有 Render 与 Delivery 都明确返回 `completed` 后才允许进入
  `succeeded`；
- Dashboard Subscription Modal 展示新建 Execution 的 `pending` 状态，并允许
  用户刷新单条 Execution 状态；查询失败显示明确错误。

本阶段没有异步派发任务，因此由 API 创建的 Execution 会保持 `pending`，直到
后续 Render Vertical Slice 引入真实消费者。Phase 1C.1 不实现 Chromium、
PDF、Email、Scheduler、Retry、Render Token 或 Render Snapshot。

## Phase 1D-0 实现状态（2026-07-29）

已实现最小 Render Snapshot 边界：

- 新增与 Execution 一对一的不可变
  `DashboardReportRenderSnapshot`；
- Orchestrator 固定步骤调整为
  `PermissionStep → SnapshotStep → RenderSnapshotStep → RenderStep → DeliveryStep`；
- `RenderSnapshotStep` 从当前 Dashboard 一次性冻结 `dashboard_id`、
  `dashboard_name`、`dashboard_updated_at`、`view_sets`、`filters`、`other`
  与 `widget_manifest`；
- `widget_manifest` 从当前及兼容的历史布局结构提取 Widget，至少记录
  `widget_id`、`widget_type`、`datasource_id`，不复制 DataSource 配置或凭据；
- Render Snapshot 创建成功后，后续 Dashboard 或 Widget 修改不改变该快照；
- 快照拒绝实例 `save()`、QuerySet `update()` 与 `bulk_update()` 修改；
- 创建失败由 Orchestrator 经过 Execution Service 标记为 `failed`，并记录
  `failure_stage=render_snapshot`；
- 未实现的 RenderStep 仍返回 `not_ready`，Execution 保持 `running`，不会
  伪造 `succeeded`。

Phase 1D-0 没有新增 Render Route，也没有实现 DataSource Runtime Snapshot、
Query Config Snapshot、Credential Snapshot、Chromium、PDF、Email 或
Scheduler。后续正式 Render Route 只接受 `execution_id`，并从上述快照读取
冻结配置，不以 `dashboard_id` 作为渲染输入。

## Phase 1D-1A 实现状态（2026-07-29）

已实现 Render Worker 之前的 Execution Claim 边界：

- `DashboardReportExecutionService.claim_execution(execution_id)` 是唯一领取
  入口；
- Claim 在数据库事务中通过带 `status=pending` 条件的单条更新原子领取
  Execution，并根据受影响行数判定结果；成功时写入 `running` 与
  `started_at`；
- Execution 不存在、已经被领取或处于其他非 `pending` 状态时返回 `False`，
  不修改状态；
- 两个独立数据库连接并发领取同一 Execution 时，只有一个返回成功；
- 公共 `transition()` 禁止 `pending → running`，防止绕过 Claim；
- Orchestrator 不再自行执行 `pending → running`，只接受已由 Worker 成功
  领取的 `running` Execution；未领取的 Execution 会被拒绝且保持 `pending`。

Phase 1D-1A 只建立 Claim Service 与 Orchestrator 调用边界，不新增 Worker
任务，不实现 Chromium、PDF、Email、Scheduler 或 Retry。

## Phase 1D-1B 实现状态（2026-07-29）

已实现 Render Vertical Slice：

- Manual Execute 在数据库事务提交后异步派发
  `operation_analysis.render_dashboard_report` Celery Task，HTTP 仍立即返回
  `pending`；
- Task 通过 `claim_execution()` 原子领取 Execution，再调用统一
  `ExecutionOrchestrator`；
- 正式页面入口为
  `/ops-analysis/render/execution/{execution_id}`，页面只通过
  `GET /dashboard_execution/{execution_id}/render-input/` 读取 Execution Input
  Snapshot 与 Render Snapshot，不调用 Dashboard detail API；
- Input Snapshot 的 `filter_values` 会注入 Dashboard 报告模式；布局、筛选定义、
  `other` 与 Widget manifest 来自不可变 Render Snapshot；
- Chromium 固定使用亮色、1440×900 viewport、横向 A4，并只等待
  `bk-dashboard-render` 的 `report-ready/report-failed`；不使用固定 sleep、
  `networkidle` 或 DOM 存在判断；
- `report-ready` 后生成并校验 PDF，受控临时目录按 Execution 隔离；新增一对一
  `DashboardReportPdfArtifact` 保存 storage reference、size、SHA-256 与生成时间；
- PDF 成功后 Execution 保持 `running`，等待尚未实现的 DeliveryStep；Render
  Contract、Chromium、PDF 或任务投递失败均进入 `failed` 且
  `failure_stage=render`；
- 同一 Execution 只能成功 claim 一次，已有 artifact 的 Render Service 也保持
  幂等，不重复生成 PDF；
- Phase 0 `dashboard_render_regression.py` 已复用正式 Chromium 适配器，继续保留
  为显式 Render Contract/PDF 回归工具。

本阶段按任务限制没有实现 Render Token。Worker 不复用用户浏览器 Cookie，而是
为 Execution 创建者无登录审计副作用地临时签发既有标准用户 JWT，并在新的
Chromium Context 中建立 NextAuth Session；该过程不更新 `last_login`，JWT
不进入 URL、Snapshot、artifact 或日志。正式 MVP 仍必须以第 12 节的一次性
Render Token 替换该阶段性会话边界。

部署时必须配置 Worker 可访问的 `DASHBOARD_REPORT_WEB_BASE_URL`；artifact 根目录
可通过 `DASHBOARD_REPORT_ARTIFACT_ROOT` 配置，未配置时使用系统临时目录。
Render Task 固定进入 `dashboard_report_render` 队列，由独立 Supervisor Worker
消费，默认并发为 2，不占用普通业务 Worker 资源池。本阶段尚未实现 Email、
Scheduler、Retry、Render Token、Data Source Runtime Snapshot 或长期 PDF 归档。

## Phase 1D-1C 实现状态（2026-07-29）

Render 生产边界已按 MVP 收紧：

- 新增与 Execution 一对一的短时 `DashboardReportRenderToken`，数据库只保存
  SHA-256、`expires_at`、`consumed_at` 与创建时间；
- Worker 签发的明文 Token 只在内存中传递，通过匿名 exchange 原子消费，重复、
  过期和跨 Execution 使用均失败；
- exchange 建立的短时 Render Session JWT 显式绑定 `render_execution_id`，
  普通用户登录 Session 不能读取 `render-input`；
- PDF artifact 增加附件 `filename` 与 `expires_at`，存储引用改为
  Execution 隔离目录；非 DEBUG 环境必须配置 Render Worker 与未来 DeliveryStep
  共同可见的 `DASHBOARD_REPORT_ARTIFACT_ROOT`；
- release-image Chromium smoke 增加 `fc-match` CJK 字体验证、Chromium 版本、
  PDF 非空与 PyMuPDF 中文文本提取断言。

本阶段未实现 Retry/Attempt/Revoke、Email、Scheduler、对象存储或 Artifact
cleanup worker。Render Token 保持每个 Execution 单次签发边界，后续 Retry
阶段再按第 12 节扩展 attempt/revoke 字段。

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
| Data Source Runtime Snapshot | 本次执行写入 Render Snapshot 的非敏感数据源配置审计冻结（如 `query_config` / `field_schema`）；不含凭据。当前 MVP 仅持久化，**不驱动**渲染取数；后续若接入消费链路，才可宣称配置变更不影响该次执行查询。 |
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

- `subscription_version`（schedule configuration version；非调度字段变更不递增）；
- `subscription_name`；
- `recipient_email`；
- `email_channel_id`；
- `scheduled_time_utc`（`scheduled` 必填；`manual_test` 为空）；
- `schedule_timezone`（订阅 IANA 时区；有调度配置时必填冻结；邮件计划时间的唯一时区来源）；
- `scheduled_local_time`（由 `scheduled_time_utc` + `schedule_timezone` 派生的本地审计表达；`manual_test` 可空）；
- `trigger_type`；
- `creator_id`；
- 筛选语义；
- 本次解析后的筛选具体值。

时间语义边界：

- 订阅 `timezone` / Snapshot `schedule_timezone` 是报告周期与邮件展示的**唯一**时区来源。
- `execution.created_at` / `started_at` / `finished_at` 仅用于 Execution Detail、运维排障与审计查询，**不**进入普通报告邮件正文。
- 既有 Snapshot 字段 `creator_timezone`（若仍存在）表示创建者账号展示偏好，**不是**邮件时间来源，Scheduler 阶段不得将其用于标题、正文或附件文件名。

Execution 开始时冻结 `Render Snapshot`：

- 当前 Dashboard 布局；
- Widget 配置；
- 数据源引用；
- 展示配置；
- Dashboard `updated_at` 或版本标识；
- Snapshot 创建时间。

按 Render Snapshot 引用写入 `Data Source Runtime Snapshot`（审计冻结）：

- `datasource_id`；
- `source_type`；
- 非敏感 `query_config` / `field_schema`。

任何 Snapshot 均不得保存密码、Token、Secret 或用户权限。

数据查询时（当前 MVP 实现）：

- 根据 `creator_id` 获取当前用户上下文。
- 沿用现有 `user_info` 权限链路向下游传递当前组织、用户、权限和组织树。
- 从安全存储读取当前有效凭据。
- **按 Widget 引用的实时 DataSource 定义取数**，不读取上述审计冻结驱动查询。

数据源在 Render Snapshot 创建时缺失则跳过写入对应审计项；渲染期若实时 DataSource
不可访问或凭据无效，按既有数据加载失败处理。**当前不宣称**“冻结后修改数据源配置
不影响当前执行”；该保证取决于尚未接入的消费链路。

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

邮件时间语义（普通报告邮件）：

- **只展示计划时间**，不展示实际生成时间或 Worker 处理时间。
- `scheduled` Execution：
  - 计划时间来源：`Execution.scheduled_time_utc`（创建时冻结进 Input Snapshot）+
    `Subscription.timezone`（冻结为 Snapshot `schedule_timezone`）。
  - 展示格式：`报告计划时间：YYYY-MM-DD HH:MM ({IANA})`，
    例如 `报告计划时间：2026-08-01 09:00 (Asia/Shanghai)`。
  - 这是用户理解「这封报告属于哪个周期」的业务时间。
- `manual_test` Execution：
  - 无计划周期；标题与正文不伪造计划时间，也不写入实际生成时间。
  - 标题使用：`[BK-Lite] {订阅名称} - 手动测试`。
  - 正文标明手动测试，不出现「报告计划时间」行。
- 禁止使用 `creator_timezone`、服务器本地时区或执行节点时区拼装邮件时间。

固定邮件标题：

- `scheduled`：`[BK-Lite] {订阅名称} - {本地计划时间}`
  （本地计划时间由 Snapshot `scheduled_local_time` 或等价格式化结果提供，不含时区后缀也可；
  时区在正文「报告计划时间」行中显式给出。）
- `manual_test`：`[BK-Lite] {订阅名称} - 手动测试`

固定邮件正文包含：

- Dashboard 名称；
- `scheduled`：报告计划时间（含 IANA 时区）；
- `manual_test`：手动测试说明（无计划时间、无实际生成时间）；
- “由 BK-Lite 自动生成”的说明。

固定邮件正文**不包含**：

- 实际生成时间；
- `created_at` / `started_at` / `finished_at`；
- 创建者展示时区或其他非订阅时区。

PDF 文件名：

- `scheduled`：`{仪表盘名称}_{本地计划时间}.pdf`
- `manual_test`：`{仪表盘名称}_手动测试.pdf`

文件名必须清理非法字符。

### 14. 执行状态、失败与重试

Execution 状态：

- `pending`
- `running`
- `succeeded`：SMTP 明确接受，或已确认 delivery success 后的终态。
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

#### 14.1 Retry 状态机与 ownership

- Retry 是单个 Execution 内部的 attempt 级行为，不创建新的 Execution。
- MVP 不增加 `retrying` 状态；attempt 失败但仍准备继续重试时，Execution 保持 `running`。
- 禁止 `failed → running`：可重试的中间失败不得先把 Execution 写成 `failed`。
- Execution claim 一次：`pending → running` 仍只能经 `claim_execution`；Retry 不重新 claim，也不把 Execution 退回 `pending`。
- Attempt 不独立 claim。
- Celery：一个 Render Task 在 claim 后的同一 owning task 内串行完成最多三个 attempt（`attempt_no` 1..3；最多两次自动重试）；不按 attempt 重新 dispatch。
- `attempt_count`：每个 attempt **开始时**递增；Classifier 在 attempt 失败后看到的值即刚结束的 attempt 序号。若结果本可 `retry` 但 `attempt_count >= 3`，必须 `terminal_failed`。
- 系统只保证内部避免重复执行，不承诺邮件端严格一次投递。

#### 14.2 RetryClassifier 输入与职责

失败分类与「是否创建下一 attempt」**不得**由各 Step 决定。

固定流水线：

`AttemptResult + attempt_count + current_resource_state → RetryClassifier → next attempt / terminal`

然后（仅当输出 `retry`）：

`resume_class + current_resource_state → Orchestrator 计算 resume point → 启动下一 attempt`

##### 输入（必须拆开）

| 输入 | 内容 | 禁止 |
| --- | --- | --- |
| `AttemptResult` | 见下方最小字段 | **不得**内嵌完整 `resource_state`；不得包含 `should_retry` / `resume_class` |
| `attempt_count` | 刚结束（或当前）attempt 序号 | — |
| `current_resource_state` | Orchestrator 在调用 Classifier **之前**观测到的只读资源快照（见 14.3） | **不得**由 Step 拼进 `AttemptResult`；**不**单独决定 `resume_class` |

##### AttemptResult 最小字段

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `ok` | 是 | 本步是否成功 |
| `failure_stage` | `ok=false` | 稳定阶段名 |
| `error_code` | `ok=false` | 稳定机器码 |
| `error_message` | `ok=false` | 脱敏可读信息 |
| `side_effect` | 否 | **仅日志/调试**；**不参与** RetryClassifier 决策 |

##### 职责

- **Step**：只执行业务步骤并返回 `AttemptResult`；不循环、不决定 retry、不计算 resume point。
- **RetryClassifier**：唯一策略入口；输出且仅输出：
  - `retry` + `resume_class`（见 14.5）；
  - `terminal_failed`；
  - `terminal_unknown`（仅 SMTP 结果未知）。
  - `resume_class` **唯一**来自 Classifier 输出；`current_resource_state` 只作观测/校验上下文（例如 artifact 是否仍 valid），不得由 Orchestrator 根据资源态改写 Classifier 已给出的 `resume_class`。
- **Orchestrator**：唯一推进 attempt、写 Execution 终态、在 `retry` 后按 Classifier 的 `resume_class` 续跑的编排者。生产入口仅 `execute(execution_id)`（或唯一等价公开方法），**禁止**第二生产入口或长期双轨旧单次执行路径；允许测试辅助函数/注入，但不得被生产调用。

##### Execution 最终错误字段语义

- `failure_stage` / `error_code` / `error_message` 表示 **Execution 最终原因**。
- attempt 中间失败 **不得**覆盖写入这些字段。
- 仅当 Classifier 输出 `terminal_failed` 或 `terminal_unknown`（或等价终态收敛）时，才写入最终原因。
- **不新增** `last_attempt_*` 字段；中间 attempt 诊断依赖日志 / 未来可选 attempt entity，不进 Execution 终态列。

##### Delivery outcome 最小规则（先于 retry）

`current_resource_state.delivery_outcome`：

- `not_delivered`：尚未确认投递成功；
- `delivered`：已确认投递成功（与现有 `delivered_at` 语义一致）；
- `smtp_unknown`：SMTP 提交结果未知。

硬规则：

- `delivery_outcome=delivered`：不得 `retry`；Orchestrator 必须将 Execution 收敛为 `succeeded`（若尚非终态）。
- `delivery_outcome=smtp_unknown` 或 Classifier 判为 SMTP unknown：`terminal_unknown`；不得再 Delivery。
- timeout 收敛**不得**把已 `delivered` 的 Execution 写成 `failed`（见 14.6）。

#### 14.3 current_resource_state（观测契约）

Orchestrator 在每次调用 Classifier / 计算 resume 前观测：

| 字段 | 取值 | 观测方式（最小） |
| --- | --- | --- |
| `input_snapshot` | `absent` \| `valid` \| `corrupt` | DB：无行=`absent`；有行且与 Execution 标识/筛选结构一致=`valid`；有行但不一致=`corrupt` |
| `render_snapshot` | `absent` \| `valid` \| `corrupt` | DB：无行=`absent`；有行且绑定本 Execution=`valid`；有行但损坏/不一致=`corrupt` |
| `artifact` | `absent` \| `valid` \| `unusable` | 无行=`absent`；有行且未过期且文件可读=`valid`；有行但过期/缺文件/不可读=`unusable` |
| `delivery_outcome` | `not_delivered` \| `delivered` \| `smtp_unknown` | 已确认成功=`delivered`；SMTP unknown 已记录=`smtp_unknown`；否则=`not_delivered` |

说明：

- `absent` 与「创建动作失败仍无行」在观测上相同；是否可 retry 由 `error_code` + 资源态共同由 Classifier 判定。
- **有行即视为曾成功冻结**；此后只允许 verify/reuse，不允许覆盖重建。`corrupt` → 只能 `terminal_failed`。
- `current_resource_state` **仅观测上下文**：用于 Classifier 输入与 resume 路径上的前置校验（如 delivery 要求 artifact valid）；**不得**由 Orchestrator 根据资源态另行推导或覆盖 `resume_class`。

#### 14.4 InputSnapshot 创建边界（Retry 不得改写）

保持现有链路：**Execution 创建阶段**负责 InputSnapshot 冻结；Retry **不**重新定义 Creation。

| 阶段 | 行为 |
| --- | --- |
| Execution creation（`execute_manual` / `create_scheduled`） | 在同一创建路径内创建 InputSnapshot。成功：Execution 保持 `pending` 并 on_commit 派发 Render Task。失败：`pending → failed`，`failure_stage=snapshot`，**不** claim、**不**进入 Retry attempt 循环。 |
| claim 之后 / Retry attempt 内 | **禁止**补建、重建、覆盖 InputSnapshot。SnapshotStep 只做 verify：`absent` 或 `corrupt` → `AttemptResult` 交 Classifier → 必须 `terminal_failed`。`valid` → 继续。 |

因此：

- claim 后不存在「InputSnapshot ensure/create」resume point。
- 「Snapshot 创建阶段 transient failure」若发生在 **creation**，由创建路径直接终态 `failed`；不占用 owning-task Retry 窗口。
- 「成功冻结后不可重建」适用于 claim 后的 InputSnapshot；与 creation 失败是否可另开新 Execution 无关（新 Execution 是新的创建边界，不是 Retry）。

#### 14.5 failure classification → retry decision → resume point

禁止无法定位 resume 的泛化分类（例如笼统的「临时网络异常」）。网络类失败必须落到具体 `failure_stage` + `error_code`，从而落入下表唯一行。

`resume_class` 仅在 Classifier 输出 `retry` 时出现：

- `render_snapshot_ensure`
- `render`
- `delivery`

##### 映射表（实现唯一依据）

| failure_stage | error_code（稳定名，示例集合） | `input_snapshot` | `render_snapshot` | `artifact` | `delivery_outcome` | Classifier | resume_class / 终态 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| * | * | * | * | * | `delivered` | （不进入 retry） | Orchestrator → `succeeded` |
| permission_check | `creator_inactive` / `dashboard_view_denied` / … | * | * | * | * | `terminal_failed` | — |
| snapshot | `input_snapshot_absent` / `input_snapshot_corrupt` / `filter_invalid` | absent/corrupt/valid | * | * | * | `terminal_failed` | claim 后不可补建 |
| snapshot | （creation 路径失败，未 claim） | absent | — | — | — | 不适用 Retry | creation 已 `failed` |
| render_snapshot | `render_snapshot_create_transient` | valid | absent | * | not_delivered | `retry`（若 attempt_count < 3） | `render_snapshot_ensure` |
| render_snapshot | `render_snapshot_corrupt` | valid | corrupt | * | * | `terminal_failed` | — |
| data_load | `widget_query_timeout` / `widget_query_transient` | valid | valid | * | not_delivered | `retry` | `render` |
| data_load | `widget_data_forbidden` / `datasource_missing` / … | valid | valid | * | * | `terminal_failed` | — |
| render | `chromium_launch_failed` / `page_load_failed` / `report_ready_timeout` / `pdf_generate_failed` | valid | valid | absent/unusable | not_delivered | `retry` | `render` |
| render | `pdf_too_large` / `render_contract_business_failed` / … | valid | valid | * | * | `terminal_failed` | — |
| email | `smtp_transient` / `smtp_connection_failed` / `smtp_timeout` | valid | valid | valid | not_delivered | `retry` | `delivery` |
| email | `smtp_transient` / … | valid | valid | absent/unusable | not_delivered | `retry` | `render`（先重建可用 Artifact，再 Delivery） |
| email | `channel_missing` / `channel_not_email` / `smtp_permanent` / … | * | * | * | * | `terminal_failed` | — |
| email | `smtp_result_unknown` | * | * | * | smtp_unknown 或等价 | `terminal_unknown` | — |
| * | 未登记 / 无法分类 | * | * | * | * | `terminal_failed` | — |
| * | `execution_timeout` | * | * | * | not_delivered | `terminal_failed` | owning task 或 timeout checker |
| * | `execution_timeout` | * | * | * | delivered | 不得 failed | 见 14.6：优先 `succeeded` |

##### resume point（仅 `retry`）

统一：下一 attempt 始终先 `Permission`；失败则新的 `AttemptResult` 再进 Classifier。

| resume_class | Permission 之后的路径 |
| --- | --- |
| `render_snapshot_ensure` | InputSnapshot **verify only** → RenderSnapshot create（仅当 `render_snapshot=absent`）→ Render → Delivery |
| `render` | InputSnapshot verify → RenderSnapshot verify/reuse → Render → Delivery |
| `delivery` | InputSnapshot verify → RenderSnapshot verify/reuse → **跳过 Render** → Delivery |

约束：

- `delivery` 仅当 Classifier 给出 `resume_class=delivery` **且**观测时 `artifact=valid`；不得仅因 Artifact valid 选择 Delivery。
- `render_snapshot_ensure` 仅当 `render_snapshot=absent`；若已是 `corrupt`，不得 ensure，应已在映射表 terminal。
- RenderSnapshot：**首次创建与 retry 补创建**共用同一 ensure/create 语义——仅 `absent` 时创建；`valid` 只 reuse；**禁止**覆盖已持久化行。与 InputSnapshot 不同：RenderSnapshot 本就在 claim 后的 Orchestrator 路径创建。

#### 14.6 Execution timeout 与 orphan（最终收敛）

区分两类 `running`：

| 类型 | 含义 | 谁负责 | 收敛 |
| --- | --- | --- | --- |
| retry window 内 running | owning task 仍存活 | owning task / Orchestrator | 总预算耗尽 → 条件写 `failed`（若未 delivered）；释放 in-flight |
| orphan running | owning task 已丢失 | **Execution timeout 收敛检查**（可挂现有每分钟 Beat 旁路；非完整 Recovery） | 超过 deadline → 条件写终态；释放 in-flight |

##### timeout 定义

- 总预算从 claim 成功（`started_at`）起算，覆盖最多三个 attempt；默认与单次 Execution 总超时同量级（5 分钟级，可配置），可加短 grace。
- 查询 orphan 候选：`status=running` 且 `started_at`（否则 `created_at`）早于 `now - execution_timeout`。
- timeout checker **不做**：重 claim、dispatch Render、新 attempt、重建 Snapshot、重发邮件、删 artifact、补漏期。

##### 并发保护与仲裁（必须）

所有终态写入（含 timeout、`succeeded`/`failed`/`unknown`）必须带 **状态条件保护**：

- 仅当当前 `status=running` 时才允许迁移到终态（条件更新 / 等价 CAS；受影响行数 0 视为 no-op）。
- **禁止** timeout 或任何 writer 覆盖已存在的 `succeeded` / `failed` / `unknown`。

仲裁：

1. owning task 与 timeout checker 同时尝试终态化时：谁先成功把 `running` 改为终态，谁生效；另一方条件更新失败并停止。
2. 若观测 `delivery_outcome=delivered`：timeout checker **不得**写 `failed`；应条件写 `succeeded`（若仍为 `running`），或 no-op（若已终态）。
3. 若观测 `delivery_outcome=smtp_unknown`：timeout checker **不得**改写为 `failed`；应条件写 `unknown`（若仍为 `running`），或 no-op。
4. owning task 在 SMTP 成功并标记 delivered 后写 `succeeded`：即使 checker 并发，条件保护保证不会出现「先 succeeded 再被 timeout 打成 failed」。

##### timeout 与 in-flight

- 成功收敛为 `failed` / `succeeded` / `unknown` 后，均不再计入 in-flight，Subscription 槽位释放。
- 释放后允许新的 manual_test；Scanner 可按既有规则继续领取后续计划（timeout 不构成漏期补偿新周期）。

##### 明确不做

- 不引入完整 Recovery/Cleanup；
- timeout 不恢复未完成投递（已 delivered 的只保证终态不被错误降级）；
- Retry 不接管 orphan。

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

- 计划时间（订阅时区下的业务周期时间；`manual_test` 可空或标为手动测试）；
- 实际时间（`created_at` / `started_at` / `finished_at`，仅详情与排障，不 mirror 进邮件）；
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
   - Retry resume 按 InputSnapshot / RenderSnapshot / Artifact 资源状态决定起点，不按 failure_stage 硬编码路径。
   - scheduled 与 manual_test 共用该模块；Retry 不产生新 Execution，也不接管 orphan。

5. **Dashboard Render Contract**
   - 渲染页与 Worker 只通过 `report-ready/report-failed`、Render Token 和冻结 Snapshot 协作。
   - Widget 自身只报告状态，不理解调度、邮件或重试。

6. **Mail Delivery Adapter**
   - 输入冻结渠道 ID、固定模板数据（含 Snapshot 计划时间字段）和 PDF 字节。
   - 邮件只消费 `scheduled_time_utc` / `schedule_timezone` / `scheduled_local_time` 拼装计划时间；不消费 `creator_timezone`，不写入实际生成时间。
   - 复用现有系统管理邮件附件能力，隐藏渠道解密、SMTP 结果分类和 `unknown` 判定。

删除任一模块时，其规则会散落到多个 API、任务或组件，因而这些边界都应保持小接口和高行为杠杆。

## Failure Matrix

| 场景 | 阶段 | 是否重试 | 最终行为 |
| --- | --- | --- | --- |
| 创建者账号无效 | permission_check | 否 | failed，不生成、不发送 |
| Dashboard View 失效 | permission_check | 否 | failed，不生成、不发送 |
| 数据源或下游 401/403 | permission_check/data_load | 否 | failed，不发送部分报告 |
| 筛选值失效 | snapshot | 否 | failed，不回退默认值 |
| Input/Render Snapshot 创建阶段 transient failure | snapshot / render_snapshot | 最多 2 次 | 仍未成功落库则可再 ensure/create；耗尽后 failed |
| Input/Render Snapshot 冻结成功后损坏 | snapshot / render_snapshot | 否 | failed；禁止重建 |
| Widget 空数据 | data_load | 不适用 | 合法 empty，继续生成 |
| Widget 查询临时超时 | data_load | 最多 2 次 | 耗尽后 failed |
| Widget 明确失败 | data_load/render | 按错误分类 | 不发送部分报告 |
| report-ready 超时 | data_load/render | 最多 2 次 | 耗尽后 failed |
| Chromium/PDF 失败 | render | 最多 2 次 | 耗尽后 failed |
| PDF 超过 20 MB | render | 否 | failed，不发送 |
| 邮件渠道删除或越出组织 | email | 否 | failed，不切换渠道 |
| SMTP 明确临时失败 | email | 最多 2 次 | 耗尽后 failed |
| SMTP 结果未知 | email | 否 | unknown，不重发 |
| Execution 总超时耗尽 | running 内 | 否 | failed；不得再开下一 attempt |
| Worker crash / task 丢失导致 orphan running | running | 否（MVP） | 保持 running；不自动 reclaim / 重投；**继续占用 in-flight，阻塞同订阅新的 manual/scheduled** |
| Dashboard 在 Snapshot 前删除 | snapshot | 否 | failed |
| Dashboard 在 Snapshot 后删除 | 不阻断 | 不适用 | 当前执行继续；Subscription terminated |
| 清理任务失败 | cleanup | 后续周期重试 | 不影响 Server 启动 |

## Testing Decisions

### 测试接缝

- Schedule Calculator 使用纯函数表驱动测试覆盖周期、月末、DST 和补偿。
- Subscription Service 使用真实 ORM 与权限 fixture 覆盖权限、状态、乐观锁、逻辑删除和 Dashboard 删除终止。
- Scanner 使用真实数据库事务验证行锁、批量限制、串行执行、幂等唯一约束和 `next_run_at` 推进。
- Execution Orchestrator 在 Chromium、数据查询和邮件适配器边界替换外部依赖，验证状态机、Snapshot、attempt、按资源状态的 resume 起点，以及重试分类。
- 内部 Render Token 使用真实签发与校验逻辑测试 hash、TTL、消费、废止、attempt 和跨 Execution 拒绝。
- 渲染页使用组件级测试与真实浏览器集成测试验证 Widget 状态聚合、完整展开、显式 ready/failed 和 PDF 生成。
- 邮件适配器复用现有附件发送测试风格，并覆盖固定标题、正文、文件名清理、20 MB 限制、SMTP 结果分类，以及「只含计划时间、不含实际生成时间 / 不使用 creator_timezone」的契约。
- UI 通过现有 Ant Design/Storybook 或页面测试覆盖列表、抽屉、权限、状态、禁用、错误和执行详情。
- MVP 不要求覆盖 orphan reclaim；若补充测试，仅断言 worker 丢失后 execution 可停留 `running` 且无第二 task 自动接管。

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
18a. Resume 仅按资源状态：Snapshot 未成功落库的 transient 创建失败可再 ensure/create；冻结成功后损坏则终结且禁止重建；无可用 Artifact 的可重试 render/pdf 从 Render 重跑；有有效 Artifact 的可重试 delivery 跳过 Render。
18b. Retry 期间 Execution 保持 `running`；不新增 `retrying`；不出现 `failed → running`；同一 owning task 内完成 attempt；MVP 不自动接管 orphan running Execution；orphan 继续占用 in-flight 并阻塞同订阅新的 manual/scheduled。
19. scheduled 与 manual_test 分别按各自幂等键去重；同一 Subscription 不能同时存在多个 pending/running Execution。
20. manual_test 只基于已保存 Subscription，异步返回 execution ID，不影响 next_run_at，不进入漏期补偿。
21. 固定邮件标题、正文和文件名符合契约；`scheduled` 仅展示订阅时区下的计划时间，不展示实际生成时间；`manual_test` 不伪造计划时间；发送使用冻结渠道 ID 和当前安全存储凭据；渠道失效不 fallback。
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
