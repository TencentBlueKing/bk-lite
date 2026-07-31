# APM MVP：接入、服务、Trace 与基础告警

Status: accepted

## Problem Statement

仓库已经有 APM 产品规格和 Storybook 原型，但尚无真实的 `server/apps/apm`、`web/src/app/apm`、OTLP 数据面或 Trace 存储。现有规格还混淆了“接入实例”与“逻辑服务”：接入列表口头上展示实例，实际却按 `service.namespace + service.name` 聚合；同一多节点服务因此无法同时满足实例接入管理和服务整体健康分析。

当前 `/telegraf/api` 由 Telegraf 的 Influx 输入使用，不能接收 OTLP protobuf。Django 也不适合作为高吞吐 Span 接收器。APM 必须作为与 Monitor、Log 同级的独立产品域，在不破坏现有采集链路、不让外部 Trace 基础设施阻断 Server 启动的前提下，先打通“能接入、能看服务、能查 Trace、能告警”的纵向链路。

## Solution

新增独立的 APM 控制面，并把遥测数据面交给 OpenTelemetry Collector、VictoriaTraces 和 VictoriaMetrics：

```text
应用探针 / SDK
      │ OTLP/HTTP 或 OTLP/gRPC
      ▼
边缘鉴权 ── 校验接入凭证、移除伪造保留属性
      ▼
OpenTelemetry Collector Gateway
      ├── 全量 Span → Span Metrics → VictoriaMetrics
      └── 尾采样 Span ───────────→ VictoriaTraces

BK-Lite apps.apm
      ├── PostgreSQL：接入源、服务、实例、组织、策略、事件与告警
      ├── TraceStore：查询 VictoriaTraces
      ├── MetricStore：查询 VictoriaMetrics
      └── 可选通知 ── 标准事件 / NATS ──→ 告警中心
```

第一期只实现添加接入、接入实例列表、服务目录与 RED、Trace 搜索与详情、基础阈值告警。首页、拓扑、SLO、Issue 聚类、运行时指标和高级治理保留 Storybook 设计，不进入本期生产路由。

## User Stories

1. As an APM 管理员, I want to create an ingest source and copy a language-specific setup snippet, so that telemetry is authenticated and attributed without modifying BK-Lite source code.
2. As an APM operator, I want to see every reporting runtime instance separately, so that a silent or replaced Pod does not disappear inside a service aggregate.
3. As an application owner, I want horizontally scaled instances to aggregate into one logical service, so that throughput, error rate and latency describe the whole service.
4. As an operator, I want service health separated by environment, so that testing traffic cannot pollute production health.
5. As a developer, I want to start from an anomalous service and drill into a concrete Trace and Span, so that I can locate the slow or failing dependency.
6. As an alert administrator, I want APM policies to maintain their own alert lifecycle and optionally send standard events to a configured alert-center NATS channel, so that APM remains independently operable while cross-source aggregation is still available.
7. As a deployment administrator, I want APM storage failures to degrade APM pages without blocking BK-Lite Server startup, so that observability is not a circular hard dependency.

## Implementation Decisions

### 1. 产品与模块边界

- 后端新增 `server/apps/apm`，由现有 app 自动发现机制暴露在 `/api/v1/apm/`；前端新增 `web/src/app/apm`，与 `/monitor`、`/log` 同级。
- APM 不复用 Monitor 的监控对象、监控实例或 CMDB 服务模型。它们的身份、生命周期和数据来源不同。
- APM 只拥有接入元数据、服务与实例目录、遥测查询编排、APM 策略、事件、告警和评估状态。原始 Span 与派生指标不写 PostgreSQL。
- Monitor、Log、APM 等同级 App 各自拥有领域告警事实与生命周期；任何 App 不得直接引用另一个 App 的模型、表或内部实现。告警中心仅作为可选通知渠道接收标准事件副本。
- Storybook 是视觉和交互参考，不把当前大型 story 文件直接复制进生产页面。生产页面按路由拆分并复用 Ant Design 和已有共享组件；只有出现至少两个真实使用方时才新增共享抽象。

### 2. 统一领域模型

#### 2.1 APM 接入源

`ApmIngestSource` 表示一次“添加接入”产生的受控上报入口，而不是逻辑服务或运行实例。它包含名称、接入方式、环境提示、启停状态、凭证摘要与前缀、首次/最近接收时间和审计字段。

`ApmIngestSourceOrganization` 是接入源与组织的多对多关系。添加接入时至少选择一个组织；新发现实例默认复制接入源当时的组织集合。接入源只提供默认权限，不参与服务或实例身份。

凭证规则：

- 创建或轮换时只展示一次明文，数据库仅保存不可逆摘要和可识别前缀；凭据不得写日志、操作记录、Span 或前端持久缓存。
- 接入代码片段必须携带 `Authorization: Bearer <token>`，不再沿用旧规格中的匿名 OTLP 入口。
- 禁用或轮换接入源必须使旧凭证失效；并发轮换以数据库状态为最终仲裁。
- 网关从认证结果注入受信任 `bk.ingest_source.id`。客户端提交的同名 `bk.*` 保留属性一律先删除，不能伪造来源或组织。
- `bk.ingest_source.id` 只用于来源追踪、接入方式解析和排障，不参与服务身份。

第一期边缘鉴权实现使用反向代理认证子请求：代理将 Bearer Token 交给 APM 机器认证接口校验，成功后把内部来源 ID 传给 Collector；正向结果可短时缓存，撤销延迟必须有上限并可测试。代理必须移除外部同名内部 Header。认证服务不可用时，新且未缓存的请求返回 503，不允许匿名降级。

#### 2.2 APM 接入实例

接入实例是一个实际上报遥测数据的运行实例，身份为：

```text
service.namespace + service.name + service.instance.id
```

- `service.instance.id` 必须在同名服务实例间唯一。接入向导按运行环境动态注入：Kubernetes 使用 Pod UID，Docker 使用容器实例 ID，固定主机使用稳定的平台实例 ID；无法取得稳定天然 ID 时由探针生成 UUID。
- 不能把一个写死的实例 ID复制到多个副本。Collector 无法无歧义判断来源时不得自行猜测实例 ID。
- 缺少 `service.instance.id` 的 Span 仍可进入 Trace 与服务级指标，但不创建虚假的接入实例；接入诊断展示“实例身份缺失”并给出修复片段。
- Pod 或运行实例被重建并产生新 ID 时创建新实例；旧实例停止上报后进入静默，达到归档阈值后自动归档。实例历史不因重建而覆盖。
- `ApmServiceInstanceOrganization` 表示实例可见、可操作组织。新实例默认继承接入源组织；用户可改为自定义组织集合。继承态随接入源组织变化，自定义态不被自动覆盖。
- 当前组织只影响实例列表、实例详情、具体 Trace 和实例操作的授权，不改变底层 Span 存储。

#### 2.3 APM 服务

APM 服务是一个长期存在的逻辑服务，身份为：

```text
service.namespace + service.name
```

- 同名服务的所有 `service.instance.id` 聚合为一个服务；接入源、版本、环境和实例 ID 都不参与服务身份。
- `service.namespace` 缺失时规范化为空 namespace，UI 展示为“未归类应用”；`service.name` 必须非空。不要因 namespace 缺失丢弃有效 Span。
- `deployment.environment` 与 `service.version` 是查询维度。服务身份不含环境，但 RED、健康和告警必须按环境分别计算。
- 服务目录的“全部环境”表示列出所有环境视图，不把生产、预发、测试的健康值合并成一个值。服务数量仍按逻辑服务去重。
- 服务指标全局聚合同一环境下的全部实例，不受实例组织权限影响。
- `ApmServiceOrganization` 独立控制服务聚合页、拓扑和服务级操作权限。服务首次原子创建时复制第一个成功发现实例的组织集合；多个实例同时首次上报时，以成功创建服务记录的实例为准。
- 后续实例及其实例权限变化不自动修改服务权限；管理员可以手动调整服务组织。因而有服务权限但无某实例权限的组织可以看到包含该实例贡献的聚合值，但不能查看该实例明细或 Trace。

#### 2.4 状态与归档

- 实例活跃：最近 15 分钟有 Span；静默：超过活跃窗但不足 7 天；已归档：静默至少 7 天或手动归档。
- 服务状态按“服务 + 环境”的全局实例指标计算，不复用实例状态。单个实例静默不能使仍有流量的服务归档。
- 归档只影响默认目录与操作状态，不删除 Trace、指标和元数据；数据是否可查询仍受其存储保留期限制。
- 新 Span 到达已归档实例或服务时自动解档。自动归档、解档和目录对账属于运行期幂等任务。

#### 2.5 PostgreSQL 模型

| 模型 | 关键字段与约束 |
| --- | --- |
| `ApmIngestSource` | UUID 主键、名称、接入方式、云区域、`credential_digest`、`credential_prefix`、启用状态、首次/最近接收时间、审计字段 |
| `ApmIngestSourceOrganization` | 接入源 + 组织唯一；作为继承态实例的默认权限 |
| `ApmService` | UUID 主键、规范化 namespace/name、首次/最近发现、归档时间/原因；namespace/name 条件唯一 |
| `ApmServiceOrganization` | 服务 + 组织唯一；与实例组织独立 |
| `ApmServiceInstance` | UUID 主键、服务外键、instance ID、环境、版本、来源外键、权限模式、首次/最近发现、归档字段；服务 + instance ID 唯一 |
| `ApmServiceInstanceOrganization` | 实例 + 组织唯一；实例为继承态时由接入源组织同步 |
| `ApmPolicy` | 服务、环境、指标类型、比较符、阈值、持续/恢复窗口、级别、通知开关、通知渠道、启用状态和审计字段 |
| `ApmPolicyState` | 策略评估游标、连续命中/恢复计数、当前状态、最后成功/失败时间、外部告警 ID |
| `ApmAlert` | APM 告警唯一 ID、策略、服务、环境、状态、级别、当前值、开始/结束时间和组织快照 |
| `ApmEvent` | 事件唯一键、关联告警、动作、级别、值、内容、发生时间和组织快照 |
| `ApmAlertOutbox` | 关联 APM 事件、目标通知渠道、规范化 payload、投递状态、尝试次数和下次重试时间；事件 + 渠道唯一防止重复投递 |

- 所有数据库访问使用 Django ORM，不使用 raw SQL、`.raw()`、`RawSQL` 或 `cursor.execute`。
- 原始 namespace/name/instance ID 保留用于展示，同时保存规范化值用于唯一约束；规范化规则由一个领域函数统一实现，API、任务和迁移不能各自复制。
- 外部组织使用稳定 ID 关联并遵循现有组织删除语义；不得把组织 ID写进 Trace 或指标标签。
- `ApmAlert`、`ApmEvent`、`ApmAlertOutbox` 与策略状态更新处于同一数据库事务；实际通知发生在提交后的运行期任务。

### 3. 遥测入口与数据面

- Collector Gateway 是唯一 OTLP 接收器：内部支持 OTLP/gRPC `4317` 和 OTLP/HTTP `4318`；外部反向代理至少暴露 `POST /v1/traces`。
- 不复用 `/telegraf/api`。该路径继续服务 Influx line protocol，和 OTLP 数据面完全隔离。
- Django 不接收或转发原始 Span，不进入每次请求的高吞吐数据路径。
- Collector pipeline 至少包含接收、内存限制、批处理、保留属性清理、受信来源注入、Span Metrics、尾采样和两个 exporter。
- 数据发送失败使用 Collector 自身有界队列与重试；达到资源上限后按明确丢弃策略计数和告警，不无限占用内存或磁盘。
- 请求体大小、单批 Span 数、属性数量/长度、队列容量和接入速率都必须有部署级硬上限；超限返回明确错误并产生内部指标。

### 4. Span 与 Span Metrics

原始 Span 是单次调用明细，包含 `trace_id`、`span_id`、父子关系、时间、持续时长、状态和属性，写入 VictoriaTraces。Span Metrics 是 Collector 从大量 Span 生成的计数器和延迟直方图，写入 VictoriaMetrics。

第一期派生指标维度只允许有界集合：

```text
service.namespace
service.name
service.instance.id
deployment.environment
service.version
span.kind
span.name（规范化后的端点）
status.code
bk.ingest_source.id（受信来源）
```

- 禁止把 `trace_id`、`span_id`、完整 URL、用户 ID、订单 ID、异常消息等无界属性放入指标标签。
- HTTP 端点优先使用低基数 `http.route`；缺失时使用经规范化的 span name，不得直接使用含路径参数或查询串的 URL。
- 请求量使用入口 SERVER/CONSUMER Span；错误按 `span.status=ERROR` 或协议明确的服务端错误状态统一计算；延迟使用直方图，P95/P99 必须由分布聚合，不能平均各实例百分位。
- 服务 RED 查询必须携带环境和时间窗。实例视图额外按 `service.instance.id` 过滤。

### 5. 采样与保留

- Span Metrics 在采样前从全部 Span 生成，保证 RED 不因原始 Trace 采样而失真。
- Collector 使用尾采样：错误 Trace 100% 保留，超过慢阈值的 Trace 100% 保留，普通 Trace 默认保留 10%。慢阈值和普通采样率通过部署配置提供安全默认值。
- 第一阶段不同时启用探针头采样与 Collector 尾采样的复杂组合；若客户已有上游采样，UI 必须明确指标和 Trace 可得性的影响。
- 默认保留期：VictoriaTraces 7 天、VictoriaMetrics 30 天、APM 告警与 Issue 元数据 90 天；服务、实例和权限元数据长期保留。
- 第一阶段 VictoriaTraces 使用统一保留期，不实现“错误/慢 Trace 比普通 Trace 保存更久”的多层存储。保留期由部署环境变量配置，不在第一期 UI 中修改。

### 6. 元数据发现与对账

Collector 不同步调用 Django 创建服务或实例。`TelemetryCatalogReconciler` 在运行期周期性读取最近活跃的资源维度/实例信息指标，并幂等 upsert PostgreSQL 元数据：

- 以唯一约束仲裁服务和实例并发发现；同一批和重复任务不会产生重复记录。
- `first_seen_at` 在首次发现时写入后不后移，`last_seen_at` 单调前进。
- 根据受信 `bk.ingest_source.id` 解析接入方式，并为新实例复制当时的接入源组织。
- 服务不存在时与首个实例在同一数据库事务内创建，并复制该实例组织作为服务初始组织。
- 对账失败只记录健康状态并按有界退避重试；不得阻断 API、Worker 或 Server 启动。
- 查询结果允许存在短暂的“Trace 已落库、目录尚未发现”窗口，接入页说明通常在 1–2 分钟内可见。

### 7. 深模块与存储端口

`apps.apm` 对外提供四个深模块：

1. `IngestSourceService`：创建、轮换、禁用接入源，管理默认组织，生成接入片段和校验机器凭证；隐藏摘要、轮换并发、审计和模板参数。
2. `TelemetryCatalogService`：发现、查询、归档服务与实例，管理服务/实例组织；隐藏身份规范化、继承/自定义权限、首次实例规则和状态机。
3. `TelemetryQueryService`：提供服务 RED、Trace 搜索与详情；隐藏查询语言、标签转义、时间窗/分页硬限制和外部错误映射。
4. `ApmPolicyService`：管理策略、周期评估和 APM 自有告警生命周期，并按策略通知配置发布标准事件；隐藏查询公式、连续命中、恢复、防重复与投递补偿。

外部存储通过小接口隔离：

```python
class TraceStore(Protocol):
    def search(self, query: TraceSearchQuery) -> TracePage: ...
    def get_trace(self, trace_id: str) -> TraceDetail | None: ...

class MetricStore(Protocol):
    def service_red(self, query: ServiceMetricQuery) -> ServiceRed: ...
    def instance_activity(self, query: InstanceActivityQuery) -> list[InstanceActivity]: ...

class AlertPublisher(Protocol):
    def publish(self, events: Sequence[ApmAlertEvent]) -> PublishResult: ...
```

生产适配器分别使用 VictoriaTraces、VictoriaMetrics 和系统管理通知渠道；告警中心通过用户选择的 `receive_alert_events` NATS 渠道接收事件副本。测试使用功能完整的内存适配器。View、Serializer 和 Celery task 只能调用深模块，不直接拼外部查询。

### 8. API 与权限

第一期 API 资源：

| 资源 | 核心能力 |
| --- | --- |
| `/api/v1/apm/ingest-sources/` | 列表、创建、详情、轮换、禁用、组织配置、接入片段 |
| `/api/v1/apm/instances/` | 接入实例列表、详情、组织调整、归档/解档 |
| `/api/v1/apm/services/` | 服务目录、环境视图、详情、组织调整、归档/解档 |
| `/api/v1/apm/services/{id}/metrics/` | RED 时序与 Top 端点 |
| `/api/v1/apm/traces/` | 有界时间窗、游标分页的 Trace 搜索 |
| `/api/v1/apm/traces/{trace_id}/` | Trace、Span 瀑布和属性详情 |
| `/api/v1/apm/policies/` | 基础策略 CRUD、启停与测试查询 |
| `/api/v1/apm/events/` | 查询 APM 自有事件与告警生命周期 |
| `/api/v1/apm/notification-channels/` | 查询当前组织可选择的告警中心 NATS 渠道 |

- APM 菜单声明独立 View/Operate 权限；读取要求 View，接入、组织、归档和策略变更要求对应 Operate。
- 服务 API 按 `ApmServiceOrganization` 与当前团队授权；实例和 Trace API 按 `ApmServiceInstanceOrganization` 授权。通过 trace ID 直接访问也必须先解析实例并鉴权。
- 不在当前数据范围和不存在统一返回 404，避免枚举；对象可见但缺少操作权限返回 403。
- 查询必须限制最大时间窗、分页大小、返回 Span 数和属性大小；拒绝用户直接提交任意 TraceQL/PromQL。
- Span 属性默认做服务端敏感键屏蔽和长度截断；Authorization、Cookie、密码、Token 等键不可回传 UI。第一期不提供请求/响应正文采集。

### 9. 告警边界

- `apps.apm` 保存并评估错误率、P95/P99、吞吐异常/无流量三类基础策略，评估维度为服务 + 环境。
- 评估任务查询 VictoriaMetrics；查询失败时保持上次状态，记录“评估失败”并重试，不产生触发、恢复或无数据误报。
- 连续命中、恢复窗口和事件 external ID 必须幂等，任务重复执行不能创建重复告警。
- `apps.apm` 保存自身事件与告警生命周期；事件页面只查询 APM 模型，不读取其他 App 的表。
- 策略可选择系统管理中的一个或多个 `receive_alert_events` NATS 渠道。APM 以 `lite-apm` 推送方发送标准事件副本，由告警中心负责跨源聚合与事故协同，但不反向拥有 APM 告警事实。
- 未选择通知渠道时仍正常产生 APM 告警；通知失败只影响对应渠道投递状态，不影响 APM 事件和状态。
- 事务提交后通知失败必须保留待投递状态并由运行期任务补偿；不能在请求事务内同步等待通知渠道响应。

### 10. 前端范围

生产路由第一期只落地：

```text
/apm/integration/add
/apm/integration/instances
/apm/services
/apm/services/[serviceId]
/apm/traces
/apm/traces/[traceId]
/apm/events
/apm/policies
```

- 接入列表一行一个 `service.instance.id`，展示服务、应用(namespace)、环境、实例 ID、接入方式、首次/最近上报、状态和组织。
- 服务目录按逻辑服务展示；指标行按环境分开。详情页固定服务身份并允许切换环境和时间窗。
- 加载、无数据、无权限、存储不可用和部分数据状态必须可区分；不得用空数组伪装外部存储失败。
- 接入页面根据语言和运行环境生成动态实例 ID 配置，包含 OTLP 端点、协议、传播器、资源属性和 Authorization；Token 只在创建/轮换成功态显示一次。
- Storybook fixtures 与 API DTO 分离；生产页面不得 import story 文件或硬编码演示数据。

### 11. 部署、启动与降级

- 默认部署新增 VictoriaTraces、APM OTel Collector Gateway 和边缘鉴权路由；VictoriaMetrics 复用现有实例。
- VictoriaTraces 是默认 Trace Store，但 `apps.apm` 只依赖 `TraceStore` 接口。外部部署可以提供兼容适配器，不把 VictoriaTraces SDK 类型泄漏到领域层。
- `batch_init` 不探测、不创建、不等待 Collector、VictoriaTraces、VictoriaMetrics、NATS listener 或通知渠道 responder。非关键外部声明和对账全部在 Supervisor 启动后的运行期执行。
- APM 外部依赖缺失时，BK-Lite Server 正常启动；APM 健康接口和页面返回明确 degraded 状态。元数据 CRUD 仍可用，遥测查询返回可重试的 503。
- Collector、VictoriaTraces 和边缘代理各自提供健康检查、资源限制和持久卷；“端口可连接”不等同于数据可写，接入自检以成功认证和最近落库事实为准。
- 不使用 `sleep`、无限重试或延长启动超时掩盖依赖顺序。

## 实施切片

### Slice 1：骨架与契约

- 创建 `apps.apm`、菜单、权限、前端路由壳。
- 建立模型、四个深模块接口、TraceStore/MetricStore/AlertPublisher 内存适配器。
- 用 API/权限测试固定身份、组织继承和首次实例服务权限规则。

### Slice 2：真实数据面

- 增加 VictoriaTraces、Collector 和反向代理配置。
- 实现接入凭证、受信来源注入、实例 ID 动态模板、全量 spanmetrics 和尾采样。
- 用真实容器契约测试验证 OTLP → Trace/Metric 两条链路以及伪造属性被覆盖。

### Slice 3：目录与 RED

- 实现运行期目录对账、接入实例列表、服务目录、环境视图和 RED 查询。
- 覆盖 Pod 重建、并发首次发现、继承/自定义组织、静默/归档/解档。

### Slice 4：Trace 诊断

- 实现 Trace 搜索、详情、瀑布图、Span 属性与敏感字段屏蔽。
- 从服务异常时间窗携带服务/环境条件跳转到 Trace 搜索。

### Slice 5：基础告警

- 实现三类基础策略、评估任务、APM 自有告警生命周期、幂等事件和通知渠道补偿投递。
- APM 事件页读取本 App 数据；告警中心仅作为可选 NATS 通知渠道。

## 必须覆盖的验收场景

1. `/telegraf/api` 保持 Influx 行为；OTLP/HTTP `/v1/traces` 和内部 4317/4318 独立工作。
2. 无 Token、错误 Token、禁用源和伪造内部来源字段均被拒绝或覆盖；明文 Token 不落库、不进日志，只显示一次。
3. 三个同 namespace/name、不同 instance ID 的 Pod 在接入列表显示三行，在服务目录聚合成一个逻辑服务。
4. Pod 重建产生新实例；旧实例静默并归档，新实例继承接入源组织，历史实例不被覆盖。
5. 新实例默认继承多个组织；改为自定义后不再被接入源权限更新覆盖；当前权限调整同时影响历史和未来实例明细访问。
6. 服务复制首个实例组织且以后不随实例权限变化；有服务权限但无某实例权限时可见全局聚合、不可见该实例和 Trace。
7. 同一服务的 production/testing 指标分开；“全部环境”列出环境视图而不混算健康值。
8. Span Metrics 基于采样前全量 Span；错误/慢 Trace 全保留，普通 Trace 按配置比例保留。
9. RED 查询不平均实例百分位；无界属性不进入指标标签；动态 URL 不导致指标基数无界增长。
10. 缺少 instance ID 的 Span 可在服务和 Trace 中出现，但不生成伪实例，并可观察身份诊断。
11. Trace 直接访问经过实例组织鉴权；越权和不存在返回不可枚举结果；敏感属性不回传。
12. 评估重复执行不重复告警；VictoriaMetrics 查询失败不误触发或误恢复；通知渠道投递失败可补偿。
13. Collector、VictoriaTraces、VictoriaMetrics、NATS 或通知渠道不可用均不阻断 Server 启动；未安装 Alerts 时 APM 全部领域功能仍可用；`batch_init` 不调用任何运行期进程。
14. 外部存储失败与合法空数据在 API 和 UI 中有不同状态；查询时间窗、分页和响应大小都有硬限制。
15. 生产页面使用真实 API，无 Storybook fixture 泄漏；中英文菜单、权限和主要空/错/加载态均有覆盖。

## Out of Scope

- APM 首页综合看板、服务拓扑、SLO、Issue 聚类/回归、运行时指标和智能归因。
- eBPF、Kubernetes Operator、完整 OTel Collector 管理和远程探针下发；第一期页面可保留“即将支持”但不能伪装可用。
- 用户自定义 TraceQL/PromQL、任意高基数指标标签和请求/响应正文采集。
- 按错误/慢/普通 Trace 使用不同物理保留层、用量计费、软硬配额和自动成本治理。
- 跨服务实例权限过滤后的服务聚合；服务聚合明确全局，不受实例组织权限影响。
- 把 APM 服务同步为 CMDB 服务或 Monitor 监控实例。

## Further Notes

- 本规格覆盖并修正 `spec/requirements/APM` 中“接入列表按服务键聚合”“接入页不签发凭证”“Service 表同时保存接入方式与实例状态”等旧口径。产品 PRD 应在实现前同步修改，避免双重契约。
- 默认 VictoriaMetrics 当前部署保留期为 30 天；VictoriaTraces 尚未进入仓库部署资产。
- 本设计遵守 Server 启动约束：所有遥测目录对账、通知渠道投递和外部健康检查都属于运行期、可重试、非启动硬门禁。
