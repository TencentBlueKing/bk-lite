# Stargazer SNMP 160 并发与结果生命周期优化实施方案 V1（已被替代）

Status: superseded；由 V2 替代，不得据此实施（2026-09-02）

> MR #5115 已证明每目标 Engine/MIB/PLY 与 uvloop 地址 LRU 是事故的主要根因，改变了本方案对子进程和
> RSS 根因的判断。新的实施与决策统一以
> [`snmp-160-concurrency-optimization-implementation-plan-v2-2026-09-02.md`](snmp-160-concurrency-optimization-implementation-plan-v2-2026-09-02.md)
> 为准。本文件只保留为讨论历史。

Revision: 2026-09-02 根据本轮确认补充第 5 节流式所有权契约、完成屏障和释放时点。

## 1. 决策摘要

本方案只处理 Stargazer 配置采集主链在 160 目标并发口径下的事件循环、内存、SNMP 协议成本和
失败分类问题。

建议批准以下组合方案：

1. 保持当前运行时实例的全局目标并发硬上限为 `160`；
2. 结果改为逐目标流式终结，发布终态确定后立即释放完整结果对象；
3. 新增受管 `SnmpExecutionRuntime`，把 PySNMP 协议执行从 Sanic 主事件循环隔离到子进程；
4. 每个 SNMP 子进程复用长生命周期 `SnmpEngine`；
5. 合并 SNMP probe 与 collect 的首个 system GET；
6. SNMP v2c/v3 的 interface WALK 优先使用 GETBULK，并提供有界 GETNEXT fallback；
7. 完成前述优化并通过 160 并发压测后，将 SNMP 技术容量从 `100` 提升到全局 `160`，不再形成
   低于产品并发口径的第二道硬限制；
8. 把无响应、认证失败、协议错误和整轮凭据失败分开统计，不再把大量无响应笼统汇总为
   `credentials_exhausted`。

## 2. 已锁定范围

### 2.1 本次必须保持

- 当前运行时实例的全局目标并发硬上限保持 `160`；
- 只有成功且非空的正常采集数据进入 metrics NATS/JetStream；
- 现有 NATS 微批、PubAck、稳定 Msg-Id、有限重试和 round-complete 语义不变；
- 多凭据顺序、明确认证失败冷冻、成功亲和及单目标单终态不变；
- 现有 workload 公平调度保持不变；本方案只消除 SNMP 低于 160 的技术硬限制；
- 一个 Run 仍由现有 CollectionRuntime 管理，不引入新的业务任务队列。

### 2.2 明确排除

以下内容不分析、不修改，也不作为本方案验收前置条件：

- CMDB 定时任务、周期配置以及 Telegraf 的触发机制；
- 所有主机监控、monitor HTTP、Host Remote callback 和监控并发；
- Sanic Worker 数量、生产镜像版本和多 Worker 配置；
- NATS Server、Stream、ACL、底层依赖和现有 queue group；
- 配置文件采集 callback/control RPC 链路；
- 跨 Pod 或跨进程共享的分布式 160 信号量。

### 2.3 本次暂不处理

- `MAX_ACTIVE_RUNS=16` 改为按目标数或预计成本准入；
- 对长期无响应设备实施跨轮次退避或跳轮；
- 修改上游对 429 的重试协议；
- 通过增加 timeout 掩盖事件循环延迟。

这些问题会改变上游触发或采集及时性语义。先完成本方案并重新观察 backlog、吞吐和资源曲线，再以
独立变更决策。

## 3. 当前问题与证据

### 3.1 Sanic 主事件循环被 SNMP 工作拖慢

生产日志显示：

| 阶段 | CPU | RSS | Event Loop P99 |
| --- | ---: | ---: | ---: |
| 空闲 | 0.08% | 91 MiB | 1.6 ms |
| 网络采集开始 | 49.6% | 595 MiB | 1.45 s |
| 约 100 个目标执行 | 97.2% | 3.04 GiB | 5.27 s |
| 持续约 100 个目标 | 93.1% | 4.80 GiB | 11.57 s |
| 后续高负载 | 93%～100% | 4.88～5.13 GiB | 13～15.19 s |

PySNMP 的网络等待虽然是异步的，但 ASN.1/PDU 编解码、varBind/OID 处理、timeout callback、接口结果
转换和异常处理仍与 Sanic 共用 Python 进程和主事件循环。大量无响应目标在相近时间到期，会形成集中
callback 和对象释放峰值。

结论：10～15 秒不是 NATS 或单次任务 timeout 本身，而是主事件循环持续得不到及时调度。

### 3.2 结果所有权覆盖整个 Run

当前对象保留链为：

```text
CollectionScheduler._RunState.results
  -> PendingPublish
    -> TargetCollectionResult
      -> StructuredMetricsPayload
        -> 设备与接口数据
```

Scheduler 为每个目标保留结果槽；Executor 又保存整轮结果、发布状态和发布回执，直到整个 Run 完成后
才统一生成汇总。日志结束时约有 9886 个目标已经完成、所属 Run 尚未结束，RSS 为 5.13 GiB。

这条无界保留链是已经由代码确认的内存设计问题。PySNMP 对象、IPC/序列化临时对象和 Python allocator
高水位可能叠加，但各自占比仍须用 heap profile 验证。

### 3.3 产品 160 被 SNMP 技术容量限制为 100

当前存在两层容量：

```text
全局目标硬上限：160
SNMP capacity_group 硬上限：100
```

所以配置采集在 workload 层虽然可以借用空闲槽，SNMP 配置采集仍无法超过 100；加入其他执行类型后
才会看到全局活跃目标高于 100。

本方案最终语义必须是：

```text
所有活动目标总数 <= 160
只有 SNMP 配置采集积压时，SNMP 活跃目标可以达到 160
```

但解除 SNMP=100 必须在结果流式释放和主事件循环隔离完成后实施，不能在当前执行模型上直接放大压力。

### 3.4 SNMP 无响应被错误汇总

已完成的 2045 个网络目标中，成功 402、失败 1643，失败率约 80.3%。大量底层错误实际是
`No SNMP response received before timeout`，但在单凭据场景中最终汇总为 `credentials_exhausted`。

SNMP 无响应只能说明没有收到协议响应，不能直接证明：

- IP 不可达；
- community/账号错误；
- SNMP 服务未开启；
- UDP 161 被阻断；
- 设备是否因为限速而丢包。

错误分类必须保留这种不确定性，且无响应不得冷冻凭据。

## 4. 目标架构

```text
CollectionRuntime
  |
  | 全局 active target <= 160
  v
CollectionScheduler
  |  handler 不再返回整轮结果数组
  v
TargetCollectionExecutor
  |
  +---- 非 SNMP 插件：保持现有执行路径
  |
  +---- SNMP 插件
  |       v
  |   SnmpExecutionRuntime.execute(request)
  |       |
  |       +-- 有界 IPC / request id / generation / fence
  |       v
  |   受管 SNMP 子进程池
  |       +-- 每个进程一个长生命周期 SnmpEngine
  |       +-- 合并 system probe + collect
  |       +-- GETBULK + 有界 GETNEXT fallback
  |       +-- 只返回可序列化的归一化结果，不返回 PySNMP 对象
  |
  v
RunResultSink.accept(result)
  +-- 失败/空结果：累计固定大小汇总 -> 立即释放
  +-- 成功非空：转交现有有界 Publisher
                       |
                       +-- 微批与 PubAck 语义不变
                       +-- 发布终态后立即释放
  v
RunResultSink.finish()
  +-- 等待本 Run 所有目标和发布终态
  +-- 生成 RunSummary
  +-- 按既有条件生成 round-complete
```

目标架构增加两个深模块，复杂度集中在各自实现内部，不扩散到调用方。

## 5. 深模块一：RunResultSink

### 5.1 Interface

建议接口：

```python
class RunResultSink:
    async def accept(self, index: int, result: TargetCollectionResult) -> None: ...
    async def finish(self) -> RunFinalization: ...
```

调用方只需要知道：

- 每个目标完成后调用一次 `accept`；
- `accept` 完成后 Executor 不再拥有完整结果；
- `finish` 只在所有目标都已提交后调用；
- `finish` 等待成功结果的发布终态并返回固定大小汇总。

发布确认、有限重试、错误采样、计数、对象释放和排空逻辑全部隐藏在 Module 内部。

### 5.2 锁定的流式结果生命周期

本次实施必须遵循以下生命周期，不允许在实现阶段退回整轮结果保留：

```text
目标完成
  ├─ 失败 / 不可达 / 空结果
  │    -> 更新成功/失败等固定计数
  │    -> 更新有界错误类型计数
  │    -> 保留最多 3 条采集失败样本
  │    -> 立即释放 TargetCollectionResult
  │
  └─ 成功且包含有效指标
       -> 等待有界 Metrics 发布队列接收
       -> Publisher 成为 payload 唯一所有者
       -> Scheduler / Executor / RunResultSink 不再持有 payload
       -> PubAck / 最终失败 / 发布状态未知
       -> 更新发布终态计数
       -> 立即释放 payload、receipt 和临时编码对象

全部目标完成
+ 全部成功结果取得发布终态
  -> 生成 RunSummary
  -> 写终态汇总日志
  -> 满足既有条件时发布 round-complete marker
  -> 释放 RunResultSink 的固定大小状态
```

所有权转移规则：

1. `accept` 调用前，Executor 是 `TargetCollectionResult` 的唯一所有者；
2. 失败、不可达或空结果进入 `accept` 后，只读取生成计数和有界样本所需字段，随后在本次调用内释放；
3. 成功结果在 Publisher 确认接收入队前保持单一所有权；若队列暂满，`accept` 等待有界容量，不复制
   payload，也不额外写入 Run 级容器；
4. Publisher 成功接收入队后成为 payload 唯一所有者，Executor、Scheduler 和 Sink 必须清除引用；
5. 入队同步失败时，由 Sink 记录发布最终失败并立即释放；入队成功后，由 Publisher 在 PubAck、有限重试
   最终失败或发布状态未知终态释放；
6. 任意路径都不得同时由 Scheduler、Executor、Sink 和 Publisher 中两个以上 Module 长期持有同一
   payload。

这里的“立即释放”指删除业务代码中的强引用，使对象具备被 Python 回收的条件；不承诺操作系统 RSS 在
同一时刻等量下降。RSS 是否回落和 allocator 高水位由第 13、14 节的连续压测与 heap profile 验证。

### 5.3 固定大小状态

每个 Run 只保留：

- total、success、failure、empty、unreachable、skipped 等计数；
- publish succeeded/failed/unknown 等计数；
- 最多 8 类错误计数，其他归并为 `other`；
- 最多 3 条采集失败样本和 3 条发布失败样本；
- 有界在途发布数量；
- Run 排空信号。

不得保留：

- 与目标总数等长的结果数组、状态字典或回执列表；
- 每个目标一个长期存活的 waiter Task；
- 已发布完成目标的 StructuredMetricsPayload；
- 原始 PySNMP varBind/OID 对象。

### 5.4 发布语义

结果流式释放不等于逐目标向 NATS publish：

- 成功非空结果仍转交现有 `BufferedResultPublisher`；
- 继续使用最多 50 targets/20ms 微批、编码切块和 PubAck；
- Publisher 的队列、活动微批和确认窗口继续有界；
- Sink 不再复制或二次保存 Publisher 已拥有的结果；
- `finish` 必须等所有成功结果取得确定发布终态，不能提前发送 round-complete。

### 5.5 完成屏障

Run 完成只能由两个单调计数条件共同决定：

```text
targets_terminal == total_targets
and pending_deliveries == 0
```

- `targets_terminal` 在每个目标形成唯一采集终态后加一；
- `pending_deliveries` 只在成功 payload 被 Publisher 接收时加一，在 PubAck、最终失败或发布状态未知时
  减一；
- 两个计数更新必须对 cancel、timeout、重复 callback 和晚到结果保持幂等；
- 不得重新引入逐目标结果列表、逐目标发布状态字典或逐目标 waiter Task 来判断 Run 是否完成；
- 条件满足后只能完成一次，生成一个 RunSummary；
- round-complete marker 继续使用既有业务条件，发布失败或状态未知时不得误报完整轮次。

### 5.6 测试 Seam

生产使用现有 Publisher Adapter；测试使用内存 Publisher Adapter。测试通过 `RunResultSink` Interface
断言最终汇总、唯一所有权、完成屏障和对象生命周期，不依赖其内部容器结构。

## 6. 深模块二：SnmpExecutionRuntime

### 6.1 Interface

建议接口：

```python
class SnmpExecutionRuntime:
    async def execute(self, request: SnmpExecutionRequest) -> SnmpExecutionResult: ...
    async def close(self, *, grace_seconds: float) -> None: ...
```

`SnmpExecutionRequest` 只包含协议执行必需字段；凭据只能存在于内存 IPC，不得进入日志、指标或异常正文。
`SnmpExecutionResult` 只包含归一化、可序列化的成功数据或稳定错误码，不得携带 PySNMP 对象。

提供两个 Adapter：

- `InProcessSnmpRuntime`：保持旧路径，用于对照、灰度回滚和兼容性测试；
- `ProcessSnmpRuntime`：推荐生产路径，负责子进程、IPC、Engine generation 和故障恢复。

这两个 Adapter 共享同一 Interface，使调用方不感知执行位置，也避免在 CredentialAttempt、Executor 和
插件入口散落进程判断。

### 6.2 子进程模型

- 子进程在 CollectionApplication 运行期创建，禁止在模块导入或服务器 fork 前创建；
- 使用 fresh-process/`spawn` 语义，不继承父进程 event loop、NATS、Redis 或 socket；
- 父进程仍拥有 Scheduler、RunLease、凭据顺序、Redis 冷冻/亲和、NATS 和 RunSummary；
- 子进程只执行 SNMP 协议、ASN.1/PDU 处理和结果归一化；
- 全部子进程共享父调度器的 160 总上限，不允许每个子进程各自获得 160；
- IPC 在途请求、响应字节和等待队列必须有界；上界从全局 160 和现有结果大小限制派生；
- timeout/cancel 必须传播；晚到响应通过 request id、generation 和 fence 丢弃；
- 子进程异常退出时，当前 generation 的在途请求返回稳定错误，并按有界退避重建；
- shutdown 先停止接收，再等待有界 grace，最后回收，不得无限等待或遗留僵尸进程。

### 6.3 子进程数量

本方案不预先写死进程数。生产等价压测比较 `1/2/3` 个 SNMP 子进程：

- 1 个：资源最少，但可能只利用一个 CPU 核；
- 2 个：推荐的首个候选，兼顾父进程调度和 SNMP CPU 并行；
- 3 个：吞吐候选，但必须证明不会造成 cgroup throttling、IPC 拷贝或 RSS 放大。

最终默认值由同一组 160 并发压测决定。无论子进程数是多少，全局活动目标都不得超过 160。

### 6.4 Engine 生命周期

每个 SNMP 子进程拥有一个长生命周期 `SnmpEngine`：

- 跨目标和凭据尝试复用；
- 单目标完成、timeout 或 cancel 不关闭共享 dispatcher；
- Engine 只在子进程退出、generation 重建或明确不可恢复故障时关闭；
- 请求状态以 request id、target、credential attempt 和 generation 隔离；
- 一个请求取消不能影响其他目标；
- 如果当前 PySNMP 版本证明单 Engine 不能覆盖某类安全模型，只允许按明确兼容键维护固定、有界的
  小型 Engine 集合，不得退回按目标创建 Engine。

## 7. SNMP 协议降本

### 7.1 合并 probe 与 collect

SNMP 使用可选 capability 实现合并执行，非 SNMP 插件保持现有通用契约。不得在通用 Executor 中按
插件名堆叠分支。

```text
credential A
  -> system GET：同时承担访问探测和正式数据首包
  +-- 认证明确失败：冷冻 A，按策略尝试 B
  +-- no response：不冷冻；按现有凭据顺序决定是否继续
  +-- protocol error：记录稳定协议错误
  +-- success：保留 system 数据，继续 interface WALK，不重复 GET
```

必须保证：

- 每个凭据尝试最多执行一次相同 system GET；
- 一个目标最终只产生一个 `TargetCollectionResult`；
- 成功凭据亲和和明确认证失败冷冻不变；
- 无响应不得转化为明确认证失败。

### 7.2 GETBULK 与 fallback

SNMP v2c/v3 的 interface table 默认使用 GETBULK，SNMP v1 继续使用 GETNEXT。

安全限制：

- OID 必须单调前进且位于目标 subtree；
- 保留最大行数、最大 PDU 数、最大响应字节和总 deadline；
- `tooBig` 先降低 `maxRepetitions`，仍失败再对当前目标回退 GETNEXT；
- 不支持 GETBULK、非递增 OID、异常游标或畸形 varBind 只影响当前目标；
- fallback 使用低基数指标和 DEBUG 原因，不逐 varBind 打日志；
- cancel、timeout 和 Engine 重建必须释放当前请求状态，但不得关闭共享 Engine。

`maxRepetitions` 初始值由兼容性测试锁定，不以最大吞吐值直接上线。

## 8. 160 并发的最终语义与上线门禁

### 8.1 最终语义

```text
当前运行时实例 active_targets <= 160
配置采集独占且持续积压时，SNMP active_targets 可以达到 160
存在其他 workload 时，继续使用现有公平调度和空闲借用语义
```

实现上不删除所有 capacity group。只让 `snmp` 不再拥有低于全局上限的 `100` 硬限制；其他技术资源
限制和非 SNMP 执行类型保持不变。

### 8.2 上线顺序

不得先改 SNMP 100：

1. 先完成结果流式释放；
2. 再完成 SNMP 子进程隔离、Engine 复用和协议降本；
3. 在 SNMP=100 下证明父事件循环和内存达标；
4. 将 SNMP 技术上限提升到 160；
5. 执行完整 160 并发生产等价压测；
6. 只有第 5 步通过，才允许把 SNMP=160 作为生产默认值。

这里的阶段性 100 只是迁移门禁，不改变最终 160 决策。

## 9. 失败分类修正

保持凭据逐个尝试，但最终 RunSummary 使用真实终态原因：

| 场景 | 建议终态错误码 | 是否冷冻凭据 |
| --- | --- | --- |
| 所有候选均明确认证失败 | `credentials_exhausted` | 是，仅冷冻明确失败凭据 |
| 未收到任何 SNMP 响应 | `snmp_no_response` | 否 |
| 收到协议错误或畸形响应 | `snmp_protocol_error` | 否，除非是明确认证错误 |
| 整体 collection deadline 到期 | `plugin_timeout` | 否 |
| GETBULK 不兼容且 GETNEXT fallback 成功 | 成功，记录 fallback 指标 | 否 |
| GETBULK 与 GETNEXT 均失败 | 按最终真实协议原因 | 按明确认证证据决定 |

不得把 `snmp_no_response` 直接命名为 `unreachable`。跨轮次可达性退避不在本方案范围内。

## 10. 可观测性

新增或修正以下低基数指标：

- `run_result_sink_resident_results`、`run_result_sink_pending_deliveries`；
- `snmp_runtime_active_requests`、`snmp_runtime_ipc_backlog`；
- `snmp_child_processes`、`snmp_child_restart_total`、`snmp_engine_generation_total`；
- `snmp_get_total`、`snmp_getbulk_pdu_total`、`snmp_getnext_pdu_total`；
- `snmp_bulk_fallback_total{reason}`；
- `snmp_terminal_total{reason}`，reason 使用固定枚举；
- 父进程和 SNMP 子进程分别记录 CPU、RSS、FD；
- cgroup CPU quota、throttling 和内存上限必须可读取，否则压测报告标记为证据不完整。

日志只记录生命周期、终态汇总和有界失败样本；不得记录 community、凭据、原始 varBind、设备响应
正文或 IPC payload。

## 11. 实施阶段

### 阶段 A：建立可变红基线

1. 5000 目标大 payload Run，证明 RSS/驻留结果随累计完成目标增长；
2. 160 SNMP no-response 场景，记录父 event-loop lag、CPU、timeout callback 波峰；
3. 记录每目标 Engine 创建数、system GET 次数和 WALK PDU 数；
4. 固化成功、空结果、无响应、认证失败、多凭据和 NATS 微批契约。

### 阶段 B：结果流式释放

1. 新增 `RunResultSink` Interface 和内存 Publisher Adapter 测试；
2. 先验证失败/不可达/空结果在 `accept` 后不再被 Run 持有；
3. 验证成功 payload 入队后只由 Publisher 持有，并在 PubAck、最终失败或状态未知后释放；
4. 验证 Publisher 未排空时 `finish` 保持等待，排空后只生成一次 RunSummary；
5. 将 Executor 改为逐目标 `accept`；
6. 删除 Scheduler/Executor 的整轮结果、状态和回执保留；
7. 保持 RunSummary、发布终态和 round-complete；
8. 使用同一 5000 目标测试证明 RSS 不再随累计完成数线性增长。

### 阶段 C：SNMP 执行隔离

1. 新增 `SnmpExecutionRuntime` Interface；
2. 先接入 `InProcessSnmpRuntime`，证明结果契约不变；
3. 实现 `ProcessSnmpRuntime` 的 spawn、IPC、cancel、timeout、crash/restart 和 shutdown；
4. 将 ASN.1/PDU、WALK 和结果归一化迁入子进程；
5. 验证父事件循环不再受 SNMP CPU/callback 阻塞。

### 阶段 D：Engine 与协议降本

1. Engine 生命周期提升到 child generation；
2. 合并 probe/collect system GET；
3. 实现 GETBULK、降档和 GETNEXT fallback；
4. 修正 no-response/credential 错误分类；
5. 用同一设备夹具对比 Engine 创建数、PDU 数、CPU time 和目标时延。

### 阶段 E：解除 SNMP=100 并验证 160

1. 保持全局硬上限 160；
2. 将 SNMP 技术容量提升到 160；
3. 比较 1/2/3 个 SNMP 子进程；
4. 选择满足验收标准且资源最小的进程数；
5. 保存原始压测报告、火焰图、资源曲线和错误分类统计后再进入生产。

## 12. 计划代码影响范围

| Module/文件 | 计划变更 |
| --- | --- |
| `core/collection/scheduler.py` | handler 不再返回整轮结果数组；保留公平调度和全局 160 |
| `core/collection/executor.py` | 逐目标转交 Sink，删除整轮结果/状态/回执容器 |
| `core/collection/result_delivery.py` | 收敛进 `RunResultSink` 或作为其内部实现，发布终态后释放对象 |
| `core/collection/contracts.py` | 增加固定大小终结结果和 SNMP 执行请求/响应契约 |
| `core/collection/application.py` | 装配 Sink 工厂和 SnmpExecutionRuntime 生命周期；不修改 Worker 启动 |
| `core/collection/credential_attempt.py` | 通过 capability 使用合并 SNMP 执行，保留通用多凭据状态机 |
| 新增 `core/collection/run_result_sink.py` | 结果所有权、发布排空、固定大小汇总 |
| 新增 `core/collection/snmp_execution_runtime.py` | Interface、进程 Adapter、IPC、generation、取消与回收 |
| `plugins/inputs/network/snmp_facts.py` | 共享 Engine、合并 GET、GETBULK/fallback、稳定错误分类 |
| `core/collection/application.py` 的容量装配 | SNMP 技术上限在门禁通过后由 100 提升到 160 |
| capacity/metrics 相关 Module | 父/子资源、IPC、Engine、PDU、对象驻留指标 |
| 相关测试与 benchmark | 内存、进程生命周期、协议、多凭据、160 并发和 NATS 回归 |

明确不修改 `server/apps/cmdb/**`、monitor/Host Remote、`server.py`、Supervisor Worker 配置和 NATS
Server/handler 架构。

## 13. 压测矩阵

固定条件：

- 当前运行时全局 `MAX_ACTIVE_TARGETS=160`、`TARGET_TASK_WINDOW=160`；
- 使用生产同版本 PySNMP；
- 使用真实或等价的网络延迟、丢包和高接口数响应；
- 使用真实 TLS JetStream 或生产等价环境；
- 同时记录父/子 PID 和 cgroup 指标。

场景：

1. 单 Run 1000、2500、5000 目标；
2. 多 Run 合计 5000、10000、20000 目标，验证 backlog 不生成等量 Task/结果对象；
3. 160 个全 no-response 目标，制造 timeout callback 波峰；
4. 30% 成功/70% 无响应；
5. 160 个全成功小结果；
6. 160 个高接口数大结果；
7. 多凭据：A 认证失败/B 成功、A 无响应/B 成功、首凭据成功；
8. GETBULK：正常、tooBig 降档、不支持、异常游标和 GETNEXT fallback；
9. 子进程：1/2/3 个，对比吞吐、父 loop lag、RSS、IPC backlog 和 throttling；
10. 故障注入：child crash、Engine 重建、cancel、晚到响应、PubAck 变慢和 NATS 短暂断连；
11. 连续三轮相同负载，观察 RSS 平台和资源回收。

## 14. 验收标准

### 14.1 并发与任务

- 全局 `active_targets <= 160`；
- 配置采集独占且积压时，SNMP active targets 可以达到 160；
- pending 目标不创建等量 asyncio Task、Future 或结果槽；
- 同 task ID 重入、RunLease 和单目标单终态保持不变。

### 14.2 主事件循环与 CPU

- 160 SNMP 压力下，Sanic 父 event-loop lag P99 `<1s`；
- 子进程的 CPU 峰值或内部延迟不得阻塞父进程 timeout、HTTP、NATS PING/PONG 和 PubAck；
- 无无界进程、线程、FD、socket、IPC 请求或僵尸子进程；
- 进程数选择必须同时给出 cgroup quota 与 throttling，指标缺失时不得签字。

### 14.3 内存

- Scheduler/Executor 不存在与目标总数等长的结果、状态和回执容器；
- 驻留完整结果数量受 160、Publisher 队列、活动微批和 PubAck 窗口约束；
- 5000 目标大结果测试中，RSS 不随累计完成目标数单调线性增长；
- 连续三轮相同负载后 RSS 进入稳定平台，不出现逐轮持续增长；
- heap profile 能说明主要对象类型和 retained path，不能只以 RSS 单点作为结论。

### 14.4 SNMP 协议

- Engine 创建数与子进程 generation 数相关，不与目标数线性增长；
- probe/collect 合并后，每个凭据尝试不重复 system GET；
- 标准 interface fixture 中 GETBULK 的 PDU/callback 数显著低于 GETNEXT 基线；
- fallback 不影响其他目标，也不关闭共享 Engine；
- `snmp_no_response`、认证失败、协议错误和 plugin timeout 分类正确。

### 14.5 NATS 与业务契约

- 失败、无响应、空结果、凭据事件和 RunSummary 的 metrics NATS 消息数仍为 0；
- 成功非空结果继续使用现有微批，不退化为逐目标 publish/flush；
- RunSummary、round-complete、稳定 Msg-Id 和 PubAck 终态不变；
- 正常网络下发布失败为 0，故障恢复后 Publisher 可有界排空。

## 15. 风险与控制

| 风险 | 控制 |
| --- | --- |
| IPC 序列化复制大结果，造成新的 CPU/RSS | 子进程先归一化；结果只转交一次；限制在途响应；压测大接口结果 |
| 共享 Engine 出现请求串扰 | request id + generation；并发、取消、v2c/v3 混合测试 |
| 子进程崩溃导致目标悬挂 | 有界 deadline、稳定错误终结、generation fence、受监督重启 |
| GETBULK 与旧设备不兼容 | 降低 repetitions、按目标 GETNEXT fallback、兼容性指标 |
| 流式释放改变 round-complete | `RunResultSink.finish()` 统一等待目标与发布终态 |
| 解除 SNMP=100 后压力反弹 | 只有前四阶段通过后提升到 160，并以 P99/RSS 门禁决定上线 |
| 错误分类影响既有汇总 | 保留总失败数和原返回契约，新增稳定终态原因回归测试 |

## 16. 回滚

每阶段独立提交并可单独回滚：

1. `RunResultSink` 流式终结；
2. `SnmpExecutionRuntime` Interface 与 in-process Adapter；
3. process Adapter；
4. Engine 复用；
5. probe/collect 合并；
6. GETBULK/fallback；
7. SNMP 技术容量 100 -> 160；
8. 错误分类修正。

process Adapter 可回滚到 in-process Adapter；SNMP 160 可独立回滚到 100，但全局产品上限仍保持 160。
任何回滚不得恢复失败/credential metrics NATS，也不得修改本方案排除的监控、Worker 和触发链路。

## 17. 待决策清单

请按以下清单决策；建议全部批准：

- [ ] C1：批准第 5 节流式结果生命周期、Publisher 唯一所有权、双条件完成屏障，并删除跨整轮完整
  结果保留；
- [ ] C2：批准 `SnmpExecutionRuntime` 子进程隔离方案；
- [ ] C3：批准每个子进程复用长生命周期 Engine；
- [ ] C4：批准合并 SNMP probe/collect 的 system GET；
- [ ] C5：批准 v2c/v3 GETBULK，并保留有界 GETNEXT fallback；
- [ ] C6：批准最终 SNMP 技术容量提升到 160，且必须经过阶段性门禁；
- [ ] C7：批准修正 no-response/credential 终态分类；
- [ ] C8：批准子进程数量不预先写死，由 1/2/3 生产等价压测选择；
- [ ] C9：确认不在本轮引入跨轮次不可达退避；
- [ ] C10：确认本方案第 2.2、2.3 节的排除和暂缓范围。

确认后按第 11 节实施；任一决策未批准时，先修订本文，不进入代码阶段。
