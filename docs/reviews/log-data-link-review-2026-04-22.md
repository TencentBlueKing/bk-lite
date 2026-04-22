# 日志数据链路严重技术债务审查

## 结论

当前日志链路把节点侧 Vector、Kubernetes Vector DaemonSet、SNMP Trap 和 Syslog 等多类日志统一发布到 NATS 普通 subject `vector`，但仓库内没有为该 subject 建立持久化 stream、durable consumer、ack、死信或下游写入失败隔离配置。该设计无法证明“至少一次”传输：只要 NATS 到下游 Vector/VMLogs 的消费者不可用、重启、卡死或写入 VMLogs 抖动，日志可能在 NATS 普通发布链路中被确认发送后丢失，且平台侧缺少可直接定位丢数、堆积和重试状态的治理点。

这不是局部代码风格问题，而是节点探针到 NATS、NATS 到下游写入链路之间的可靠性契约缺失。

## 关键证据

1. 节点侧 Vector 文件日志模板只把数据发到普通 NATS subject `vector`，未声明持久化 buffer、ack 策略、死信或按实例隔离 subject。
   - `server/apps/log/support-files/plugins/Vector/file/file.child.toml.j2`
   - 核心配置：`type = "nats"`、`subject = "vector"`、`url = "${NATS_PROTOCOL}://${NATS_SERVERS}"`。

2. 节点侧 Docker 日志模板同样把全部 Docker 日志发到同一个普通 subject `vector`。
   - `server/apps/log/support-files/plugins/Vector/docker/docker.child.toml.j2`
   - 核心配置：`type = "nats"`、`subject = "vector"`。

3. 默认 Vector 采集器配置把 Filebeat/Logstash、SNMP Trap、Syslog 全部汇聚到同一个 subject `vector`，没有按来源、租户、节点或实例拆分。
   - `server/apps/node_mgmt/support-files/collectors/Vector.json`
   - `default_vmlogs`、`snmp_trap_nats`、`vmlogs_base` 均发布到 `subject = "vector"`。

4. Kubernetes 日志采集 DaemonSet 也把集群日志统一发到 subject `vector`。
   - `agents/webhookd/bk-lite-log-collector.yaml`
   - `deploy/dist/bk-lite-kubernetes-collector/bk-lite-log-collector.yaml`
   - 核心配置：`sinks.nats_sink.type: nats`、`subject: vector`。

5. 边缘代理的 NATS 权限仅允许监控用户 publish `vector`，没有为 `vector` 配置 JetStream stream；仓库中可见的 JetStream 配置只镜像对象存储 stream `OBJ_bklite`。
   - `agents/webhookd/infra/proxy/conf/nats/nats.conf.template`
   - `agents/webhookd/infra/proxy/conf/nats/jetstream.json`

6. 服务端 NATS 监听框架的 JetStream 明确关闭，且只针对 `bklite.js.>` 这类 RPC subject 建 stream，不覆盖日志 subject `vector`。
   - `server/config/components/nats.py`
   - `server/nats_client/management/commands/nats_listener.py`

## 影响

- 下游 Vector/VMLogs 不可用或写入变慢时，普通 NATS subject 无持久化消费语义，日志生产端可能认为发送成功，但后续实际没有可靠落库。
- 所有日志来源共用 `vector`，消费侧无法按来源、集群、节点、实例隔离回压和重试；一个高流量来源可能拖垮全局日志写入路径。
- 链路缺少可审计的 ack、lag、redelivery、dead-letter 和 drop 指标，事故时难以判断丢数发生在探针、NATS、下游 Vector 还是 VMLogs 写入阶段。
- 后续如果增加新的日志来源，默认继续进入同一个 subject，会扩大 fan-in 和高基数标签治理风险。

## 为什么本次不直接修复

安全修复需要同时定义并验证以下链路契约，不能只改单个模板：

- NATS subject 命名和隔离策略，例如按日志来源、租户、集群或实例拆分。
- `vector` 日志流是否迁移到 JetStream，以及 stream retention、max bytes、ack wait、max deliver、DLQ 和重放策略。
- 下游 Vector 到 VMLogs 的消费组、durable、ack 时机、批量写入、失败重试、限流和磁盘 buffer。
- 现有节点探针、Kubernetes DaemonSet、边缘代理和平台查询/告警对字段契约的兼容性。

在缺少这些部署与消费侧约束的情况下，直接把模板切到新 subject 或 JetStream 可能导致现网日志中断。因此本次以审查文档形式提交，建议作为日志链路可靠性专项整改入口。

## 建议整改方向

1. 为日志链路建立持久化消费契约：将 `vector` 迁移到 JetStream 或等价可靠队列，明确 durable consumer、ack 时机、重试上限、DLQ 和回放策略。
2. 拆分 subject：至少区分 `logs.file`、`logs.docker`、`logs.kubernetes`、`logs.syslog`、`logs.snmptrap`，并在 payload 中保留稳定的 `collector`、`collect_type`、`instance_id`、`node_ip`、`cluster_name`。
3. 为节点侧和 Kubernetes Vector 配置磁盘 buffer 与容量上限，避免 NATS 短时不可用时直接扩大丢数风险。
4. 为下游 Vector 到 VMLogs 增加写入失败、重试、丢弃、lag、批量大小、flush 延迟和 VMLogs HTTP 状态码指标。
5. 在平台侧暴露日志链路健康检查：采集端发送速率、NATS 堆积、消费延迟、VMLogs 写入失败率、最后成功写入时间。

