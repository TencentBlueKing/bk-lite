# 方案 B：5000 网络设备与深信服发布压测报告

Date: 2026-08-28

## 1. 结论

方案 B 已通过生产发布入口的模拟与真实 JetStream 集成压测。真实 NATS 场景共持久化
203058 条消息，与网络、深信服及混合三场景输入总数完全一致；`PubAck` 超时、重试耗尽、
永久失败和目标失败均为 0。

本轮计时覆盖：

```text
BufferedResultPublisher
  -> NatsResultPublisher
  -> 结构化结果编码与严格格式校验
  -> 结果间公平轮转和有界拆分
  -> JetStream 异步窗口
  -> 逐消息 PubAck
```

不再使用旧报告中直接调用 `JetStreamPublishWindow.publish()` 的耗时作为方案结论。报告仍只证明
生产端被 JetStream 持久接纳，不代表 Telegraf 已写入 VictoriaMetrics。根据 2026-08-28 的范围
决定，本阶段保持 Telegraf 现状，不实施消费端延迟 ACK 或 Metric Ingester。

## 2. 环境

- 主机：本地 macOS arm64；
- NATS Server：2.8.4，单节点；
- JetStream：file storage，隔离临时目录；
- 流：`CMDB_METRICS`，subject `metrics.>`，duplicate window 600 秒；
- nats-py：Stargazer 锁定版本 2.10.0；
- 网络：Stargazer 与 NATS 均在本机回环地址；
- 结果队列：250 个目标，50 目标/批，4 个发布 worker；
- 在途窗口：1024 条 / 128 MiB；
- PubAck 超时：30 秒；最大尝试：2；
- 消费端：未启动 Telegraf/VictoriaMetrics。

上述环境不等于客户生产环境，生产 NATS 节点数、磁盘、TLS、网络 RTT 和消费积压都会改变结果。

## 3. 数据集与真实 JetStream 结果

网络场景使用 5000 个独立目标，每目标 20 条结构化记录，经生产编码器生成 100000 条 Influx
Line Protocol 消息。深信服场景使用 92 个主机和 1437 个虚机，共 1529 条记录；编码后的实际
payload 为 6139859 字节，接近客户日志中的约 6.1 MiB 大结果。

| 场景 | 目标 | PubAck 消息 | payload 字节 | 完成时间 | 吞吐 | 超时/重试/失败 |
|---|---:|---:|---:|---:|---:|---:|
| 5000 网络设备 | 5000 | 100000 | 47847517 | 10.476877 s | 9544.83 msg/s | 0/0/0 |
| 深信服 HCI | 1（92 主机 + 1437 VM） | 1529 | 6139859 | 0.201537 s | 7586.68 msg/s | 0/0/0 |
| 混合 | 5001 | 101529 | 53778202 | 10.820441 s | 9383.07 msg/s | 0/0/0 |

混合场景中的深信服目标在 1.025900 秒完成，网络目标在 10.819874 秒完成。深信服没有等待全部
网络目标结束，也没有独占发布链路。流最终状态为 203058 条消息，等于三场景输入总和。

## 4. 容量和事件循环结果

| 场景 | 结果队列峰值 | 在途消息峰值 | 在途字节峰值 | Event loop p99 | 峰值 RSS |
|---|---:|---:|---:|---:|---:|
| 5000 网络设备 | 250 | 1024 | ≤1171928 | 45.266 ms | 108.28 MiB |
| 深信服 HCI | 1 | 1024（全局历史峰值） | ≤1171928 | 24.207 ms | 108.28 MiB |
| 混合 | 250 | 1024 | ≤1171928 | 58.253 ms | 113.11 MiB |

真实 JetStream 的 PubAck p95/p99 分别为 42.987/43.158 ms。所有场景结束时：

- `pending_messages=0`；
- `pending_bytes=0`；
- `puback_timeout_total=0`；
- `retry_total=0`；
- `rejected_total=0`。

## 5. 自动化故障覆盖

自动化测试另覆盖：

1. 首次 PubAck 超时后使用同一 `Nats-Msg-Id` 有限重试；
2. direct 主机回调同一结果重试 ID 稳定，不同采集运行 ID 不碰撞；
3. 混合 chunk 中一个目标拒绝时，已确认目标保持成功；
4. 窗口较小时，一个拒绝不会让当前微批后续消息变成未尝试数据空洞；
5. provider、`publish_async()` 和 PubAck 等待统一受超时预算约束；
6. 迭代器异常、超限和调用取消均清理在途任务与字节信贷；
7. 格式错误在目标第一条 NATS 消息之前整体拒绝，不再静默跳过坏行；
8. 单消息/单结果的行数和字节上限；
9. Core NATS 回退路径保持单 worker 和原有调用接口。

## 6. 客户环境复测

先由部署系统创建覆盖 `metrics.>` 的 `CMDB_METRICS` 流，再在 Stargazer 环境执行：

```bash
NATS_URLS='nats://<test-nats>:4222' \
  .venv/bin/python scripts/benchmark_jetstream_publisher.py \
  --transport jetstream --scenario all
```

认证信息只通过客户环境注入，禁止写入命令历史、报告或仓库。测试流应与生产流隔离，避免压测
消息进入正式 VictoriaMetrics。

## 7. 剩余边界

- 本报告不证明 Telegraf/VictoriaMetrics 最终入库完整；
- Telegraf 当前 ACK 语义保持不变，属于已接受的残余风险；
- 上线前仍需在三节点 JetStream、生产同等 TLS/RTT/磁盘条件下复测；
- 灰度期间监控 PubAck p95/p99、超时、重试、流存储、consumer pending 和 Telegraf/VM 错误；
- 日志中的“发布确认”只能表示 JetStream PubAck，不能命名为“VM 同步完成”。
