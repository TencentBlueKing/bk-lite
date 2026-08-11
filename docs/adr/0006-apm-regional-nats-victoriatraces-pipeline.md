# ADR 0006：APM 采用区域 Collector、JetStream 与 VictoriaTraces-only 数据面

Status: accepted

## Context

区域节点可能无法连接中心 VictoriaTraces，而 NATS 已是 BK-Lite 跨云区域传输基础设施。APM 尚未正式部署；仓库早期未发布方案曾设计 Edge Nginx、尾采样和 VictoriaMetrics Span Metrics，但该方案会形成独立入口与双存储语义，既不能复用区域 NATS 的可靠传输，也会使 RED、SLO、目录和策略跨 VictoriaTraces/VictoriaMetrics 两份事实源漂移。官方 `otelcol-contrib` 0.153.0 发行清单没有 NATS trace receiver/exporter；其 Go 模块要求 Go 1.25，仓库主机 Go 1.23.7 不能直接构建，但现有 Docker 工具链能够以固定 Go 1.25 镜像可重复构建自定义发行版。

## Decision

APM 数据面固定为“区域 Collector → NATS JetStream `apm.traces.<cloud_region_id>` → 系统级 Collector → VictoriaTraces”。BK-Lite 维护一个 traces-only 自定义 Collector 发行版，在 Collector 的 exporter/receiver seam 内实现 OTLP Protobuf 与 JetStream 的转换、持久化发布确认和显式消费确认；不使用声明不存在组件的 YAML，也不增加 Collector 旁路 Adapter。区域 Collector 直接接收 OTLP 4317/4318；首次生产上线不包含 Edge Nginx、尾采样、Span Metrics 或 APM VictoriaMetrics。VictoriaTraces 保存默认全量 Trace，并成为 APM Trace、RED、目录、SLO、策略和错误聚合的唯一遥测事实源。

控制面与数据面分离原则继续保留：Django 不接收、转发或持久化原始 Span，`/telegraf/api` 保持 Telegraf Influx 接口，JetStream、Collector 与 VictoriaTraces 都是运行期可降级依赖，失败不得阻断 Server 启动。Monitor 继续独占其 VictoriaMetrics 语义，Log 继续独占其 VictoriaLogs 语义。

## Consequences

- 运维必须部署有界 JetStream Stream、系统级 Collector 和开启 service graph 后台任务的 VictoriaTraces；研发交付双方配置契约、镜像构建和本地真实链路验证。
- JetStream 提供至少一次投递。发布端用确定性消息 ID 和 duplicate window 抑制重复发布；消费端只在下游接受后确认。崩溃窗口仍可能让同一 Span 重复写入，因此所有 APM 派生查询按 `trace_id + span_id` 去重，目录继续依赖数据库唯一约束，不能把物理重复计入 RED/SLO。
- 这是首次生产数据面的选择，不是存量架构迁移。首次上线失败时只停止或回退本次发布的正式组件，保留 Stream、区域队列和 VT 数据；不得引入早期未发布方案作为回滚路径，也不得修改 Monitor 的 VictoriaMetrics。
