# BK-Lite APM Collector 发行版

该发行版固定在 OpenTelemetry Collector `0.153.0`（镜像标签 `0.153.0-bklite.2`）。
区域配置只处理 traces。系统配置在同一条 JetStream 接收上增加入口聚合，使用
`filter`、`transform`、`span_metrics`、`count`、`batch`、`deltatocumulative` 和
`prometheusremotewrite`。可选基础认证使用 `basicauth`，只在追加 `system-auth.yaml` 时启用。

traces 路径上的三个自研组件是：

- `nats_jetstream` exporter：把 `ExportTraceServiceRequest` 的 OTLP Protobuf 正文发布到
  `apm.traces.<cloud_region_id>`，等待 JetStream 持久化 ACK，并以正文 SHA-256 设置
  `Nats-Msg-Id`；
- `nats_jetstream` receiver：绑定运维预创建的 Stream/Consumer，显式消费 ACK；只有下游
  `ConsumeTraces` 成功才 ACK，失败 NAK，非法 Subject、Content-Type 或 Protobuf 则终止毒消息。
- `trace_guard` processor：在任何本地持久化前统一清洗 Resource、Scope、Span、Event、Link，
  对属性数量与 Unicode 字符长度设硬上限，并注入可信云区域。

组件不创建 Stream 或 Consumer，避免 Collector 进程越权修改生产消息基础设施。NATS
URL 可直接沿用 BK-Lite 的 `tls://user:password@host:4222` 注入方式，也支持 credentials
文件和 CA/客户端证书路径；仓库不包含任何凭据。

```bash
make test
make build
make validate
```

`regional.yaml`、`system.yaml` 与 `system-traces.yaml` 使用同一个镜像。
`system-traces.yaml` 只有 VictoriaTraces 流水线，供写入地址为空或单独回退聚合分支时使用。
