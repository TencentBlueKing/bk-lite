# Kafka 监控接入指南

本插件基于 WeOps 自研 kafka_exporter（基于 danielqsj/kafka_exporter fork）以 **Kafka 客户端协议** 方式连接 Broker，采集 broker / topic / consumer group 等核心指标。Telegraf `inputs.prometheus` 从 kafka_exporter 本地监听端口的 `/metrics` 抓取指标。**exporter 监听端口 ≠ Kafka Broker 端口**（默认 Kafka `9092`，exporter 默认 `9308`），请勿混淆。

## 前置要求

- 目标 Kafka Broker（单机或集群）已启动，并监听 `9092`（默认）。
- exporter 以 client 协议直连 Broker，**不是**拉取 JMX，所以无需 Kafka 节点开 JMX 端口。
- Kafka Broker 启用 `advertised.listeners=PLAINTEXT://<reachable_ip>:9092`，**broker 必须能被访问到 advertised IP**——exporter 启动后只识别 broker 自己通告的地址。
- 启用 SASL 时，账号需要在 Kafka 服务端创建（`bin/kafka-configs.sh` 或 KRaft 控制面）。
- 启用 TLS 时，exporter 需要 `tls.ca-file` / `tls.cert-file` / `tls.key-file`；UI.json 当前未暴露 TLS 选项，仅支持明文或 SASL 明文。
- 采集节点到 Kafka Broker 端口（默认 `9092`）网络可达（含安全组 / 防火墙 / 双向 NAT）。
- exporter 进程能正常启动，采集节点可访问 `http://127.0.0.1:9308/metrics`。

> `kafka.server` 字段填写 broker 的 `host:port`，**多个 broker 用多个 `--kafka.server` 标记**；当前 UI 只暴露一个连接地址，多节点需扩展。

## 推荐账号权限

监控账号建议仅授予最小权限：

```text
# 7.0+ 用 SASL/SCRAM 时，先 bin/kafka-configs.sh 创建 SCRAM 凭据
# 监控账号仅授予 describe 权限即可，不需要 pub/sub 权限
kafka-acls.sh --authorizer-properties zookeeper.connect=<zk:2181> \
  --add --allow-principal User:'<monitor>' --operation Describe --topic '*'
kafka-acls.sh --add --allow-principal User:'<monitor>' --operation Describe --group '*'
kafka-acls.sh --add --allow-principal User:'<monitor>' --operation ClusterAction --cluster '*'
```

`Describe Topic` 与 `Describe Group` 是采集 Lag/Offset 所必需；`Cluster Action` 用于 `kafka_consumergroup_*` 维度。

## 接入步骤

1. 在采集节点验证 Kafka Broker 端口可达：

   ```bash
   nc -zv <broker_host> 9092
   ```

2. 在监控接入页填写：
   - Kafka 版本（默认 `2.0.0`）
   - 启用 SASL 认证（按需）
   - SASL 用户名 / 密码 / 运行机制（按需；SCRAM-SHA-256 / SCRAM-SHA-512 / GSSAPI）
   - kafka_exporter 监听端口（默认 `9308`）
   - Kafka 服务器地址（`host:port`，如 `broker-1:9092`）
   - Topic 包含 / 排除（按需；正则为 `.*` / `^$`）
   - 消费组包含 / 排除（按需）
   - 采集间隔（默认 `60s`）
3. 在「监控对象」表格中填写节点、监听端口、Kafka 服务器地址、实例名称、所属组。
4. 点击「确认」保存配置，等待至少一个采集周期。
5. 到资产或指标页确认实例已上报数据。

## 接入前校验

Broker 端口可达：

```bash
nc -zv <broker_host> 9092
```

exporter 监听可达：

```bash
curl -sS http://127.0.0.1:9308/metrics | head
```

正常返回 `kafka_broker_info`、`kafka_topic_partition_*`、`kafka_consumergroup_*`、`kafka_exporter_build_info`。

## 页面字段说明

| 页面字段 | 是否必填 | 说明 |
| --- | --- | --- |
| 版本 | 是 | Kafka Broker 协议版本，默认 `2.0.0`；不同版本在 idempotent / transactional 协议上有差异 |
| 启用认证 | 否 | 开关；启用后下发 `sasl.enabled`，关闭时空字符串 |
| 用户名 | 条件必填 | SASL 用户名；启用认证时必填 |
| 密码 | 条件必填 | SASL 密码；启用认证时必填 |
| 运行机制 | 否 | SASL 机制，如 `plain`/`sha256`/`sha512`/`gssapi`；不填走 SASL 默认（PLAIN） |
| 监听端口 | 是 | exporter 本地暴露 `/metrics` 的端口，默认 `9308`，**不是** Kafka 服务端口 9092 |
| 服务器地址 | 是 | Kafka broker 的 `host:port`，如 `kafka:9092`；broker 必须能被访问 advertised.listeners |
| Topic 包含 | 否 | 采集 topic 正则，默认 `.*` |
| Topic 排除 | 否 | 排除 topic 正则，默认 `^$` |
| 消费组包含 | 否 | 采集消费组正则，默认 `.*` |
| 消费组排除 | 否 | 排除消费组正则，默认 `^$` |
| 间隔 | 是 | 采集周期，单位秒，默认 `60` |
| 节点 | 是 | 负责采集的探针节点 |
| 实例名称 | 是 | 平台内展示的实例名，默认由「Kafka 服务器地址」自动填充 |
| 组 | 否 | 组织分组，便于权限与资产归属 |

## 常见问题

### 1. 保存后长时间无数据

- 在采集节点本地执行 `curl http://127.0.0.1:9308/metrics`，确认 kafka_exporter 已监听并暴露指标。
- 看 exporter 日志 `kafka_exporter.go:connection refused` 或 `no advertised brokers`：通常是 broker 的 `advertised.listeners` 用了内网 IP，外部访问被拒。
- TLS 启用时检查 CA / 证书链是否正确；证书中 CN/SAN 必须匹配 `tls.server-name`。
- 等待至少一个采集间隔后再查看。

### 2. 认证失败

- SASL 凭据（用户名 / 密码 / 运行机制）必须与 Broker 端 `bin/kafka-configs.sh` 创建的一致。
- 含特殊字符的密码务必通过 password 字段下发，不要拼到 broker 地址或参数中。
- ACR/AKS/Strimzi 部署下，KafkaUser 资源必须将 `authentication.type` 与 SASL 机制匹配。

### 3. 部分指标缺失

- `kafka_consumergroup_*` 需要 `Describe Group` 权限；不给则看不到维度。
- `kafka_topic_partition_*` 在 topic 数量极多时会被 `topic.filter/exclude` 过滤；正则不匹配将不返回。
- 老版本 broker (< 0.10.1) 上 `kafka_consumergroup` 不可用，请升级 broker。