# ADR 0003：APM 控制面与遥测数据面分离

Status: accepted

## Context

APM 原始 Span 吞吐量高、数据体积大，并需要 OTLP、批处理、尾采样和 Trace 查询。让 Django 接收或持久化 Span 会把业务 API、数据库和 Server 启动绑定到遥测洪峰；复用 `/telegraf/api` 也会把 OTLP protobuf 错投给现有 Influx 接收器。

## Decision

BK-Lite 的 `apps.apm` 只作为控制面，拥有接入源、服务、实例、权限、策略、事件和告警生命周期数据，并通过内部存储接口查询遥测。OpenTelemetry Collector Gateway 是唯一 OTLP 数据入口；原始 Span 经采样写入默认的 VictoriaTraces，全量 Span 派生指标写入现有 VictoriaMetrics。Django 不接收、转发或保存原始 Span，`/telegraf/api` 保持原用途。

VictoriaTraces、Collector、VictoriaMetrics 和外部通知渠道均是运行期可降级依赖，缺失或失败不得阻断 BK-Lite Server 启动。领域层只依赖 `TraceStore`、`MetricStore` 和 `AlertPublisher` 小接口，生产与内存适配器遵守相同契约；告警归属与跨 App 协同遵循 ADR 0004。

## Consequences

- APM 数据洪峰与 Django/PostgreSQL 隔离，服务页使用预聚合指标，Trace 页使用专用 Trace Store。
- 默认部署增加 Collector 和 VictoriaTraces 的运行、容量、升级与健康治理成本。
- 跨存储不存在数据库事务；目录发现、告警投递和外部声明必须通过运行期幂等对账与补偿达到最终一致。
- 替换 Trace/Metric 后端需要实现既定端口，而不要求改写 API、权限和领域模型。
