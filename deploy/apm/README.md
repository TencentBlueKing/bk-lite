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

APM 不使用 VictoriaMetrics，不生成 Span Metrics，不做尾采样，也不包含独立 APM Edge
Nginx。`/telegraf/api` 仍只属于 Monitor。APM 从未正式部署，不存在旧数据面迁移。

职责边界见 [ADR 0006](../../docs/adr/0006-apm-regional-nats-victoriatraces-pipeline.md)、
[ADR 0008](../../docs/adr/0008-apm-trusted-regional-ingress.md) 与
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

## 本地验证

```bash
cd deploy/apm
make up        # 仅拉起契约夹具
make test
make validate
make contract  # 真实 SDK 全链路；需 Docker
```

`make contract` 使用独立 Compose project、随机端口与独立卷，验证入口、ACK、VT 查询、清洗与去重；
结束后只删除自建资源。通过契约不等于完成生产上线。

## 与 Server 启动的关系

NATS、Collector、VT 都是运行期可降级依赖：不可用只使 APM degraded，不得阻断
`batch_init`、API、Worker、Beat 或 Listener 启动。
