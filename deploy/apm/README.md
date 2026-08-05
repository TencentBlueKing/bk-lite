# BK-Lite APM 数据面

该目录提供与 Django Server 启动解耦的 traces-only 运行期部署参考：

```text
OTel SDK / Agent
  -> 区域 Collector（直接监听 OTLP 4317/4318）
  -> NATS JetStream apm.traces.<cloud_region_id>
  -> 系统级 Collector
  -> VictoriaTraces
```

APM 不使用 VictoriaMetrics，不生成 Span Metrics，不做尾采样，也不再部署独立 APM Edge
Nginx。`/telegraf/api` 仍只属于 Monitor 的 Telegraf Influx 接口。

## 目录与角色

- `collector/`：固定 OTel Collector `0.153.0` 的 BK-Lite 发行版；包含 traces-only
  JetStream exporter/receiver 和 `trace_guard` 清洗处理器。
- `otel/regional.yaml`：区域入口，先限制内存、清洗/限长、注入可信区域、批处理，再通过
  bytes 计量的本地持久队列等待 JetStream publish ACK。
- `otel/system.yaml`：绑定预创建 durable consumer，直接写 VictoriaTraces；下游失败时 NAK，
  成功后才同步 ACK。
- `nats/nats-server.conf`：本地契约环境的最小权限参考，不是生产凭据。
- `compose.yaml`：可重复本地验证。生产 Stream、Consumer、系统 Collector、VT、容量和告警
  由运维部署。

## 传输契约

- Subject：区域仅可发布 `apm.traces.<自身区域>`；中心订阅 `apm.traces.>`。
- Payload：OTLP Protobuf `ExportTraceServiceRequest`，`Content-Type: application/x-protobuf`。
- Headers：`BK-Cloud-Region-Id`、`BK-OTLP-Schema-Version: 1`、`Nats-Msg-Id`。
- `Nats-Msg-Id` 是 schema、区域和 Protobuf 正文的 SHA-256；Stream duplicate window 抑制
  publish 重试。VT 接受后到 ACK 持久化前仍有崩溃窗口，所以端到端是至少一次，而非
  exactly-once；Server 聚合必须按 `trace_id + span_id` 去重。
- 非法 Subject、区域 header、schema、Content-Type 或 Protobuf 是 poison message，终止投递；
  VT 不可用是可重试失败，消息不 ACK。

生产运行身份不得拥有 Stream/Consumer 管理权限。区域凭据的 publish ACL 必须精确到自身
Subject；中心凭据只需要 Stream/Consumer info、pull、ACK 与 inbox。`apm-nats-init` 使用的
管理身份只用于本地契约，生产由运维在运行进程启动前创建并核对配置。

## 启动与配置

复制 `.env.example` 的变量到受管部署环境。文件中的 `replace-me` 和 Compose 的默认密码仅供
隔离本地契约，禁止用于共享或生产环境；生产凭据、CA 和客户端证书必须由 Secret/环境注入。

```bash
docker compose -f deploy/apm/compose.yaml up -d --wait
```

区域 Collector 的宿主机绑定默认是 `127.0.0.1:4317/4318`。生产应把
`APM_OTLP_GRPC_BIND`、`APM_OTLP_HTTP_BIND` 配置为区域内受控地址，并把 NodeMgmt 中该云区域
受信代理地址的 4318 映射到 HTTP receiver；Server 固定生成
`http://<proxy_address>:4318/v1/traces`，不得通过浏览器提交 endpoint。4317 保留给手工 gRPC
接入兼容，普通接入页面不展示。VT 默认保留 35 天，覆盖产品 30 天/月历月 SLO 窗口。

本地 Stream/Consumer 创建是幂等的“存在则复用、缺失则创建”。生产升级不能只跳过已存在
对象：运维必须对照以下边界检查漂移，再显式 edit/reconcile：

- Stream：file/limits/discard-old、max bytes、max age、8 MiB 单消息、duplicate window；
- Consumer：durable pull、AckExplicit、ack wait、max deliver、max ack pending；
- 达到 max deliver 后保留消息并通过 advisory/指标告警，不无限重投或静默 ACK。

## 清洗与资源边界

`trace_guard` 在数据进入本地持久队列和 NATS 前统一处理 Resource、Scope、Span、Event、Link：

- 删除客户端提交的 `bk.*`、凭据/密码/cookie/token 类键、请求响应 body 和完整 URL；
- 清洗后注入部署可信的 `bk.cloud_region.id`；
- Resource/Scope/Span/Event/Link 属性上限分别为 64/32/100/32/32，字符串默认最多 4096
  Unicode code points；应用归属字段被优先保留；
- span name 删除 query/fragment，批次与 OTLP 请求不超过部署上限。

区域队列使用 bytes 硬上限；满载时拒绝新批次并增加 exporter failure 指标，不能无限占用磁盘。
重试持续到恢复，但同时受有界磁盘队列约束。JetStream 也同时受 max bytes/max age/max message
约束。

## 观测与容量

至少采集并告警以下信号：

- 区域 Collector：accepted/refused spans、exporter sent/send-failed、queue size/capacity、最后成功发布；
- NATS `/jsz`：Stream bytes/messages、consumer pending/ack pending/redelivered、消息年龄、API error；
- 系统 Collector：receiver accepted/refused、exporter sent/send-failed、处理延迟；
- VT：写入错误、查询错误/延迟、磁盘使用/剩余空间和保留期一致性。

区域队列和 Stream 使用 70%/85% 两级告警；pending 消息年龄接近 max age、持续 publish/VT
失败和 max-delivery advisory 必须告警。生产容量至少按峰值 bytes/s、区域中断容忍时长、
35 天 Trace 日写入量、存储放大、副本数和 30% 余量计算，不能直接照搬本地 256 MiB Stream。
具体输入、公式和告警门槛见 [CAPACITY.md](./CAPACITY.md)。

## 验证

```bash
make -C deploy/apm/collector test
make -C deploy/apm/collector validate

RUN_APM_CONTAINER_CONTRACT=1 \
  server/.venv/bin/python -m pytest -q deploy/apm/tests/test_data_plane_contract.py
```

容器契约使用独立 Compose project、随机宿主端口和独立卷，验证 OTLP/HTTP 与 gRPC 入口、
JetStream 持久化/ACK、VT 查询、保留字段清理和重复批次去重；结束后只删除自己创建的资源。

## 启动与迁移边界

该数据面不是 `batch_init`、迁移、API、Worker、Beat 或 Listener 的启动依赖。NATS、Collector
或 VT 不可用只使 APM 运行期 degraded，不能阻断 Server 启动。升级时先部署 Stream/中心/VT，
再逐区域切换 4317/4318，最后停止旧 Edge、tail sampling 和 APM Span Metrics 写读。不得删除或
修改 Monitor 的 VictoriaMetrics 数据与配置；旧镜像和路由至少保留一个发布窗口用于回滚。
逐步升级、验证、回滚和可恢复清理步骤见 [MIGRATION.md](./MIGRATION.md)。
