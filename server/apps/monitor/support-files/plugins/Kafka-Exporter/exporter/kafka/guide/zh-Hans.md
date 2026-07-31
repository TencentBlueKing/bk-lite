# Kafka 监控接入指南

本能力通过 kafka_exporter 使用 Kafka 客户端协议访问 Broker，再由 Telegraf 从 exporter 本地 `/metrics` 端点拉取数据；它不使用 JMX。

## 前置要求

- 采集节点能够访问所填 Kafka Broker 的 `host:port`，并能继续访问 Broker 在 `advertised.listeners` 中通告的地址。
- 当前页面只接收一个 Broker 地址；该地址用于发现集群，不支持在页面填写多个 Broker。
- 当前页面支持明文连接以及 SASL 明文认证，不提供 TLS 证书或 TLS 开关字段。
- 启用 SASL 时，准备匹配 Broker 配置的用户名、密码和机制，并确保账号可读取 Topic、分区与消费组元数据。
- 在采集节点上准备一个未占用的 exporter 监听端口；它与 Kafka Broker 端口不是同一端口。

## 接入步骤

1. 从实际采集节点验证 Broker 地址和其通告地址均可达。
2. 填写 Kafka 协议版本；按需开启认证并填写 SASL 用户名、密码和机制。
3. 填写未占用的监听端口、单个 Kafka 服务器地址、Topic/消费组包含与排除正则，以及采集间隔（默认 `60` 秒）。
4. 在监控对象表格中选择节点，填写监听端口、服务器地址、实例名称和可选分组。
5. 保存后等待至少一个采集周期。

## 接入前校验

从采集节点检查所填 Broker 端口，例如：

```bash
nc -vz broker.example.com 9092
```

还应使用与页面相同的认证方式运行 Kafka 客户端元数据查询，确认返回的 Broker 通告地址对采集节点可达。仅初始端口连通不能证明集群发现链路完整。

## 页面字段说明

| 页面字段 | 是否必填 | 说明 |
| --- | --- | --- |
| 版本 | 是 | Kafka 客户端协议版本，例如 `2.0.0`，需与 Broker 兼容。 |
| 启用认证 | 否 | SASL 开关，默认关闭。 |
| 用户名、密码 | 条件必填 | 启用认证时填写。 |
| 运行机制 | 否 | SASL 机制：`plain`、`sha256`、`sha512` 或 `gssapi`；留空时按当前 exporter 默认使用 PLAIN。 |
| 监听端口 | 是 | exporter 在采集节点本地暴露 `/metrics` 的端口。 |
| 服务器地址 | 是 | 单个 Broker 的 `host:port`。 |
| Topic 包含 / 排除 | 否 | 正则默认分别为 `.*` 和 `^$`。 |
| 消费组包含 / 排除 | 否 | 正则默认分别为 `.*` 和 `^$`。 |
| 间隔 | 是 | 采集周期，单位秒，默认 `60`。 |
| 节点 | 是 | 运行 exporter 的采集节点。 |
| 实例名称 | 是 | 平台内展示的实例名称。 |
| 组 | 否 | 实例所属分组。 |

## 接入后验证

保存并等待一个采集周期后，可按实际监听端口检查本地端点，例如：

```bash
curl --fail --silent --show-error "http://127.0.0.1:9308/metrics"
```

随后在平台确认以下指标可查询：

- `kafka_up_gauge`
- `kafka_brokers_gauge`
- `kafka_topic_partition_count`
- `kafka_consumergroup_lag`

## 常见问题

### 初始 Broker 可达但无数据

- 检查 exporter 日志中的实际 Broker 地址；`advertised.listeners` 通告了采集节点不可达的地址时仍会失败。
- 确认所填版本与 Broker 协议兼容。
- 当前页面不能配置 TLS；要求 TLS 的集群无法用此配置直接接入。

### SASL 认证失败

- 核对认证开关、用户名、密码和机制是否与 Broker 一致。
- 密码只填写在密码字段，不要拼入服务器地址或其他字段。

### Topic 或消费组数据缺失

- 核对包含与排除正则，默认排除正则 `^$` 表示不排除。
- 确认账号具有读取 Topic、分区和消费组元数据所需权限。
