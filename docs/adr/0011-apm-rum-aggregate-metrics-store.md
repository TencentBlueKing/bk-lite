# ADR 0011：APM 与 RUM 的入口聚合使用独立 VictoriaMetrics

Status: accepted

## Context

APM 的首页、服务列表、服务 RED 和可用性 SLO，以及 RUM 的应用概览、页面列表和
Web Vitals 告警，都在打开页面或每分钟评估时扫描 VictoriaTraces 里的 Span 或
VictoriaLogs 里的事件。查询时间和数据量一起增长，长窗口先超时，并且和用户正在看的
明细查询抢同一套库。

监控和 CMDB 已经共用 `VICTORIAMETRICS_HOST` 指向的 VictoriaMetrics。聚合序列如果写进
那套库，监控扫描会把它们当成主机指标，两边的序列也会抢磁盘和查询。因此聚合层使用
独立地址、独立进程的单节点 VictoriaMetrics，只保存有界维度的累计计数和累计直方图。

2026-11-09 的概念验证支持这个决定，也限定了它的误差：

- APM Collector v0.153.0 可以在不抬升核心版本的前提下，与现有自研组件一起构建
  spanmetrics、count、filter 和 prometheusremotewrite。spanmetrics 写出累计值。
  重复累计样本不改变 `increase()`。重启后的重置只计入新 Span，不把重启前的计数再乘一遍。
- 连接器默认会加随机的 `collector.instance.id`。固定分片要用 remote write 的
  `external_labels.shard`，并排除该维度。`service.instance.id` 不能充当 APM 分片；
  留在 Span 资源上会变成 Prometheus 的 `instance`。`job` 仍然去不掉。
- 直方图桶必须带时间单位。裸数字能通过配置校验，运行时却被当成纳秒。
- 晚到条件里的 `300e9` 不能解析，要写成整数纳秒。count 输出 Delta，直接 remote write
  不会得到累计计数，需要先经过 deltatocumulative。
- remote write 失败时，spanmetrics 不把错误交回 traces，JetStream 不 NAK，
  VictoriaTraces 不因此写两次。count 如果不先经过 batch，导出失败会 NAK，同一条
  Span 会在 VictoriaTraces 写两次。
- 聚合层不按 `trace_id` 和 `span_id` 去重。验证里 10 个唯一 Span 再重投其中 2 个
  错误 Span 后，聚合侧请求数是 12、错误数是 4，VictoriaTraces 去重后是 10 和 2。
  偏差等于重投比例。不能把“稳定流量下偏差不超过 1%”写成无条件验收。
- 磁盘按约 1 字节每个样本、60 秒一个样本、35 天估算。APM 1,620,000 条序列约
  76 GiB，RUM 夹具 3,420,000 条序列约 161 GiB。这是上限估算，不是远程库上的实测磁盘。
  RUM 夹具的直方图是 8 个边界，不是产品 Web Vitals 的桶。同一轮的进程堆增量大约是
  APM 236 MiB、RUM 331 MiB，不能当成磁盘。

这轮验证没有覆盖“同一服务的多个实例只合并成一组序列”。RUM 容量夹具只量了进程内的
signal_to_metrics 和 deltatocumulative。完整的 RUM 网关写入路径随后由 05 ticket 在
`bklite/rum-collector:0.1.0-bklite.2` 上补验，标签、错误隔离和重启后的 `increase()`
以该 ticket 的容器契约为准。运维规则和容量口径见
[聚合库运维规则](../operations/aggregate-metrics-store.md)。

## Decision

- 本决定部分替代 [ADR 0006](0006-apm-regional-nats-victoriatraces-pipeline.md)。
  APM 与 RUM 可以把有界维度的累计计数和直方图写入独立聚合库。
- VictoriaTraces 仍是调用链明细、告警策略、慢请求、Apdex、延迟 SLO、下钻和拓扑的
  唯一来源。RUM 事件明细和会话类查询仍以 VictoriaLogs 为准。
- Monitor 的 VictoriaMetrics 不受影响。聚合库不读取、不复用 `VICTORIAMETRICS_HOST`。
- 聚合层不去重。没有重复投递时，请求数和错误数应与 VictoriaTraces 按
  `trace_id` 加 `span_id` 去重的结果一致。有重复投递时，读数按重投比例偏高，错误数
  单独计算。
- ADR 0006 的其余决定不变。区域 Collector、JetStream、系统 Collector、受信内网入口、
  无 Edge、无尾采样、控制面不接收原始 Span，以及外部遥测依赖不阻断 Server 启动，
  都继续有效。
- 研发交付本规则、两个产品镜像中的组件和配置，以及 Server 读取侧。研发不提供生产
  编排。运维按[聚合库运维规则](../operations/aggregate-metrics-store.md)部署单节点库、
  保留期、内网边界、告警和写入身份，并自行重新打包镜像。

## Consequences

- 入口 RED 与可用性 SLO 可以改读聚合库。查询窗口早于聚合起点时仍走原来的明细查询。
  聚合库故障时，这些页面降级或缺数据，不显示成 0，也不在故障时把负载扫回明细库。
- 明细入库不经过聚合库。停库不阻断 VictoriaTraces、VictoriaLogs，也不阻断 Server
  启动和 `batch_init`。
- 重投期间聚合数字会高于去重后的调用链。这是接受的偏差，不作为无条件的 1% 门槛。
- Client Span、推断下游、慢请求、Apdex、延迟 SLO 和告警策略不进入聚合库。
- 两个镜像要加入 Alpha 或 Beta 组件。升级 Collector 时必须回归聚合流水线。
  组件清单以镜像 `components` 输出核对运维规则。APM 镜像标签是 `0.153.0-bklite.3`，
  RUM 镜像标签是 `0.1.0-bklite.3`。本文不表示聚合库已经在生产部署。
- `deploy/apm` 的验收清单、README 和数据面配置测试在聚合流水线 ticket 中更新。
  那些文件在本次决定接受时仍描述调用链契约，不描述已经部署的聚合库。
