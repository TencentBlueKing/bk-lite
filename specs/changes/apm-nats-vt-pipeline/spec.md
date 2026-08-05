# APM 多云区域 NATS 与 VictoriaTraces-only 数据链路

Status: accepted

## 目标

把 APM 数据面收敛为一条跨云区域、可部署、可重复验证且只有一个遥测事实源的链路：

```text
OTel SDK / Agent
  → 所选云区域的区域 Collector（OTLP 4317/4318）
  → NATS JetStream subject apm.traces.<cloud_region_id>
  → 系统级 Collector
  → VictoriaTraces
  ← apps.apm VictoriaTracesTelemetryStore 受控查询
```

APM、Monitor、Log 是同级产品域：Monitor 只使用 VictoriaMetrics，APM 只使用 VictoriaTraces，Log 只使用 VictoriaLogs。NATS 是区域到中心的长期遥测传输模块，不是临时转发层。运维负责生产 Stream、系统级 Collector、VictoriaTraces、容量和告警；研发交付区域发布能力、中心消费能力、传输契约、参考部署、本地契约验证以及 Server/Web 查询闭环。

## 非目标

- 不引入 `ApmIngestSource`、APM Token、浏览器可提交的 endpoint 或持久化接入配置。
- 不复用 `/telegraf/api`，不改变 Monitor 的 VictoriaMetrics 或 Log 的 VictoriaLogs 配置和数据。
- 不保留独立 APM Edge Nginx，不在 Django 中接收、转发或保存原始 Span。
- 不生成 Span Metrics，不运行 metrics pipeline，不执行尾采样；默认全量 Trace 进入 VT。
- 不在 `batch_init`、迁移或 Server 启动钩子创建 Stream、等待 Collector 或探测 VT。
- 不在本变更顺手实现 APM 首页、任意 LogsQL/TraceQL 输入或无关 Storybook 差距。

## 基线审计

| 域/链路 | 当前事实 | 本变更差异与复用 |
| --- | --- | --- |
| APM 接入 | `integration-config` 仍接受浏览器 endpoint；页面按浏览器 hostname 拼 4318；配置无状态、无 Token；Shell/Docker 混合单双引号存在注入风险 | 保留应用与无状态片段；新增受权限保护的云区域选择，Server 从 NodeMgmt 云区域 envconfig 解析两个 endpoint；所有 shell 值统一安全引用 |
| APM 数据面 | `deploy/apm` 为 Edge Nginx → 单个 contrib Collector → VT/VM；Collector 先 spanmetrics、后 tail sampling；compose 含 standalone VM | 删除 Edge、spanmetrics、tail sampling、metrics pipeline 和 VM；拆成区域发布与中心消费两种角色 |
| APM 查询 | `TraceStore` 查 VT，`MetricStore` 查 VM；目录、RED、SLO、策略依赖 VM；拓扑逐 Trace 详情扫描 | 用一个 `TelemetryStore` interface 隐藏 VT 的 Jaeger/LogsQL 查询；dependencies 接口替代 N+1 拓扑扫描 |
| Monitor 区域解析 | `TemplateAccessGuideService` 通过 `apps.rpc.node_mgmt.NodeMgmt.get_cloud_region_envconfig` 读取受信 `SidecarEnv`，校验 `NODE_SERVER_URL` 后构造固定 `/telegraf/api` | 复用受信 envconfig 获取模式和显式错误语义，但 APM endpoint 必须读取完整的 `APM_OTLP_HTTP_ENDPOINT` / `APM_OTLP_GRPC_ENDPOINT`，不从 hostname 或 `NODE_SERVER_URL` 猜测 |
| Monitor NATS | NodeMgmt Telegraf 以环境注入 NATS TLS/用户名密码，向 `metrics.<node>` 发布 Influx；系统 Telegraf 使用 `nats_consumer` 消费 `metrics.*` | 复用现有 Broker、认证与区域 envconfig；APM 使用独立受限 `apm.traces.*` Subject 和 OTLP Protobuf，不复用 metrics payload |
| Log NATS | Vector 使用相同区域 NATS 凭据体系，JSON 日志通过独立 Subject 传输；配置/测试验证环境变量完整性 | 复用凭据注入、TLS 和缺失配置失败模式；不复用 JSON 编码或 Log Subject |
| 官方 Collector | `otelcol-contrib` 0.153.0 的官方 builder manifest 无 NATS trace receiver/exporter；仓库只引用官方镜像，没有 Collector Go 模块 | 使用 Go 1.25 容器可重复构建 BK-Lite 自定义发行版，新增 traces-only JetStream exporter/receiver；不伪造 YAML 组件 |

## 领域与身份不变量

- 普通 APM 应用由用户创建；平台提供不可删改的内置“未归类应用”。非空 `service.namespace` 必须等于一个当前可见的普通应用 ID，空值归入未归类应用，非空未知值不得进入目录并产生有界诊断计数/日志。
- APM 服务由 `service.namespace + service.name` 发现；实例由服务身份 + `service.instance.id` 发现；版本和环境是查询维度。
- 区域 Collector 删除客户端提交的全部 `bk.*` 保留属性后注入可信 `bk.cloud_region.id`。组织 ID、NATS 凭据和 endpoint 不进入 Span。
- 应用组织更新必须在一个事务内同步继承态实例和该应用下服务的 `ApmServiceOrganization`；自定义实例组织仍不被覆盖。
- 原始 Span 不写 PostgreSQL；目录、策略、SLO、告警和通知生命周期仍由既有 Django 领域模型持有。

## 云区域接入 interface

### 请求

`POST /api/v1/apm/integration-config/` 只接受：

- `application_id`
- `cloud_region_id`
- `language`、`runtime`
- `service_name`、可选 `service_version`
- `environment`

客户端不得提交 endpoint。Server 通过 NodeMgmt 公开 interface 读取该区域受信 envconfig：

- `APM_OTLP_HTTP_ENDPOINT`：绝对 `http`/`https` URL；仅允许空路径或 `/v1/traces`，响应和片段统一为可直接使用的 OTLP HTTP endpoint。
- `APM_OTLP_GRPC_ENDPOINT`：绝对 `http`/`https` URL，必须包含主机和显式或默认端口，不允许 userinfo、query、fragment。

区域不存在、无查看权限、变量缺失或格式非法分别返回稳定 404/403/400，不回退到浏览器 hostname、Server hostname 或 `/telegraf/api`。响应包含区域 ID/名称、HTTP/gRPC endpoint、标准 OTEL 环境变量与 Shell 片段，但不包含 NATS 配置或凭据。

### Shell 安全

所有用户或配置值通过单一 POSIX shell literal 函数引用；不得把内容插入已有单引号字符串。Docker `sh -c` 脚本和 `-e` 参数分别引用，恶意值中的单引号、换行、`$()`、反引号、反斜杠和 shell 元字符均只能成为字面量。复制失败、生成失败和 endpoint 缺失有显式 UI 状态。

## JetStream 传输 interface

### Subject 与载荷

- 发布：`apm.traces.<cloud_region_id>`；`cloud_region_id` 规范化为十进制 CloudRegion 主键。
- 中心过滤：`apm.traces.>`；生产发布凭据只允许自身精确 Subject，中心凭据只允许消费 APM Stream。
- payload：未经 JSON 转换的 OTLP Protobuf `ExportTraceServiceRequest`，`Content-Type: application/x-protobuf`。
- headers：`BK-Cloud-Region-Id`、`BK-OTLP-Schema-Version: 1`、`Nats-Msg-Id`。消费者必须拒绝 header、Subject 区域与 payload 中受信区域标识不一致的消息。
- 单消息上限、每批 Span 数和属性上限在进入 NATS 前执行；超限是可观察的拒绝/丢弃，不允许无界分配。

### 交付、确认与重复

- exporter 使用 JetStream publish interface 并等待持久化 ACK；Core NATS publish 不满足契约。超时或无 ACK 返回错误，由 Collector 有界持久队列重试。
- `Nats-Msg-Id = sha256(schema_version + cloud_region_id + protobuf_payload)`；Stream duplicate window 抑制同一批发布重试。
- receiver 使用 durable pull consumer、`AckExplicit`；只有 Collector 下游 `ConsumeTraces` 成功返回后才 `AckSync`。VT 不可用、超时或 Collector 停止时不 ACK，并按有界 backoff 重投。
- 端到端语义是至少一次。VT 接受后到消费 ACK 持久化前仍有崩溃窗口，物理重复不可被宣称为 exactly-once。Trace 详情按 `trace_id + span_id` 去重；目录由服务/实例唯一约束幂等；所有 RED、端点、SLO、策略和错误聚合在 VT 查询中先按 `trace_id + span_id` 去重，且查询有唯一 Span 数上限。重投不得造成目录重复或派生统计双计数。
- 达到 `max_deliver` 的消息保留在有界 Stream 中并发出 advisory/指标，由运维处置；不能无限重投，也不能 ACK 后静默丢弃。

### 有界配置

仓库提供 Stream/Consumer 参考契约，生产由运维创建：

| 项 | 默认参考值 | 语义 |
| --- | --- | --- |
| Stream subjects | `apm.traces.*` | 单 token 区域 Subject |
| retention/storage/replicas | limits/file/1（生产按容量调副本） | 不创建第二套 Broker |
| max bytes | 256 MiB（本地参考） | 超限 `discard old` 并告警；生产必须按容量测算调整 |
| max age | 24h | 中心中断后的最大区域缓冲 |
| max message size | 8 MiB | 与 OTLP 请求上限一致 |
| duplicate window | 2m | 覆盖短时区域 exporter publish 重试 |
| ack wait | 60s | 下游超时上界以上 |
| max deliver | 8 | 有界重投并产生 max-delivery advisory |
| max ack pending | 256 | 中心消费背压 |

必须暴露发布成功/失败/重复、队列深度/丢弃、消费成功/失败/重投、pending/lag、max-delivery、下游延迟与最后成功时间指标。容量告警至少覆盖 Stream 70%/85%、消息年龄逼近 max age、区域本地队列 70%/85%、持续发布失败和 VT 持续拒绝。

## Collector 角色

### 区域 Collector

直接监听可配置内网地址的 OTLP gRPC 4317 和 HTTP 4318，依序执行：

1. memory limiter；
2. 删除 span/event/link/scope/resource 的 `bk.*` 与敏感键，删除请求/响应正文和完整 URL；
3. 注入 `bk.cloud_region.id`；
4. 限制资源/Span/Event/Link 属性数量为 64/100/32/32，字符串长度 4096，批次与请求体不超过部署上限；
5. batch；
6. 写入启用 file storage 的有界 exporter queue，重试并等待 JetStream ACK。

区域 Collector 不连接 VT/VM，不含 tail sampling、spanmetrics 或 metrics pipeline。NATS URL、TLS CA、用户名密码只由环境注入，参考现有 NodeMgmt 区域 NATS 配置；配置和日志不得回显秘密。

### 系统级 Collector

使用自定义 NATS receiver 消费 `apm.traces.>`，校验 headers/Subject/protobuf 和资源中的区域身份，将 traces-only pipeline 交给 OTLP HTTP exporter 写 VT。只有下游接受后才确认 JetStream 消息。中心不创建 Stream，不在启动前等待 VT；Collector 自身失败和重启由部署编排治理。

## VictoriaTraces-only 查询 interface

`VictoriaTracesTelemetryStore` 是 `apps.apm` 的唯一生产遥测 Adapter。领域调用方只能提交类型化 query DTO，不能提交 LogsQL、TraceQL 或 URL。Adapter 隐藏并统一：

- Trace 搜索、详情与去重；
- 服务 RED summary/timeseries、P95/P99、端点聚合；
- 最近服务、版本、实例、环境活动；
- SLO 可用性和时延阈值统计；
- 策略当前窗口评估；
- 错误视图的有界聚合基础；
- `/select/jaeger/api/dependencies` 服务图查询。

每个查询模板必须转义字段值，时间窗不超过 35 天，分组/唯一 Span/结果数量有硬上限，HTTP 连接与读取有超时，响应体有大小上限。合法无样本返回 `no_data`；连接、超时、非法上游响应返回 `degraded/unavailable`，不得伪装空数据。Trace 详情先按可见服务/实例做不可枚举授权，再做属性脱敏和响应截断。

VT 开启 `-servicegraph.enableTask=true`。拓扑使用 dependencies 接口，不逐条获取 Trace 详情；结果仍按当前组织可见 `ApmServiceOrganization` 过滤。由于 Jaeger dependencies 只返回 `service.name`，同名服务横跨多个 namespace 时结果无法安全归属，Adapter 必须省略歧义节点/边并返回诊断标记，不能合并或泄漏。

当前产品支持 rolling 7d、rolling 30d 和 calendar month SLO，因此 VT 默认保留期设为 35d，覆盖最长 31 天窗口和调度余量；部署若配置更短保留期，健康状态必须 degraded，并禁止把不完整窗口标为 available。

## 运行期发现、评估与一致性

- 目录对账、服务 RED、端点、SLO 和策略任务全部切到 `TelemetryStore`；不改变 Django 模型和 ADR 0004 告警生命周期。
- 目录接纳 `service.namespace` 对应已有应用的数据，并把空 namespace 归入内置“未归类应用”。非空未知 namespace 逐项跳过，不阻断同批有效应用，并更新 `unknown_application` 诊断计数与采样日志。
- “未归类应用”复用现有应用组织过滤，其组织范围始终是普通 APM 应用当前组织的并集；组织变化同时同步到已发现的未归类服务和继承态实例。
- VT 查询失败保留原始异常类型和稳定错误码，运行期有界重试；失败不能推进归档游标、触发/恢复告警或把 SLO 标成 no_data。
- 应用组织更新在事务锁内重读应用，原子替换应用组织、继承态实例组织和服务组织；失败整体回滚。

## 健康与启动语义

APM 健康模型包含：区域 Collector 接收/清洗、本地发布队列、NATS publish ACK、JetStream backlog/max-delivery、系统级 Collector 消费/下游写入、VictoriaTraces 查询/保留期、目录对账、策略评估和通知投递。移除 APM Edge、APM VictoriaMetrics 和 spanmetrics 状态。

所有数据面检查只在运行期执行。`batch_init`、数据库迁移、API/Worker/Beat/Listener 启动不连接 NATS、Collector 或 VT，不声明 Stream/Consumer。外部依赖异常只使 APM degraded；API 的元数据能力继续可用，遥测查询返回明确 503/降级状态。

## 安全

- endpoint 只来自受信云区域 envconfig；客户端不能影响出站目标，避免 SSRF 和伪造区域。
- NATS 凭据、TLS 私钥/CA 和 VT 地址由环境注入，不提交 `.env`、keystore、Token 或环境专属地址。
- NATS 区域发布 ACL 精确到单 Subject；中心只读 APM Stream；Stream/Consumer 管理凭据与运行凭据分离。
- payload、属性、批次、队列、查询窗口、响应大小和并发均有上界；敏感字段删除发生在持久队列和 NATS 之前。
- Server 数据库仅使用 Django ORM；无 raw SQL、`.raw()`、`RawSQL` 或 `cursor.execute`。

## 迁移与回滚

1. 先发布兼容 Server/Web：接入请求改用 cloud region，VT Adapter 就绪但旧任务尚可回滚。
2. 运维创建有界 Stream/Consumer、部署中心 Collector 和 35d VT，开启 service graph；重复执行与存量同名漂移必须由运维预检，不在 Server 启动期自动修正。
3. 按区域部署新 Collector，验证 publish ACK、积压与中心写入后切换 4317/4318；移除 Edge 路由。
4. 停止 APM spanmetrics/VM 写入，再切目录/RED/SLO/策略读取到 VT；观察至少一个最大策略窗口后才清理 APM 专用 VM 配置。Monitor 的 VM 数据、配置和保留期绝不删除。
5. 删除 compose 中 Edge、standalone VM、APM VM env/健康项和旧 tail-sampling 配置。旧镜像/配置至少保留一个发布窗口，可通过回滚镜像与恢复旧路由恢复；VT 全量数据不删除。

应用模型升级时创建内置“未归类应用”、回填空 namespace 服务并移除应用启用字段。数据库降级只移除内置标识字段，保留该应用、组织关系和目录数据，避免回滚过程删除可恢复的历史目录。

迁移失败时停止切流并恢复上一版本区域入口/读路径。Stream 和 VT 数据属于可恢复运行数据，删除或缩短保留期是运维显式操作，不由应用升级执行。

## 容量模型

生产容量至少按以下参数估算并记录：峰值 spans/s、平均 protobuf bytes/span、batch 大小、区域断连容忍时长、中心消费倍数、VT 每 span 磁盘放大、35d 保留期、副本数和 30% 安全余量。参考公式：

```text
JetStream bytes ≈ peak_ingest_bytes_per_second × outage_seconds × replicas × 1.3
VT bytes ≈ average_ingest_bytes_per_day × retention_days × storage_amplification × replicas × 1.3
```

区域 file queue、Stream max bytes/max age 和 VT `storage.minFreeDiskSpaceBytes` 必须共同配置；任何一层达到丢弃条件都产生明确指标与告警。

## 测试 seam 与验收

TDD 只在以下已确认 interface 上测试，不耦合内部实现：

1. `POST /api/v1/apm/integration-config/`：权限、区域、endpoint、Shell 安全和响应 DTO。
2. 自定义 Collector 的 exporter/receiver：OTLP Protobuf、Subject、headers、publish ACK、显式 ACK、重投、清洗和资源边界。
3. `TelemetryStore`：受控 VT 请求构造、映射、去重、no_data/degraded、目录/RED/SLO/策略/错误/拓扑。
4. APM Web 接入页：区域选择、空/错/权限态、表单、复制和 Storybook/生产一致性。
5. APM 应用与目录：内置标识和不可修改、空 namespace 归类、非空未知 namespace 拒绝，以及 Web 只读呈现。

### 分阶段实施清单

- [x] 阶段 0：审计 APM/Monitor/Log；更新术语；新增本 spec 与 ADR 0006；废弃冲突规格。
- [x] 阶段 1：云区域接入 API/UI、受信 endpoint、Shell 安全和前后端测试。
- [x] 阶段 2：自定义 Collector、JetStream interface、区域/中心参考配置、Edge 删除和容器契约。
- [x] 阶段 3：VT-only Adapter、任务切换、dependencies、35d 保留期和组织一致性。
- [x] 阶段 4：健康、迁移、升级/回滚和可靠性故障语义。
- [x] 阶段 5：单元/接口/容器/故障/数据正确性/Web 与 Storybook 全量验证。

### 完成门槛

- HTTP 以及 Collector 支持的 gRPC OTLP 从区域入口经真实 JetStream 到 VT 成功，链路中无 Edge、VM、spanmetrics、tail sampling。
- NATS 断开时区域本地持久排队并恢复；中心停止时 Stream 有界积压并恢复；VT 不可用时消息不 ACK；达到上限/max-delivery 有指标和确定语义。
- 同一消息重投不产生目录重复，RED/SLO/策略对唯一 Span 的统计不双计；空 namespace 进入内置未归类应用，非空未知应用不入目录且可诊断。
- 全量请求数、错误率、P95/P99、服务/版本/实例发现、Trace、依赖图和 SLO 由 VT 数据对账正确。
- Web 可选择有权限云区域、显示服务端 endpoint、生成并安全复制配置；缺配置和越权有明确状态；Storybook 不再出现 `/telegraf/api` 或 hostname 拼接。
- 服务目录的应用视角以应用目录为事实来源；即使尚未发现任何空 namespace 服务，也显示零服务的内置“未归类应用”，不得只从服务列表反推应用。
- 使用 Makefile 启停 Server API/Worker/Beat/Listener；启动前无重复进程。外部数据面停止不阻断启动，只产生 APM degraded。
- 每阶段有新鲜聚焦测试和中文提交；最终列出提交、命令结果、运维待办与限制，不自动推送或合并。
