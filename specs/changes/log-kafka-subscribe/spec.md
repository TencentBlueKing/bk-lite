# 通用 Kafka 日志订阅

Status: implemented

## Problem Statement

客户第三方系统只能把日志推到自己的 Kafka，平台又不内置 Kafka 集群。运维人员现在无法把这条外部 Topic 接进日志系统：现有 `kafka` 采集方式只读取 Kafka Broker 日志文件，监控 Kafka 只采指标，日志主干也不会主动去订客户 Topic。

## Solution

新增一种通用日志采集方式「Kafka 日志订阅」。用户在日志集成里选择该方式、绑定能访问客户 Kafka 的节点，填写 Topic、消费组和 Broker 地址。节点上的 Vector 以 Kafka 消费者身份订阅消息，补齐采集身份后写入现有 NATS `vector` 通道；中心系统 Vector、VictoriaLogs、检索、提取器和告警沿用原链路，不新开存储或查询通道。

## User Stories

1. As a 日志运维人员, I want a distinct Kafka 日志订阅 collect type under 通用, so that I can ingest third-party Topic logs without confusing them with Kafka Broker 文件日志.
2. As a 日志运维人员, I want to bind a managed node and configure topics, consumer group and bootstrap servers like file collection, so that the collector can reach the customer Kafka and start consuming.
3. As a 日志运维人员, I want optional SASL and a start-from-latest/beginning choice, so that a typical authenticated Kafka can be connected without dumping historical partitions on first attach.
4. As a 日志运维人员, I want consumed payloads to appear as ordinary log events on the collection instance, so that I can search, extract, group and alert using the existing log product.
5. As a 日志运维人员, I want to reopen the instance and see the same subscription settings I saved, so that later edits do not drop topics, group, brokers or SASL state.

## Implementation Decisions

### 1. 采集身份与边界

- 新增内置采集方式：`name = kafka_subscribe`，`collector = Vector`，`display_category = general`。展示名「Kafka 日志订阅」，描述明确为订阅外部 Topic，而不是采集 Kafka 进程日志。
- 禁止复用现有 `Filebeat / kafka`。后端唯一约束是 `(name, collector)`，但前端采集方式表、默认查询、分析入口都按 `name` 分发；同名会把两种完全不同的日志语义叠在一起。
- 采集器仍是节点 fusion-collector 中的 Vector。中心系统 Vector 继续只消费 NATS、归一化、执行提取器并写入 VictoriaLogs。平台不部署 Kafka Broker，也不在中心增加 Kafka source。
- 日志采集实例仍是权限、数据范围、提取器和检索过滤的共同对象。事件必须带顶层 `message`、`timestamp`、`collect_timestamp`、`collector`、`collect_type`、`instance_id`。
- 现有提取器入口对所有经过中心系统 Vector 的采集类型开放，本方式无需单独做能力矩阵。

### 2. 数据链路

节点 Vector：`kafka` source → enrich remap → NATS sink（`subject = vector`，JSON，现有用户名密码与 TLS 环境变量）。

中心系统 Vector：现有 `server_nats` → `normalize_event` → `log_extractors` → `prepare_victoria_logs` → VictoriaLogs。

这条主干不改。本变更只增加一种节点侧 source 插件。

### 3. 插件与配置

沿用日志采集插件机制：采集类型声明、Vector 子配置 Jinja 模板、节点管理下发。`log_init` 扫描插件目录后即可登记新类型，不新增对外 API 或独立采集服务。

Vector source 使用原生 `type = "kafka"`，配置映射为：

- `topics`：用户填写的 Topic 列表
- `group_id`：消费组；留空时模板默认为 `bk-lite-<instance_id>`
- `bootstrap_servers`：逗号分隔的 `host:port`
- `auto_offset_reset`：界面「从最新 / 从头」分别对应 `latest` / `earliest`，默认从最新
- `decoding.codec = bytes`：Kafka value 写入顶层 `message`，第一版不做 JSON 拍平
- 可选 SASL：关闭时不渲染；开启后写 `sasl.enabled`、mechanism（默认 `PLAIN`，可选 `SCRAM-SHA-256` / `SCRAM-SHA-512`）、username、password
- 可选 `tls.enabled`：默认关闭；自定义 CA / 客户端证书不做

enrich 必须写入 `collector = "Vector"`、`collect_type = "kafka_subscribe"`、`instance_id`，并包含与文件采集相同的主机元数据托管块（`host_name` / `host_ip`）。组件命名与文件采集一样按配置 ID 生成稳定后缀，保证编辑回显能定位到对应 source。

凭据只存在采集子配置中并随节点下发，不得写入仓库、日志或 stdout。生产日志只记录实例 ID、失败阶段和错误类型。

### 4. 消费语义

- 接入流程与文件采集相同：选择节点、填写源参数、创建日志采集实例。不做成 Syslog 那种「展示监听地址让对端来推」。
- 同一 `group_id` 绑到多个节点时，Kafka 按分区负载分担，不会每条日志都进每个节点。不同 `group_id` 会重复消费。界面提示这一事实，第一版不强制单节点，也不做 Lag 看板。
- 所选节点必须能访问 Kafka `advertised.listeners`。这是接入前置条件，不是平台代理 Kafka。

### 5. 前端

- 日志集成列表通过插件同步出现新类型，分类为通用。
- 接入表单复用文件采集的分区布局：上方订阅（Topic 列表、消费组），下方连接（Broker 地址），高级区放起始位点、SASL、TLS 开关。
- 必须同时实现自动接入与编辑回显：保存写扁平 `child.content`；加载时既能读扁平结构，也能从已渲染 TOML 的 `sources.kafka_subscribe_*` 反解，避免文件采集曾经出现的「保存后再编辑字段丢失」。
- 采集类型注册表按 `kafka_subscribe` 增加 Vector 插件，不得挂到现有 `kafka` 条目下。
- 中英文语言包、接入说明与图标一起交付。现有 Filebeat Kafka 文案保持「Kafka 日志 / 采集 Kafka 日志文件」，避免用户选错。

### 6. 契约与兼容

- 内置采集类型从 18 种变为 19 种。正文与时间契约测试改为枚举新数量，并要求新类型恰好声明一次 `message`、`timestamp`、`collect_timestamp`，不得声明旧正文别名。
- 不修改中心 Vector 固定拓扑，不修改 NATS subject，不迁移历史日志。
- 主机元数据 reconcile 命令仍只处理 file / docker 存量配置；新模板从一开始就带托管块，本变更不扩大该命令的所有权范围。

### 7. Vector 二进制前提

节点 Vector 必须带 Kafka source（librdkafka）。配置能保存不代表采集器能启动。发布验收用与节点同款 Vector 二进制校验渲染后的 TOML；CI 单测不依赖真实 Kafka 集群。

## Testing Decisions

好的测试只锁定用户可观察的采集方式身份、渲染后的 Vector 配置、表单保存/回显和既有日志契约，不测 Vector/Kafka/NATS 内部实现，也不把主干链路再测一遍。

- 插件模板渲染：给定 Topic、消费组、Broker、起始位点、开关态 SASL/TLS，断言渲染结果是合法 TOML，source 类型为 `kafka`，NATS sink 仍写 `vector`，enrich 含采集身份与主机元数据托管块；SASL 关闭时不出现用户名密码。
- 编辑往返：前端纯函数覆盖扁平保存、渲染后 TOML 回显、关闭 SASL 后不残留认证字段。优先扩展现有 Vector 文件/Docker 配置一致性测试，而不是新开页面快照。
- 采集类型契约：内置类型计数与 `message` / 时间字段枚举包含 `kafka_subscribe`；前端注册表能按该类型取到 Vector 插件，且 `kafka` 仍只指向 Filebeat。
- 不引入真实 Kafka、NATS 或 VictoriaLogs 集成测试。节点 Vector 能否加载 Kafka source 作为发布验收，而不是默认单测。

## Out of Scope

- 平台内置 Kafka 集群或中心系统 Vector 直接消费客户 Kafka
- 修改现有 Filebeat Kafka、监控 Kafka Exporter、CMDB Kafka 发现
- Schema Registry、Avro、Kerberos、自定义 CA、Topic 正则、多行合并、采集侧 JSON 拍平
- 消费 Lag 看板、内置分析仪表盘、强制单节点校验
- 改变提取器、日志分组、告警或查询协议

## Further Notes

需求来源是客户「第三方只支持写 Kafka、平台不内置 Kafka」的接入缺口。第一版目标是可商用验证的接入闭环，而不是 Kafka 治理产品。若现场 Kafka 必须 TLS 双向认证或 Kerberos，应另开变更，不要把本插件做成任意 librdkafka 选项表单。

## Completion Evidence

- 内置采集类型 `kafka_subscribe` / Vector 已登记，正文与时间契约计数 18 → 19。
- 节点 Vector 模板渲染明文消费、SASL/TLS 开关，NATS sink 仍写 `vector`。
- 前端保存/回显与采集方式注册表测试覆盖 Topic、Broker、消费组、SASL 关闭不残留凭据，且 `kafka` 仍只指向 Filebeat。
- 验证：`cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true uv run pytest apps/log/tests/test_log_message_contract_pure.py apps/log/tests/test_log_template_sandbox_rendering.py --no-cov`
- 验证：`cd web && pnpm exec tsx scripts/log-vector-config-test.ts`
