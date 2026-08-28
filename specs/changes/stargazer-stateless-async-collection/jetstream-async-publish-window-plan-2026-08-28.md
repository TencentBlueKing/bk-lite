# Stargazer 方案 B：JetStream 异步确认窗口实施与压测方案

Status: approved for implementation (2026-08-28)

## 1. 结论与边界

结果发布从“内存结果队列 + 单 writer + Core NATS flush”升级为：

1. 采集结果仍在 Stargazer 内存中按需编码，不引入磁盘 Outbox；
2. 不对任务或设备做成本分级，大结果和小结果统一切成有界消息；
3. 多结果按轮转方式产生消息，避免深信服、云、vCenter、拓扑快照独占发布链路；
4. 生产端使用 JetStream 异步发布，以每条消息的 `PubAck` 作为“已被 NATS 持久接纳”的确认；
5. 同时限制在途消息数和在途字节数，窗口满时对上游施加背压；
6. 同一消息重试沿用稳定 `Nats-Msg-Id`，由 JetStream 去重窗口抑制重复持久化；
7. 一个目标的所有消息均获得 `PubAck` 后，目标发布回执才进入 `CONFIRMED`。

本方案解决的是高峰期发布链路的串行等待和大结果队头阻塞。它不承诺在 Stargazer 进程崩溃时
保留尚未获得 `PubAck` 的内存数据；该情况沿用产品既有语义，由下一采集周期整轮补采。

## 2. 当前方案与方案 B 的差异

| 维度 | 当前实现 | 方案 B |
|---|---|---|
| NATS 语义 | Core NATS `publish + flush` | JetStream `publish_async + PubAck` |
| 发布并发 | 单 writer，一批完成后才取下一批 | 全局异步确认窗口，多个结果同时在途 |
| 大结果 | 分块但同一发布批次串行等待 | 懒编码、分块、结果间轮转 |
| 背压 | 只按结果个数限制队列 | 结果接纳边界 + 在途消息数/字节数双限制 |
| 成功判定 | flush 完成，无法证明消息已持久化 | 每条消息都有服务器 `PubAck` |
| 超时归因 | 队列等待和 NATS 等待容易混在一起 | `queue_wait`、`puback_timeout`、`stream_rejected` 分开 |
| 重试去重 | 投递不确定时可能重复 | 稳定 `Nats-Msg-Id` + JetStream duplicate window |
| 回滚 | 无 | 环境开关立即回到 Core NATS |

执行时序：

```text
5000 个网络结果 ─┐
                  ├─> ResultPublisher.enqueue ─> 公平轮转编码器 ─> 消息/字节双窗口
深信服大快照 ────┘                                  │
                                                    ├─ publish_async(msg-1) ─┐
                                                    ├─ publish_async(msg-2) ─┼─> JetStream
                                                    └─ publish_async(msg-n) ─┘       │
                                                                                     ▼
                           目标 CONFIRMED <─ 聚合该目标全部确认 <─ 每条 PubAck/重试
```

这里的 `PubAck` 只表示 JetStream 已接纳消息，不表示 Telegraf 已写入 VictoriaMetrics。若产品需要
展示“实例已同步”，后续必须增加消费端业务确认；不能把生产端 `PubAck` 命名为“同步完成”。

## 3. 深模块与公开接口

### 3.1 `JetStreamPublishWindow`

模块只暴露一个批量发布接口，隐藏信贷、等待集合、重试和统计：

```python
await window.publish(
    subject,
    messages,          # Iterable[JetStreamMessage]，可懒生成
    before_publish=..., # 保留目标超时前取消能力
)
```

`JetStreamMessage` 只包含 `payload` 和稳定 `message_id`。窗口对调用方返回已确认条数；失败携带
已尝试索引、已确认索引和 `delivery_detected`，以便现有目标级发布状态正确归因。

默认参数：

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `NATS_METRICS_JETSTREAM_ENABLED` | `false` | 灰度开关；完成流配置后开启 |
| `NATS_JS_PUBLISH_MAX_PENDING` | `1024` | 最大在途 PubAck 数 |
| `NATS_JS_PUBLISH_MAX_PENDING_BYTES` | `134217728` | 最大在途负载，128 MiB |
| `NATS_JS_PUBACK_TIMEOUT` | `30` 秒 | 单轮确认上限 |
| `NATS_JS_PUBLISH_MAX_ATTEMPTS` | `2` | 同一消息、同一 Msg-Id 的有限重试 |
| `NATS_JS_STREAM_NAME` | `CMDB_METRICS` | 每次发布显式声明期望流，拒绝重叠流误路由 |
| `MAX_NATS_LINES_PER_FLUSH` | `1000` | 每次交给窗口的最大行数 |
| `MAX_NATS_BYTES_PER_FLUSH` | `900000` | 每次交给窗口的最大字节数 |

字节限制必须计算 UTF-8 payload 实际大小。单条消息大于字节窗口时直接返回永久失败，禁止形成
永远等不到信贷的死锁。

### 3.2 消息身份

消息 ID 由以下稳定字段计算 SHA-256：

```text
collection_result_id + line_ordinal + sha256(payload)
```

重试不得改变 ID。修改 payload 必须产生新 ID。JetStream 流的 `duplicate_window` 必须不小于
Stargazer 最大目标发布总预算与一次重连恢复时间之和，建议首期 10 分钟。

### 3.3 目标完成边界

一个 `collection_result_id` 可产生 0..N 条消息。只有 N 条全部获得 `PubAck` 才记录当前既有的
结果事件并返回 `CONFIRMED`；任一永久失败则该目标失败。别的目标已经确认的消息不回滚，失败目标
由下一轮补采。日志不得输出 payload、响应正文或凭据。

同一个有界 chunk 混合多个目标时，失败必须携带 `attempted_indices` 和 `confirmed_indices`。已经
确认全部所属消息的目标保持成功，未全部确认的目标独立失败；窗口会在有界信贷内处理完当前微批，
不得让编码器已经取走的后续消息变成“未尝试数据空洞”。

### 3.4 格式校验

结构化结果和 Prometheus 文本在目标第一条消息进入 NATS 前完成全量扫描。缺少 metric value、
标签引号/分隔符损坏、非法时间戳、单行或单结果超限均使当前目标永久失败；禁止静默跳过坏行后把
目标记录为发布成功。合法输入的 measurement、tag、field 和 timestamp 保持既有格式。

## 4. JetStream 与消费端配置

必须预先声明专用流，不能在 Stargazer 启动阶段动态创建：

```text
stream: CMDB_METRICS
subjects: metrics.>
storage: file
retention: limits
discard: old
duplicate_window: 10m
max_age: 按可接受消费中断时长配置，建议不低于 24h
replicas: 生产集群 3；单节点验证 1
```

注意：用户拒绝的是 Stargazer 本机磁盘 Outbox；JetStream 服务端的持久化是消息系统可靠语义的
组成部分，不能关闭。Telegraf 继续用 `jetstream_subjects = ["metrics.*"]` 和固定 queue group。
根据 2026-08-28 的范围决定，本阶段不修改 Telegraf ACK 语义，也不引入 Metric Ingester；这段链路
保留为已知残余风险，生产端 PubAck 不得命名为 VictoriaMetrics 同步完成。

## 5. 上线顺序与回滚

1. 在测试环境建立 `CMDB_METRICS`，核对容量、存储和消费者积压监控；
2. 用本方案的 5000 网络设备和深信服压测脚本建立基线；
3. 先在一个 Stargazer Pod 开启 `NATS_METRICS_JETSTREAM_ENABLED=true`；
4. 同时观察 PubAck p95/p99、在途消息/字节峰值、重试数、超时数、stream bytes、consumer pending；
5. 混合运行期间 Core 生产者与 JetStream 生产者使用相同 `metrics.*` 协议，消费者协议不变；
6. 灰度稳定一个完整采集周期后逐 Pod 开启；
7. 回滚只关闭环境开关并滚动重启 Stargazer，不删除流和 durable consumer；待积压清零后再处置。

禁止在启动脚本中通过 `sleep` 等待流；流声明属于运行期可重试的部署对账动作。

## 6. 压测设计

### 6.1 数据集

- 网络设备：5000 个独立 `collection_result_id`，每设备生成可配置数量的 Influx 行；默认 20 行，
  用于覆盖大量小结果和公平调度。
- 深信服 HCI：92 个主机、1437 个虚机，生成约 6.1 MiB 结构化快照；如编码后偏差超过 5%，
  通过填充非敏感描述字段校准。
- 混合场景：网络设备与 HCI 同时进入发布器，记录网络目标完成分布以及 HCI 完成时间。

### 6.2 测试层次

1. 单元故障注入：模拟 PubAck 延迟、一次超时、重复确认、永久拒绝，锁定双窗口、稳定 Msg-Id、
   有限重试和独立目标归因。
2. 进程内并发基准：使用可控 PubAck adapter，不连接网络；用于发现串行等待、事件循环阻塞和
   内存窗口失效。该耗时不得当作生产 NATS 性能。
3. 真实 JetStream 集成基准：连接独立测试流，记录生产端总耗时、吞吐、PubAck 延迟和失败数；
   这是回答“多久推送完成”的有效数据。
4. 可选端到端观测：若另行验证 Telegraf/VictoriaMetrics，生产端 PubAck 耗时与实例可查询耗时
   必须分别报告；该项不属于本阶段代码改造的完成门槛。

### 6.3 验收门槛

- 5000 网络设备、深信服和混合三场景：`puback_timeout=0`、永久失败 `=0`；
- 故障注入的一次超时可在总预算内以相同 Msg-Id 恢复，最终无重复持久消息；
- 峰值在途消息不超过配置值，峰值在途字节不超过配置值；
- 事件循环 p99 lag 小于 100 ms，进程 RSS 不随总结果数线性无界增长；
- 混合场景中小结果持续完成，不允许等待 HCI 全部发完后才开始；
- 真实环境报告必须列出 NATS 版本、节点数、存储类型、网络 RTT、消息数、总字节数、窗口参数；
- 只有额外完成端到端实例对账时，才可在对外表述中使用“同步无丢失”；本阶段只能表述为
  “JetStream 发布无丢失”。

## 7. 可观测性

新增或锁定以下有界指标：

- `nats_js_publish_pending_messages`
- `nats_js_publish_pending_bytes`
- `nats_js_publish_pending_messages_peak`
- `nats_js_publish_pending_bytes_peak`
- `nats_js_publish_confirmed_total`
- `nats_js_puback_duration_seconds`（p95/p99）
- `nats_js_puback_timeout_total`
- `nats_js_publish_retry_total`
- `nats_js_publish_rejected_total`
- `publish_queue_wait_seconds` 与 `publish_queue_timeout_total`

生产 INFO 只记录一次目标或批次终态汇总。单消息细节放 DEBUG，且不记录 payload。

## 8. 明确不做

- 不引入本地磁盘 Outbox；
- 不为网络、云、vCenter、深信服定义高低成本等级；
- 不通过无限增大队列、超时或单批大小掩盖背压；
- 不把 PubAck 解释为消费端已入库；
- 不修改 Telegraf ACK 时机，不新增 Metric Ingester；
- 不承诺进程崩溃后恢复未确认的内存消息。
