# Stargazer 生产日志后续优化实施方案（2026-09-03）

Status: implemented，local verification passed，pending production verification

Baseline: `snmp-160-concurrency-optimization-implementation-plan-v2-2026-09-02.md` 已实施版本及
2026-09-03 新版本生产日志。本方案只描述单个 Stargazer/Sanic Worker 内部设计；Worker 数量、请求
分配和跨 Worker 协调不属于本次设计。

## 1. 生产验证结论

1. `SnmpEnginePool` 已消除每目标 Engine/MIB/PLY 重建：单进程 RSS 最高约 393 MiB，未再出现旧版本
   5.1 GiB 跨整轮增长；Engine 的轮换、空闲关闭和目标预算正常。
2. 事件循环 P99 从 10～15 秒下降到最高约 2.8 秒，但仍未满足 `<1s` 门禁；高延迟与单进程 CPU
   接近 100% 同时出现。
3. SNMP WALK 仍在事件循环内累积完整 PySNMP `varBind` 表，再集中执行 `prettyPrint`、OID 判断和结果
   转换；网络拓扑存在相同模式。
4. 单 Worker 已有容量 160 的应用级 `BufferedResultPublisher`，但容量只覆盖队列元素，不覆盖 Writer
   已取走的活动批次；4 个 Writer、每批 50 个结果时，完整 payload 实际驻留上限可高于 160。
5. 每个 Run 还创建 4 个发布回执观察任务和容量 160 的观察队列。它不会复制 payload，但
   `PendingPublish.result` 会继续引用同一结果，所有权没有完全收敛到应用级发布 Module。
6. 发布超时预算不闭合：单 flush 最多 1000 行，JetStream 窗口 256 条、PubAck 30 秒、最多 2 次尝试，
   故障路径理论上可超过 240 秒，而目标总发布期限只有 120 秒。
7. JetStream 窗口发现首个错误后仍继续启动后续窗口；大结果和慢 PubAck 会长期占用 Writer，生产日志
   已出现“队列为 0、发布终态为 0，但活动批次年龄仍为数百秒”。

## 2. 锁定的不变量

### 2.1 单 Worker 并发

```text
CollectionScheduler active_targets <= 160

网络配置、网络拓扑及其他配置采集共同使用这 160 个目标槽位；
workload 数值只表达软权重和空闲借用；
SNMP 不拥有另一套独立的 160 并发池。
```

本轮删除 `SNMP_MAX_IN_FLIGHT=160` 的独立准入语义。同步 SDK、远程作业等确有不同资源成本的技术舱壁
继续服从全局 160，不改变本方案的 SNMP 结论。

### 2.2 结果所有权

```text
目标完成
  +-- 失败 / 不可达 / 空结果
  |    -> Run 更新固定计数和最多 3 条样本
  |    -> 立即释放完整结果
  |
  +-- 成功非空
       -> 目标执行前已获取应用级 payload permit
       -> Publisher 成为完整 payload 唯一长期所有者
       -> 等待队列、活动 Writer、重试合计不得超过 160 个 payload
       -> PubAck / 最终失败 / unknown 后释放 permit 和全部强引用

全部目标终态 + 全部发布终态
  -> RunSummary
  -> round-complete（保持既有条件）
```

Run 只持有轻量 receipt/目标标识、固定计数、有限错误类别和有限样本，不持有可重试 payload。

### 2.3 发布期限

一次结果从进入发布路径开始只有一个绝对 deadline。队列等待、编码、JetStream 信贷等待、PubAck 和
重试都消费同一预算；内部任何步骤不得创建比剩余总预算更长的局部超时。

## 3. Module 与 Interface

### 3.1 `BufferedResultPublisher`

保留 `enqueue(request, result, lease) -> receipt` 小 Interface，内部承担：

- 应用级 payload permit；
- 有界队列与活动批次统一计数；
- Writer 生命周期；
- payload 终态释放；
- 批次公平性和 shutdown 排空。

队列 `qsize()` 只作为排队观测，不再等同于 payload 总量；新增 pending/peak 指标表达目标执行、排队、
活动和重试合计。permit 在目标执行前获得，失败/不可达/空结果立即释放；成功非空结果把 permit 与
payload 一并交给 Publisher，只在 receipt 完成后释放。这样不会在 `enqueue()` 等待 permit 时先生成并
保留一批未计数的大 payload。

### 3.2 `JetStreamPublishWindow`

`publish()` 隐藏消息数/字节双信贷、绝对 deadline、PubAck 和有限重试：

1. 每条消息继承所属结果的绝对 deadline；
2. 信贷等待和单次 PubAck 都使用 `min(局部上限, deadline 剩余时间)`；
3. 任一窗口首次失败后停止启动后续消息，取消仍在途任务并返回已尝试/已确认索引；
4. 已尝试未确认仍为 delivery unknown，未尝试结果允许在剩余总期限内有限重试；
5. 稳定 `Nats-Msg-Id` 和既有 Stream/subject 不变。

### 3.3 SNMP WALK

对外 `collect()`/`bulkCmd()` Interface 不变，内部改为：

- 每收到一行立即转换为普通 Python 字典；
- 不跨 PDU 保存完整 PySNMP `varBind` 表；
- 每个 PDU 或固定行数主动 `await asyncio.sleep(0)`；
- GETBULK fallback 前丢弃本次已转换的部分结果，避免重复；
- 最大 PDU、行数、响应字节和 deadline 不变；
- 网络配置和网络拓扑采用相同增量原则。

## 4. 实施顺序

### 阶段 A：发布故障快速收敛

1. 红灯：窗口首批 PubAck 失败后不得继续启动下一批消息。
2. 红灯：绝对 deadline 覆盖信贷等待和 PubAck 重试。
3. 实现 fail-fast、逐消息 deadline 和完整 attempted/confirmed 归因。
4. 将 JetStream pending/waiting/PubAck/retry/rejected 指标加入周期容量日志。

### 阶段 B：payload 统一容量

1. 红灯：Writer 取走元素后，新的 enqueue 仍不得突破 160 个未终态 payload。
2. permit 覆盖等待队列、活动批次和重试。
3. Run 回执观察层不再持有完整 `TargetCollectionResult`；重试 payload 只在 Publisher 内部保存。
4. 发布终态、RunSummary、失败样本和 shutdown 语义保持不变。

### 阶段 C：发布公平性

1. 大结果与小结果混合压测复现 Writer 队头阻塞。
2. 每个活动结果每轮最多发送一个有界 chunk；未完成结果回到当前活动批次的 task/subject lane 队尾。
3. 单次 transport quantum 与 JetStream 消息窗口对齐，避免一个调用串行消耗多个窗口。
4. 健康 NATS 下保持微批；故障时活动批次不得超过统一 deadline。

### 阶段 D：SNMP 增量 WALK

1. 红灯：多 PDU 成功 WALK 在处理期间持续让出事件循环。
2. 红灯：GETBULK/GETNEXT 不返回或保留完整原始 PySNMP 表。
3. 网络配置逐行生成接口字典；网络拓扑逐行生成 OID 记录。
4. fallback、非递增 OID、最大行数/字节/PDU、取消和错误分类回归。

### 阶段 E：并发与压测

- 160 个全无响应 SNMP；
- 160 个成功低/中/高接口数 SNMP；
- 成功、无响应、GETBULK fallback 混合；
- 5～6 MiB 大结果和大量小结果同时发布；
- PubAck 正常、变慢、永不返回和间歇失败；
- 连续三轮验证 RSS 平台、Task/Future/Engine/FD 释放。

## 5. 验收门禁

- 单 Worker `active_targets <= 160`，SNMP 无独立并发池；
- Event Loop P99 `<1s`，目标为 `<200ms`；
- 完整待发布 payload（等待＋活动＋重试）总数 `<=160`；
- 健康 NATS 下成功结果发布确认率 100%；
- 故障 NATS 下在统一 deadline 内进入明确的 failed/unknown 终态；
- 首个窗口失败后不再启动后续消息；
- 不再出现发布队列已空但活动批次超过总发布期限；
- 多轮 RSS 进入稳定平台，不随已完成目标或 Run 数线性增长；
- 既有失败抑制、稳定 Msg-Id、RunLease、重入保护、RunSummary 和 round-complete 不变。

## 6. 范围外

- CMDB/Telegraf 的周期触发来源；
- 主机监控、Host Remote callback 和监控并发；
- 多 Worker 的总容量、路由和协调；
- SNMP 子进程或 IPC；
- 通过单纯延长 timeout、降低 160 或增加发布队列容量掩盖问题。

## 7. 回滚

发布期限/窗口 fail-fast、payload permit、发布公平量子、SNMP 增量 WALK 和 SNMP 独立准入删除分别保持
可独立回滚。不得回滚到每目标创建 `SnmpEngine`、跨整轮保留完整结果或失败指标进入 metrics NATS。

## 8. 实施结果

### 8.1 已完成

- 删除 `SNMP_MAX_IN_FLIGHT` 的应用准入配置；SNMP 的 `capacity_group` 只保留分类和指标用途，未配置独立
  信号量时直接服从单 Worker 全局 160。
- `snmp_facts.py` 的 GETBULK/GETNEXT 和 `snmp_topo.py` 的批量/降级 WALK 均改为逐 PDU 转换；原始
  PySNMP 对象不再跨 PDU 累积，每个 PDU 后主动让出事件循环。
- `BufferedResultPublisher` 增加应用级 payload permit，目标执行、等待队列、活动 Writer 和 transport
  重试合计不超过 160；周期容量日志和健康指标分别暴露当前值与峰值。
- 默认 metrics JetStream 负责 transport 有限重试。Run 的发布观察队列只保留目标、receipt、deadline 等
  轻量字段，不再保留完整 payload；测试注入的旧 Publisher 仍保留原有 Run 级重试兼容语义。
- 绝对 deadline 已贯穿元数据持久化前检查、指标编码前后、JetStream 信贷等待、PubAck 和 transport
  重试；超时后不会继续产生新的网络发送。
- JetStream 首个 PubAck 拒绝/超时后立即停止后续窗口，并取消同窗口尚未终态的 PubAck；不再等整批
  局部 30 秒超时全部耗尽。
- task/subject lane 保持轮转，每个目标每轮只编码和发送一个 chunk；单次 chunk 的行数动态取
  `min(MAX_NATS_LINES_PER_FLUSH, NATS_JS_PUBLISH_MAX_PENDING)`，不再让一个 flush 串行跨越多个消息窗口。
- 周期容量日志新增 payload 未终态数、JetStream 在途/等待信贷、PubAck P99、超时、重试和拒绝计数。

### 8.2 新增或强化的回归/压力场景

- 160 个 SNMP WALK 并发、每目标 20 个 PDU，验证逐 PDU 让出事件循环且模拟调度延迟小于 100 ms；
- 5000 个 JetStream 消息，验证消息/字节双窗口和任务释放；
- 约 5.8 MiB 单目标快照分片，验证全部 chunk PubAck 及稳定 Msg-Id；
- 5000 个 32 KiB 成功结果，验证 Run 未结束时已完成 payload 不跨整轮保留；
- Writer 已取走结果后继续验证 payload permit，总数不得突破容量；
- PubAck 正常、首次失败后成功、永不返回、同窗口一条拒绝一条挂起以及绝对 deadline 到期；
- 大小结果同 subject、不同 subject 的发布公平性，以及 transport quantum 与 JetStream 窗口对齐。

### 8.3 本地验证证据

```text
影响范围核心回归：221 passed, 2 warnings, 6.46s
统一采集端到端回归：14 passed, 1 skipped, 1 warning, 16.88s
压力场景组合：4 passed, 1 warning, 0.74s
压力场景进程最大 RSS：97,730,560 bytes（约 93.2 MiB）
git diff --check：通过
Python compileall（core/plugins/tasks）：通过
```

全量 `agents/stargazer/tests` 当前结果为 `1073 passed, 6 skipped, 69 failed`。其中本次相关的发布重试兼容
回归已修复并单独通过；其余失败来自当前工作区基线（缺失 `core.task_queue`、`tasks.handlers.plugin_handler`、
`mssql` fixture 等）以及本次明确排除的 Host Remote/监控测试。直接从 Stargazer 根目录无筛选执行 pytest
还会在 `common/.../test_sync.py` 收集阶段因缺失 `home_application` 失败。

本地模拟压力结果不能替代生产验收。部署后仍须用同一单 Worker 容量口径观察至少三轮：
`event_loop_lag_p99_ms < 1000`、`publish_payloads_pending <= 160`、活动批次年龄不超过统一发布期限，且 RSS
形成稳定平台；目标值仍为 Event Loop P99 `<200 ms`。

### 8.4 2026-09-04 日志复核后的补充实施

本次按新版本日志再次对照当前架构后，补齐以下缺口；仍不处理跨 Run 同设备并发采集，也不涉及监控链路：

1. **Payload permit 前移到目标执行前。** 原实现只在 `enqueue()` 内申请 permit，目标可能先完成并持有
   完整 payload，再阻塞等待发布容量，导致实际强引用数高于 `publish_payloads_pending`。现在执行前预留，
   失败/不可达/空结果立即归还，成功结果转交 Publisher，PubAck/最终失败/unknown 后归还。
2. **Run 准入增加目标总预算。** 保持 `MAX_ACTIVE_RUNS=16`，新增
   `MAX_ACTIVE_RUN_TARGETS=4000`，避免多个大 Run 仅按数量同时进入内存和调度队列。空闲时允许一个合法
   超大 Run 独占执行，防止永久饥饿；该 Run 结束前拒绝其他 Run，并返回既有 busy/429。
3. **IP 预检失败增加有界日志。** 每个 Run 最多输出一条 `event=ip_precheck_failed` WARNING，包含失败
   总数和最多 3 个 `target|error_code` 安全样本；不记录凭据、异常正文或 payload，出站策略拒绝不归入
   此事件。
4. **容量日志强化。** 默认周期从 180 秒调整为 30 秒；新增 Run 准入目标、payload 当前值/容量、
   JetStream 超时/重试/拒绝的周期增量，并将 payload 高水位、活动批次超过总期限、信贷等待、PubAck
   超时/拒绝纳入“需关注”判定。SNMP Engine 文案明确区分活跃数、存活总数和安全上限。
5. **观测正确性。** P95/P99 样本按 5 分钟时间窗口淘汰，空闲后不再长期展示历史峰值；资源采样增加
   cgroup v1 回退，兼容客户环境无法读取 v2 指标的情况。

补充回归与模拟压力结果：

```text
核心生命周期/准入/日志回归：123 passed
调度、HTTP、SNMP、JetStream/NATS 回归：129 passed
5000 网络设备 + 深信服 + 混合发布模拟：全部 203058 行确认，失败 0
网络 5000 目标：Event Loop P99 29.314 ms，峰值 RSS 91.23 MiB
混合 5001 目标：Event Loop P99 27.234 ms，峰值 RSS 92.75 MiB
模拟发布进程最大 RSS：97,255,424 bytes（约 92.75 MiB）
```

上述为本机模拟 PubAck 结果，不代替生产三轮验收；生产门禁仍以第 5 节为准。
