# RocketMQ 监控接入指南

本能力采集 RocketMQ 4.x 集群的 Broker 吞吐、CommitLog 磁盘占用、主题与消费者组当前偏移量、消费堆积和死信主题偏移量。RocketMQ 5.x 不在本能力范围内。

## 前置要求

- 采集节点能够访问 NameServer，默认端口 9876。多个地址时，能访问其中至少一个即可。
- 集群未开启访问控制时，访问密钥和密钥都留空。开启后两项成对填写。
- NameServer 中登记的 Broker 地址从采集节点不可达时，填写一个可连通的 Broker 地址。留空则使用登记地址。

## 接入步骤

1. 从实际采集节点确认 NameServer 地址可以连通。
2. 填写 NameServer 地址。多个地址用英文逗号分隔。
3. 按需要填写 Broker 地址、访问密钥和密钥。
4. 填写采集间隔（默认 60 秒，建议不少于 30 秒）。
5. 在监控对象表格中选择节点，填写同一 NameServer 地址、可选 Broker 地址、实例名称和可选分组。
6. 保存后等待至少一个采集周期。

## 接入前校验

```bash
nc -vz namesrv.example.com 9876
```

命令应显示端口可达。请在实际采集节点上执行。

## 页面字段说明

| 页面字段 | 是否必填 | 说明 |
| --- | --- | --- |
| NameServer 地址 | 是 | 一个或多个 `host:port`，多个地址用英文逗号分隔，默认端口 9876。 |
| Broker 地址 | 否 | 登记地址不可达时填写一个可连通的 `host:port`。留空则使用登记地址。 |
| 访问密钥 | 否 | 开启访问控制时与密钥成对填写。未开启时留空。 |
| 密钥 | 否 | 开启访问控制时与访问密钥成对填写。未开启时留空。 |
| 间隔 | 是 | 采集周期，单位秒，默认 60，建议不少于 30。 |
| 节点 | 是 | 能够访问该 NameServer 的采集节点。 |
| 实例名称 | 是 | 平台内展示的实例名称。 |
| 组 | 否 | 实例所属分组。 |

## 接入后验证

保存并等待一个采集周期后，在平台确认以下指标可查询：

- 采集存活（`bklite_rocketmq_up`）
- Broker 写入 TPS（`bklite_rocketmq_broker_tps`）
- Broker 读取 TPS（`bklite_rocketmq_broker_qps`）
- CommitLog 磁盘占用率（`bklite_rocketmq_broker_commitlog_disk_ratio`）
- Topic 当前偏移量（`bklite_rocketmq_producer_offset`）
- 消费者组当前偏移量（`bklite_rocketmq_consumer_offset`）
- 消费 TPS（`bklite_rocketmq_consumer_tps`）
- 消费堆积（`bklite_rocketmq_group_diff`）
- 死信主题偏移量（`bklite_rocketmq_group_dlq`）

死信主题偏移量的主题名是 `%DLQ%` 加上消费者组名。

## 常见问题

### 采集存活为 0

- 从实际采集节点检查 NameServer 地址、端口和网络。
- 集群开启访问控制时，确认访问密钥和密钥成对填写且没有首尾空格。

### 没有 Broker、主题或消费指标

- 登记的 Broker 地址不可达时，填写可连通的 Broker 地址后重新保存。
- 集群上没有对应的主题或消费者组时，相关指标不会出现。
