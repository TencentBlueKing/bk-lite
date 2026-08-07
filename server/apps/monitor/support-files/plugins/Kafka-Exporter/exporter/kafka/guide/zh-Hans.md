# Kafka 监控接入指南

本能力通过 kafka_exporter 使用 Kafka 客户端协议访问 Broker，再由 Telegraf 从 exporter 本地 `/metrics` 端点拉取数据；它不使用 JMX。

## 前置要求

- 采集节点能够访问所填 Kafka Broker 的 `host:port`，并能继续访问 Broker 在 `advertised.listeners` 中通告的地址。
- 当前页面只接收一个 Broker 地址；该地址用于发现集群，不支持在页面填写多个 Broker。
- 当前页面支持明文连接以及 SASL 明文认证，不提供 TLS 证书或 TLS 开关字段。
- 启用 SASL 时，准备匹配 Broker 配置的用户名、密码和机制，并确保账号可读取 Topic、分区与消费组元数据。
- 在采集节点上准备一个未占用的 exporter 监听端口；它与 Kafka Broker 端口不是同一端口。
- 当前 exporter 最低支持 Kafka **0.10.2.0**；低于该版本会启动失败。

## 接入步骤

1. 从实际采集节点验证 Broker 地址和其通告地址均可达。
2. 填写 Kafka 协议版本（不低于 `0.10.2.0`）；按需开启认证并填写 SASL 用户名、密码，并选择认证机制（默认 `plain`）。
3. 填写未占用的监听端口、单个 Kafka 服务器地址、Topic/消费组包含与排除正则，以及采集间隔（默认 `60` 秒）。
4. Topic 或消费组规模较大时，按需调整采集并发、批次大小、消费组采集超时等调优字段。
5. 在监控对象表格中选择节点，填写监听端口、服务器地址、实例名称和可选分组。
6. 保存后等待至少一个采集周期。

## 接入前校验

从采集节点检查所填 Broker 端口，例如：

```bash
nc -vz broker.example.com 9092
```

还应使用与页面相同的认证方式运行 Kafka 客户端元数据查询，确认返回的 Broker 通告地址对采集节点可达。仅初始端口连通不能证明集群发现链路完整。

## 页面字段说明

| 页面字段 | 是否必填 | 说明 |
| --- | --- | --- |
| 版本 | 是 | Kafka 客户端协议版本，例如 `2.0.0`，需与 Broker 兼容；**最低 `0.10.2.0`**。 |
| 启用认证 | 否 | SASL 开关，默认关闭。 |
| 用户名、密码 | 条件必填 | 启用认证时填写。 |
| 认证机制 | 条件必填 | 启用认证时选择：`plain`、`scram-sha256` 或 `scram-sha512`；默认 `plain`。 |
| 监听端口 | 是 | exporter 在采集节点本地暴露 `/metrics` 的端口。 |
| 服务器地址 | 是 | 单个 Broker 的 `host:port`。 |
| Topic 包含 / 排除 | 否 | 正则默认分别为 `.*` 和 `^$`。 |
| 消费组包含 / 排除 | 否 | 正则默认分别为 `.*` 和 `^$`。 |
| Topic 采集并发 | 是 | Topic 元数据与 Offset 请求并发数，默认 `20`。 |
| 消费组采集并发 | 是 | 消费组 OffsetFetch 请求并发数，默认 `20`。 |
| 消费组批次大小 | 是 | 单次 DescribeGroups 请求的消费组数，默认 `50`。 |
| Offset 批次大小 | 是 | 单次 ListOffsets 请求的分区数，默认 `1000`。 |
| 消费组采集超时 | 是 | 消费组指标单轮采集超时（秒），默认 `45`；**必须小于采集间隔**。 |
| 采集全部已提交分区 | 是 | 默认开启；关闭后仅采集活跃成员分配的分区。 |
| 允许并发抓取 | 是 | 默认关闭；万级 Topic 场景建议保持关闭，使并发抓取复用同一轮结果。 |
| 间隔 | 是 | 采集周期，单位秒，默认 `60`。 |
| 节点 | 是 | 运行 exporter 的采集节点。 |
| 实例名称 | 是 | 平台内展示的实例名称。 |
| 组 | 否 | 实例所属分组。 |

## 采集超时推荐取值

超时配置保持一致关系，避免 Telegraf 先于 exporter 结束导致整实例无数据：

`GROUP_METRICS_TIMEOUT` < 采集间隔 `interval`

其中 Telegraf 的 `timeout` 与 `response_timeout` **始终与 `interval` 相同**（由 child 模板一并下发），不要单独改成更短或更长的值。

| 参数 | 推荐值 |
| --- | --- |
| 采集间隔 (`interval`) | `60` 秒 |
| Telegraf `timeout` / `response_timeout` | 与 `interval` 相同（例如 `60` 秒） |
| 消费组采集超时 (`GROUP_METRICS_TIMEOUT`) | `45` 秒（必须小于 `interval`） |

若将采集间隔调到 `30` 秒，请同步把消费组采集超时调到小于 `30` 秒（例如 `20` 秒）。平台保存时会校验该偏序。

## 升级与重下发

已接入实例不会自动应用 child 模板中的超时改动。升级 BK-Lite 或 kafka_exporter 后，若需要新的 `timeout` / `response_timeout`（与间隔一致）行为，请在监控接入页对该实例重新保存并下发采集配置。

## Lag 语义说明

- `kafka_consumergroup_lag = LEO - committed offset`，两者来自同一轮采集。
- committed offset 为 `-1` 时，Lag 输出 `-1`，且不输出异常指标，表示该分区没有提交记录。
- committed offset 大于同轮 LEO 时，Exporter 保留计算得到的原始负 Lag（可能包含 `-1`），并输出 `kafka_consumergroup_lag_anomaly=1`。
- 因此 Lag 为 `-1` 时需结合异常指标判断：无异常指标表示没有提交记录；异常指标为 `1` 表示 committed offset 大于 LEO。

## 接入后验证

保存并等待一个采集周期后，可按实际监听端口检查本地端点，例如：

```bash
curl --fail --silent --show-error "http://127.0.0.1:9308/metrics"
```

随后在平台确认以下指标可查询：

- `kafka_up_gauge`
- `kafka_brokers_gauge`
- `kafka_exporter_scrape_success`
- `kafka_topic_partition_count`
- `kafka_consumergroup_lag`

## 常见问题

### 初始 Broker 可达但无数据

- 检查 exporter 日志中的实际 Broker 地址；`advertised.listeners` 通告了采集节点不可达的地址时仍会失败。
- 确认所填版本不低于 `0.10.2.0`，且与 Broker 协议兼容。
- 当前页面不能配置 TLS；要求 TLS 的集群无法用此配置直接接入。
- 确认消费组采集超时小于采集间隔，避免 Telegraf 先于 exporter 超时。

### SASL 认证失败

- 核对认证开关、用户名、密码和认证机制是否与 Broker 一致。
- 认证机制须显式选择（`plain` / `scram-sha256` / `scram-sha512`），不要依赖占位提示。
- 密码只填写在密码字段，不要拼入服务器地址或其他字段。

### Topic 或消费组数据缺失

- 核对包含与排除正则，默认排除正则 `^$` 表示不排除。
- 确认账号具有读取 Topic、分区和消费组元数据所需权限。
