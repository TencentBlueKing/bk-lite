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
  -> 系统级 Collector
  -> VictoriaTraces
```

调用链明细只写 VictoriaTraces。入口 Span 的累计计数、耗时直方图和晚到计数写入独立聚合库，
不写入 Monitor 的 VictoriaMetrics，也不复用 `VICTORIAMETRICS_HOST`。不做尾采样，也不包含独立
APM Edge Nginx。`/telegraf/api` 仍只属于 Monitor。APM 从未正式部署，不存在旧数据面迁移。

职责边界见 [ADR 0006](../../docs/adr/0006-apm-regional-nats-victoriatraces-pipeline.md)、
[ADR 0008](../../docs/adr/0008-apm-trusted-regional-ingress.md)、
[ADR 0011](../../docs/adr/0011-apm-rum-aggregate-metrics-store.md) 与
`docs/design/product-decisions/apm-data-plane.md`。

## 目录与角色

| 路径 | 归属 | 说明 |
| --- | --- | --- |
| `collector/` | 研发（产品组件） | 固定 OTel Collector `0.153.0` 的 BK-Lite 发行版；JetStream exporter/receiver、`trace_guard` |
| `otel/regional.yaml` / `otel/system.yaml` | 研发（契约参考配置） | 区域清洗/排队与中心消费写 VT 的行为基线；生产可换编排，语义须等价 |
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

- 有界 `APM_TRACES` Stream 与 `BKLITE_APM_SYSTEM` durable consumer（语义见验收清单）。
- VictoriaTraces 保留期 ≥ 35 天，并启用 service graph 任务；APM 唯一遥测事实源。
- 容量下界与告警门槛见 [CAPACITY.md](./CAPACITY.md)；本地 256 MiB Stream 仅契约测试。
- 验收与回滚约束见 [ACCEPTANCE.md](./ACCEPTANCE.md)。**如何**用 Helm/Ansible/现有流水线落地不在本目录规定。

## 入口聚合

系统 Collector 的同一个 `nats_jetstream` 接收器扇出三条流水线：

1. `traces`：只经过 `memory_limiter`，写入 VictoriaTraces。这条流水线的形状保持不变。
2. `traces/aggregate`：只留 `SERVER` / `CONSUMER`，丢掉结束时间早于处理时刻 5 分钟的 Span，
   用 `transform` 的 `keep_keys` 把资源属性收窄到 `service.namespace`、`service.name`、
   `deployment.environment`，再进入 `span_metrics`。环境字段与 Server 现有 RED 查询相同。
3. `traces/late`：同样只留入口 Span，只保留晚到 Span，做同样的资源收窄，再交给 `count`。
   指标名是 `apm_aggregate_late_spans_total`。写出前经过 `batch`、把样本时间改成处理时刻、再 `deltatocumulative`。
   count 默认把时间打在 Span 结束时间上；晚到 Span 的结束时间已经超过 5 分钟，不改的话即时查询看不到。

晚到条件是 `span.end_time_unix_nano < UnixNano(Now()) - 300000000000`。聚合分支和晚到分支
不放 `memory_limiter`，也不放会把错误退回接收器的组件。remote write 失败时接收器不 NAK，
同一条 Span 不会因此在 VictoriaTraces 写两次。

`span_metrics` 的指标前缀是 `apm_`。它排除 `span.kind` 和 `collector.instance.id`，关闭
exemplars，直方图单位是 `ms`，桶从 `5ms` 到 `10000ms`。`aggregation_cardinality_limit` 默认
90000。资源分组键就是上面三个资源属性，这样同一个服务的多个 `service.instance.id` 只产生一组序列。
超出上限的组合并进一条 `otel.metric.overflow=true` 序列。这条序列只有该标记，不再带服务名和操作名；
`job` 仍是「命名空间/服务名」。
Prometheus 侧允许的业务标签是服务命名空间、服务名、环境、入口操作和状态；另有去不掉的 `job`
以及 `shard`。不应出现 `instance`、`collector.instance.id`、`target_info` 或 scope 标签。

remote write 写入 `AGG_VICTORIAMETRICS_WRITE_URL`。`external_labels.shard` 来自 `APM_AGG_SHARD`，
每个写入进程一个固定值，重启不变，进程之间互不相同。不要用 Span 上的 `service.instance.id` 充当分片。
`resource_to_telemetry_conversion`、`target_info` 和 scope 标签都关闭。区域 Collector 不写聚合库。

刷出间隔默认 60 秒（`APM_AGG_FLUSH_INTERVAL`）。容量估算按这个间隔；缩短后磁盘按比例增加。
本地夹具可以把该变量设为 `1s`。

### 写入地址为空

Collector 不能按空环境变量关掉一条流水线。未设置的 `${env:...}` 会展开成空字符串。
`otel/system.yaml` 在写入地址为空时校验失败，错误是 `invalid endpoint`；`APM_AGG_SHARD`
为空时错误是 `external labels configuration contains an empty key or value`。两种都会让
整个系统 Collector 进程无法启动，VictoriaTraces 入库一起停。空地址不回落到
`VICTORIAMETRICS_HOST`。

聚合库还没就绪、又要保住明细时，启动参数改为 `--config=/etc/bklite-apm/system-traces.yaml`。
这份配置只有原来的 VictoriaTraces 流水线，不启用聚合分支，也不读取聚合库变量，因此这两个
变量留空仍然可以启动。区域 Collector 不受影响。使用 `system.yaml` 时，写入地址和分片值是部署硬约束。

### 可选基础认证

两个变量都留空时，只加载 `system.yaml`，不发送 `Authorization`。不要把空的 basicauth
扩展放进这份配置：扩展即使用户名为空也会发出认证头。

`AGG_VICTORIAMETRICS_USER` 和 `AGG_VICTORIAMETRICS_PASSWORD` 都设置时，再追加
`--config=/etc/bklite-apm/system-auth.yaml`。只设置其中一个是错误的部署，不要这样启动。
口令只从环境注入。认证不能代替内网边界。

### 单独回退聚合分支

系统 Collector 改挂 `otel/system-traces.yaml` 后重启。VictoriaTraces 流水线、区域 Collector、
Stream 和已经写入的明细保持不动。

## 本地验证

```bash
cd deploy/apm
make up        # 仅拉起契约夹具
make test
make validate
make contract  # 真实 SDK 全链路；需 Docker
```

`make contract` 使用独立 Compose project、随机端口与独立卷，验证入口、ACK、VT 查询、清洗、去重，
以及入口聚合的标签、多实例合并、桶、溢出、晚到计数、remote write 不可达和重启后的 `increase()`。
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
