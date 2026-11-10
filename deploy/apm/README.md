# BK-Lite APM 数据面契约夹具

本目录**不是**生产编排手册，也不替运维设计流水线。它只提供：

1. **硬契约**：链路拓扑、协议、ACK、清洗与安全边界；
2. **产品自有组件**：BK-Lite traces-only Collector 发行版与参考配置；
3. **可重复验证**：本地/CI 用 Compose 证明契约成立。

生产上的 NATS Stream、VictoriaTraces、系统级 Collector、容量、告警与发布流水线由运维按自身平台落地；须满足本文与 [ACCEPTANCE.md](./ACCEPTANCE.md)（原上线验收清单）中的约束，编排方式自选。

正式链路：

```text
OTel SDK / Agent
  -> 区域 Collector（OTLP 4317/4318；产品页只生成 4318）
  -> NATS JetStream apm.traces.<cloud_region_id>
       -> 系统级 Collector -> VictoriaTraces
       -> 聚合 Collector -> 独立聚合库
```

调用链明细只写 VictoriaTraces。入口 Span 的累计计数、耗时直方图和晚到计数由独立的聚合 Collector
写入独立聚合库，不写入 Monitor 的 VictoriaMetrics，也不复用 `VICTORIAMETRICS_HOST`。两个 Collector
各自 ACK。VictoriaTraces 故障只重投明细消费者，不会让聚合把同一批 Span 再算一次。不做尾采样，
也不包含独立 APM Edge Nginx。`/telegraf/api` 仍只属于 Monitor。APM 从未正式部署，不存在旧数据面迁移。

职责边界见 [ADR 0006](../../docs/adr/0006-apm-regional-nats-victoriatraces-pipeline.md)、
[ADR 0008](../../docs/adr/0008-apm-trusted-regional-ingress.md)、
[ADR 0011](../../docs/adr/0011-apm-rum-aggregate-metrics-store.md) 与
`docs/design/product-decisions/apm-data-plane.md`。

## 目录与角色

| 路径 | 归属 | 说明 |
| --- | --- | --- |
| `collector/` | 研发（产品组件） | 固定 OTel Collector `0.153.0` 的 BK-Lite 发行版；JetStream exporter/receiver、`trace_guard` |
| `otel/regional.yaml` / `otel/system.yaml` / `otel/aggregate.yaml` | 研发（契约参考配置） | 区域清洗/排队、中心消费写 VT、聚合消费写聚合库的行为基线；生产可换编排，语义须等价 |
| `nats/nats-server.conf` | 契约夹具 | 本地最小权限示例，**不是**生产凭据或生产 NATS 拓扑 |
| `compose.yaml` + `Makefile` | 契约夹具 | 仅本地/CI 验证；**不是**生产 Compose 真相源 |
| `.env.example` | 契约夹具 | 隔离环境默认值；生产 Secret 由运维注入 |

Server 运行期查询与健康探测模板：
[`server/support-files/env/.env.apm.example`](../../server/support-files/env/.env.apm.example)。
这些 endpoint 只由运行期任务使用，不参与 Server 启动。

## 传输契约（硬约束）

- Subject：区域仅可发布 `apm.traces.<自身区域>`；中心订阅 `apm.traces.>`。
- Payload：OTLP Protobuf `ExportTraceServiceRequest`，`Content-Type: application/x-protobuf`。
- Headers：`BK-Cloud-Region-Id`、`BK-OTLP-Schema-Version: 1`、`Nats-Msg-Id`。
- `Nats-Msg-Id` 是 schema、区域和 Protobuf 正文的 SHA-256；Stream duplicate window 抑制
  publish 重试。端到端至少一次；Server 聚合按 `trace_id + span_id` 去重。
- 非法 Subject、区域 header、schema、Content-Type 或 Protobuf 为 poison message，终止投递；
  VT 不可用为可重试失败，消息不 ACK。
- 运行身份不得拥有 Stream/Consumer 管理权限。区域 publish ACL 精确到自身 Subject；中心只需
  Stream/Consumer info、pull、ACK 与 inbox。

## 入口与清洗（硬约束）

- 受管区域代理正式包含区域 Collector 与宿主机 4318 映射；4318 仅受信区域内网可达
  （ADR 0008）。无应用级 Token；公网/跨租户接入当前不支持。
- Server 固定生成 `http://<receiver_host>:4318/v1/traces`，客户端不得提交 endpoint。
- `trace_guard`：删除客户端 `bk.*` 与敏感键后注入可信 `bk.cloud_region.id`；属性与字符串长度有界。
- 区域队列与 JetStream 均有 bytes/age/message 硬上限；满载拒绝或丢弃须可观测，禁止无界膨胀。

## 运维须满足、但自行编排

- 有界 `APM_TRACES` Stream，以及 `BKLITE_APM_SYSTEM`、`BKLITE_APM_AGGREGATE` 两个 durable consumer（语义见验收清单）。
- VictoriaTraces 保留期 ≥ 35 天，并启用 service graph 任务；APM 唯一遥测事实源。
- 容量下界与告警门槛见 [CAPACITY.md](./CAPACITY.md)；本地 256 MiB Stream 仅契约测试。
- 验收与回滚约束见 [ACCEPTANCE.md](./ACCEPTANCE.md)。**如何**用 Helm/Ansible/现有流水线落地不在本目录规定。

## 入口聚合

`APM_TRACES` 上有两个 durable consumer，各自拉取、各自 ACK：

| Consumer | 进程 | 投递策略 | ACK 等待 | 重投上限 |
| --- | --- | --- | --- | --- |
| `BKLITE_APM_SYSTEM` | 系统 Collector | `deliver all` | `APM_NATS_ACK_WAIT`，默认 `60s` | `APM_NATS_MAX_DELIVER`，默认 `8` |
| `BKLITE_APM_AGGREGATE` | 聚合 Collector | `deliver new` | `APM_AGG_NATS_ACK_WAIT`，默认 `30s` | `APM_AGG_NATS_MAX_DELIVER`，默认 `3` |

两个消费者都过滤 `apm.traces.>`，显式 ACK，pull。`max ack pending` 仍共用 `APM_NATS_MAX_ACK_PENDING`
（默认 256），与各自接收器的 `pull_max_messages` 对齐。仓库里的 NATS ACL 已用
`$JS.API.CONSUMER.*.APM_TRACES.*` 通配，不按 consumer 名收紧。生产账号如果按名字授权，要给
`BKLITE_APM_AGGREGATE` 补上 info、pull 和 ACK。

`deliver new` 只在消费者第一次创建时生效：不回放当时已经在 Stream 里的消息。积压的结束时间往往已经超过
5 分钟，回放会全部记成晚到；即便还没超过，也会把系统 Collector 已经处理过的历史再算一遍。初始化命令先
`consumer info`，同名消费者已存在时不会改写投递策略。不要删掉重建，否则重建时刻之前的消息不会进入聚合。

ACK 等待和重投上限与系统消费者分开。系统侧 60 秒和 8 次是为了盖住 VictoriaTraces 导出重试
（`max_elapsed_time` 30 秒，接收器 `downstream_timeout` 45 秒）期间的 NAK。聚合流水线正常不把导出失败退回
接收器，重投只发生在进程崩溃，或处理卡住超过 ACK 等待。默认 30 秒短于系统侧，也长于聚合配置里写死的
`downstream_timeout` 20 秒，避免还在处理时被重投。把 `APM_AGG_NATS_ACK_WAIT` 调到 20 秒或更短会打破这个关系。
重投上限取 3 而不是 1：1 是最多一次，每次正常重启都会丢掉已拉取未 ACK 的消息。3 表示正常投递之外再给两次，
用来盖住崩溃后的在途消息，然后终止，避免崩溃循环按 8 次把同一批 Span 计入请求数。重复范围是当时尚未 ACK
的在途消息，不是整条 Stream。

系统 Collector 的 `otel/system.yaml` 只有一条流水线：`memory_limiter` 之后写入 VictoriaTraces。
它不读取聚合库地址、分片或认证变量，这些变量为空也不影响明细入库。

聚合 Collector 使用同一镜像和 `otel/aggregate.yaml`。入口只有一条流水线，顺序是
`memory_limiter` → 只留 `SERVER` / `CONSUMER` → 用 `keep_keys` 把资源属性收窄到
`service.namespace`、`service.name`、`deployment.environment` → `routing` 连接器。
v0.153 的 `routing` 支持 Span 上下文，默认动作为 `move`：晚到 Span
（`span.end_time_unix_nano < UnixNano(Now()) - 300000000000`）移到 `count/late`，其余进入
`span_metrics`。过滤和收窄只跑一遍，不会再把整批克隆给两条流水线各自过滤。
`memory_limiter` 在任何计数之前。它拒收时只 NAK 聚合消费者，这条消息还没被计入；恢复后只算一次。

晚到指标名是 `apm_aggregate_late_spans_total`。写出前经过 `batch`、把样本时间改成处理时刻、再
`deltatocumulative`。count 默认把时间打在 Span 结束时间上；晚到 Span 已经超过 5 分钟，不改的话即时查询看不到。
`batch` 同时吃掉导出错误。不这样做的话，count 的失败会经 `routing` 返回接收器，同一条消息里已经进入
`span_metrics` 的 Span 会随 NAK 再算一次。`span_metrics` 本身不把 remote write 失败交回 traces。
因此聚合库不可达时两个消费者都 ACK，VictoriaTraces 不因此把同一条 Span 写两次。

`span_metrics` 的指标前缀是 `apm_`。它排除 `span.kind` 和 `collector.instance.id`，关闭
exemplars，直方图单位是 `ms`，桶从 `5ms` 到 `10000ms`。资源分组键是上面三个资源属性，同一个服务的多个
`service.instance.id` 只产生一组序列。`aggregation_cardinality_limit` 默认 500，按每服务资源计算
（命名空间 + 服务名 + 环境），不是全局。大约相当于 166 个入口操作乘 3 种状态。超出的组合并进一条
`otel.metric.overflow=true` 序列。这条序列只有该标记，不再带服务名、环境和操作名；`job` 仍是
「命名空间/服务名」。Server 查询仍按服务名和环境，不改成按 `job`。

`series_expiration` 默认 1 小时（`APM_AGG_SERIES_EXPIRATION`）。一条序列这么久没有新 Span，就从聚合进程
内存删掉，组合名额释放给后来的接口。再出现时计数从 0 开始，`increase()` 按计数器重置处理。这不是按服务资源
过期：空闲服务资源仍占 `resource_metrics_cache_size` 的名额，直到缓存换出。该缓存显式设为 1000，与容量文档一致。
不设置 `metrics_expiration`，避免一整份服务资源被时间删掉。
Prometheus 侧允许的业务标签是服务命名空间、服务名、环境、入口操作和状态；另有去不掉的 `job`
以及 `shard`。不应出现 `instance`、`collector.instance.id`、`target_info` 或 scope 标签。

remote write 写入 `AGG_VICTORIAMETRICS_WRITE_URL`。`external_labels.shard` 来自 `APM_AGG_SHARD`，
每个聚合进程一个固定值，重启不变，进程之间互不相同。不要用 Span 上的 `service.instance.id` 充当分片。
`resource_to_telemetry_conversion`、`target_info` 和 scope 标签都关闭。区域 Collector 和系统 Collector
都不写聚合库。

刷出间隔默认 60 秒（`APM_AGG_FLUSH_INTERVAL`）。容量估算按这个间隔；缩短后磁盘按比例增加。
Server 用同名变量对齐查询结束时间。改这个值必须同时改采集端和 Server。
本地夹具可以把该变量设为 `1s`。

容量压测里聚合状态大约增加 236 MiB 堆，里面包含连接器状态和最后一次刷出。这份状态不再和明细入库挤在
同一个 384 MiB 上限里。聚合进程单独取值，不另做压测：

| 项 | 默认 | 原因 |
| --- | --- | --- |
| `memory_limiter.limit_mib`（`APM_AGG_COLLECTOR_MEMORY_LIMIT_MIB`） | 512 | 软拒绝线是 512 − 128 = 384 MiB，比测到的 236 MiB 高出约 148 MiB |
| `spike_limit_mib`（`APM_AGG_COLLECTOR_MEMORY_SPIKE_MIB`） | 128 | 留给单批入口和刷出尖峰。越过软拒绝线时在计数前拒收 |
| 容器上限（`APM_AGG_COLLECTOR_CONTAINER_MEMORY_LIMIT`） | 640 MiB | 与系统 Collector 一样，容器上限 = `limit_mib` + 128 MiB，避免 limiter 拒绝前被 cgroup 杀掉 |

系统 Collector 仍是 384 / 96 / 512 MiB，只服务明细入库。

### 写入地址为空

聚合 Collector 不能按空环境变量关掉计数。未设置的 `${env:...}` 会展开成空字符串。
`otel/aggregate.yaml` 在写入地址为空时校验失败，错误是 `invalid endpoint`；`APM_AGG_SHARD`
为空时错误是 `external labels configuration contains an empty key or value`。两种都只让聚合进程
起不来。系统 Collector 不读这两个变量，VictoriaTraces 入库继续。空地址不回落到 `VICTORIAMETRICS_HOST`。
区域 Collector 不读这些变量。

### 可选基础认证

两个变量都留空时，聚合进程只加载 `aggregate.yaml`，不发送 `Authorization`。不要把空的 basicauth
扩展放进这份配置：扩展即使用户名为空也会发出认证头。

`AGG_VICTORIAMETRICS_USER` 和 `AGG_VICTORIAMETRICS_PASSWORD` 都设置时，再追加
`--config=/etc/bklite-apm/aggregate-auth.yaml`。只设置其中一个是错误的部署，不要这样启动。
口令只从环境注入。认证不能代替内网边界。系统 Collector 不加载这份认证。

### 聚合写入可单独回退

停掉聚合 Collector。系统 Collector 仍用 `system.yaml` 写 VictoriaTraces，区域 Collector、Stream 和已经
写入的明细保持不动。不要为了回退聚合去删除 Stream 或两个 consumer。

预建命令（已存在则跳过）：

```text
nats consumer add APM_TRACES BKLITE_APM_AGGREGATE \
  --filter "apm.traces.>" --pull --deliver new --ack explicit \
  --wait 30s --max-deliver 3 --max-pending 256 --replay instant --defaults
```

同一变更里启动聚合进程，并把系统 Collector 换成只含 VictoriaTraces 的 `system.yaml`。不要让旧的聚合分支
和新进程同时消费，也不要用 `deliver all` 回放积压。

## 本地验证

```bash
cd deploy/apm
make up        # 仅拉起契约夹具
make test
make validate
make contract  # 真实 SDK 全链路；需 Docker
```

`make contract` 使用独立 Compose project、随机端口与独立卷，验证入口、ACK、VT 查询、清洗、去重，
以及入口聚合的标签、多实例合并、桶、溢出、晚到计数、remote write 不可达、重启后的 `increase()`，
和 VictoriaTraces 停止期间写入的入口 Span 在恢复后只计一次。
聚合库只在这个夹具里出现，宿主端口默认 `18428`，不占用宿主 `8428`。结束后只删除自建资源。
通过契约不等于完成生产上线。

## 探针制品初始化（部署准备期）

APM 接入页生成的 Java / Python / Node.js / Go / .NET 接入脚本都从本系统下载离线包，
不依赖公网。运维调整发布流水线、归档产物和对象存储初始化，以
[APM 探针制品发布 Runbook](../../docs/operations/apm-probe-artifact-release.md)
为准。制品缺失只影响对应语言的接入指引，不阻断 Server 启动，也不得加入
`batch_init`。

## 与 Server 启动的关系

NATS、Collector、VT 都是运行期可降级依赖：不可用只使 APM degraded，不得阻断
`batch_init`、API、Worker、Beat 或 Listener 启动。
