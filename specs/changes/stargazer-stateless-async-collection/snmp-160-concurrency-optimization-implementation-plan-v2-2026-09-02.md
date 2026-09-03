# Stargazer SNMP 160 并发与结果生命周期优化实施方案 V2

Status: implemented locally；代码、并发测试与本地压测已完成，待生产灰度（2026-09-02）

Baseline: 社区版 MR [#5115](https://github.com/TencentBlueKing/bk-lite/pull/5115)，
commit `1a6068ddfa3c7c2ced6d954a025d37c438560bf9`，已合入 `upstream/master@a3011d472`。

## 1. 结论摘要

本方案根据 MR #5115 的根因和 A/B 数据修订原方案：

1. MR 已完整实现进程内 `SnmpEngine` 复用，并证明每目标 Engine/MIB/PLY 被 uvloop 地址 LRU 持有是
   生产事件循环延迟和大部分 RSS 不回落的主要根因；本轮直接吸收 MR，不重复实现 Engine 池；
2. 本方案明确放弃 SNMP 子进程路线，直接采用并加固 MR 的进程内 `SnmpEngine` 复用；不新增 IPC、
   子进程池、进程代际或跨进程 payload 序列化；
3. MR 的 Engine 池必须先补齐进程级 Engine/Scope 总量上界、LCD 目标条目总预算、有限配置校验和
   160 并发仓内回归，不能原样将 SNMP 从 100 提升到 160；
4. `RunResultSink` 流式生命周期继续实施，因为跨整轮保留完整结果是已确认的架构缺陷；但不再声称它是
   本次 5.1 GiB 的主要来源，具体占比在 MR 基线合入后重新量化；
5. probe/collect 合并、配置采集 GETBULK、真实失败分类和 SNMP 100→160 仍未被 MR 覆盖，继续保留；
6. 全局目标并发最终口径保持 `160`；失败、空结果、凭据事件和 RunSummary 仍不进入 metrics NATS。

## 2. 已锁定范围

### 2.1 必须保持

- 当前运行时实例全局 `active_targets <= 160`；
- 配置采集独占且积压时，SNMP 最终可以使用 160 个目标槽；
- 现有 workload 公平调度、RunLease、重入保护和单目标单终态不变；
- 现有 Metrics 微批、PubAck、稳定 Msg-Id、有限重试和 round-complete 语义不变；
- 多凭据顺序、明确认证失败冷冻、成功亲和及无响应不冷冻凭据不变；
- 只有成功且非空的正常指标进入 metrics NATS/JetStream。

### 2.2 明确排除

- CMDB 周期任务及 Telegraf 触发机制；
- 主机监控、monitor HTTP、Host Remote callback 和监控并发；
- Sanic Worker 数量、多 Worker 配置和生产镜像代际；
- NATS Server、Stream、ACL、queue group 和底层依赖；
- 配置文件采集 callback/control RPC；
- `MAX_ACTIVE_RUNS=16` 的成本化准入；
- 跨轮次不可达退避；
- 企业版监控插件。

企业版最新 `origin/main@06a6599` 未发现本次配置采集主链的另一套 `SnmpEngine` 实现；本轮代码变化仍在
社区版公共 Stargazer。

## 3. 修订后的问题判断

### 3.1 已被 MR 证明并解决的主要根因

MR 给出的实测引用链：

```text
每目标 SnmpEngine
  -> 每 Engine 独立 MibBuilder
  -> 每 Engine 新建 MibCompiler
  -> PLY 重算 SMI LR 表
  -> UdpTransportAddress._localAddress
  -> uvloop sockaddr LRU 保留地址键
  -> 已 closeDispatcher 的 Engine/MIB 树仍然可达
```

MR 在 1 Worker、SNMP 100 并发、2×400 个无响应目标下的 A/B：

| 指标 | 修复前 | MR 修复后 |
| --- | ---: | ---: |
| 800 目标后 RSS | 1747 MiB | 115 MiB |
| 空闲 60 秒 RSS | 1784 MiB | 115 MiB |
| Event Loop P99 最大值 | 7304 ms | 25.2 ms |
| 存活 PLY LRParser | 800 | 1 |
| CPU max | 99.7% | 18.0% |

因此原方案“必须先用子进程隔离才能解决 10～15 秒延迟”的判断不再成立。进程内共享 Engine 已直接消除
主要 CPU 和引用保留根因，本方案不再保留子进程设计。

### 3.2 MR 仍存在的资源边界缺口

MR 按凭据作用域保存活跃 Engine：v1/v2c 共用一个，v3 按安全材料摘要各一个。当前只有单 Engine 的
目标数和空闲时间限制，没有进程级 Engine/Scope 总量上限：高基数 v3 凭据可能在空闲窗口内累积多个
Engine、LCD 和 TimerHandle；永久 `_scope_labels` 也随历史 scope 增长。

另外，`SNMP_ENGINE_IDLE_SECONDS=inf` 可通过“正数”校验，形成永不回收配置；MR 仓内真实测试只覆盖
8 个并发超时和 32 个并发取消，没有锁定 160 并发 RSS/P99。

### 3.3 仍然成立但需要重新量化的结果生命周期缺陷

当前仍存在：

```text
CollectionScheduler._RunState.results
  -> PendingPublish.result
    -> TargetCollectionResult
      -> StructuredMetricsPayload
```

MR 没有修改 Scheduler、Executor、ResultDelivery 或 Publisher。大量成功设备及高接口数 payload 仍可能
在多个未结束 Run 中跨整轮保留。

新的结论是：

- “跨整轮保留完整结果”是确定的架构缺陷；
- “它贡献了 5.1 GiB 中的多少”尚未证明；
- 必须在 MR 基线下用成功大 payload 和 heap retained-path 重新测量；
- 无论占比如何，最终实现仍按第 7 节改为流式所有权。

## 4. V2 架构决策

| 编号 | 决策 |
| --- | --- |
| D1 | 以社区版 MR #5115 为 Engine 修复基线，不再自行实现另一套 Engine 池 |
| D2 | Engine 池保留进程内执行；先补齐进程级资源预算和 160 门禁 |
| D3 | 明确放弃子进程和 IPC 路线；事件循环治理统一收敛在进程内 EnginePool、协议降本和结果生命周期 |
| D4 | 保留 `RunResultSink` 流式结果生命周期；成功 payload 只由发布子系统长期持有 |
| D5 | 保留 probe/collect system GET 合并 |
| D6 | 配置采集 v2c/v3 interface WALK 改 GETBULK，保留有界 GETNEXT fallback |
| D7 | 修正 `snmp_no_response`、认证失败、协议错误和 plugin timeout 分类 |
| D8 | 最终解除 SNMP=100 的第二层硬限制，配置采集独占时可使用全局 160 |
| D9 | NATS、监控、Telegraf、Worker 和企业版插件不属于本轮修改 |

## 5. 默认目标架构

```text
CollectionRuntime
  |
  | active_targets <= 160
  v
CollectionScheduler
  | handler 不返回整轮结果数组
  v
TargetCollectionExecutor
  |
  +-- SNMP probe/collect capability
  |      |
  |      v
  |   MR SnmpEnginePool（进程内）
  |      +-- v1/v2c community scope
  |      +-- v3 安全材料 scope
  |      +-- 进程唯一 MIB compiler
  |      +-- Engine/Scope 总量预算
  |      +-- 全局 LCD 目标条目预算
  |      +-- 代际轮换 / 空闲回收 / shutdown
  |      +-- 合并 system GET
  |      +-- GETBULK / GETNEXT fallback
  |
  v
RunResultSink.accept(result)
  +-- 失败/空结果：固定计数与最多 3 条样本 -> 立即释放
  +-- 成功非空：发布子系统（DeliveryCoordinator + Publisher）成为 payload 唯一长期所有者
                         -> PubAck/最终终态后立即释放
  v
RunResultSink.finish()
  +-- targets_terminal == total_targets
  +-- pending_deliveries == 0
  +-- RunSummary / 必要时 round-complete
```

目标架构明确不包含子进程：统一使用已验证的进程内 Engine 复用解决真实根因，不引入凭据 IPC、进程
generation、崩溃恢复和大 payload 跨进程序列化。若 160 门禁不达标，继续在本架构内定位和优化，或将
SNMP 技术并发回退到 100；不切换到子进程实现。

## 6. SnmpEnginePool 加固

MR 的 `shared_snmp_engine(auth, target=...)` Interface 保持不变；资源预算、凭据 scope、MIB compiler、
轮换和关闭复杂度隐藏在池 Module 内部。

### 6.1 全局资源不变量

实施后必须满足：

```text
live_engines = active_engines + draining_engines
live_engines <= MAX_ACTIVE_TARGETS  # 当前为 160

sum(distinct_targets of live engines)
  <= SNMP_ENGINE_TOTAL_TARGET_BUDGET  # 初始默认 4000
```

预算策略：

1. 创建新 Engine 前，先关闭最近最少使用且 `in_flight == 0` 的 holder；
2. 目标条目总预算不足时，同样优先回收空闲 holder；
3. 若全部 holder 都有在途请求，则 acquisition 等待容量条件，不继续无界创建；
4. 任何等待受目标 collection deadline 和 cancel 控制；
5. 旧代 Engine 排空关闭后唤醒等待者；
6. 不因资源饱和冷冻凭据，也不把容量等待误报为认证失败。

`4000` 的初始目标条目预算来自 MR 报告的约 `21 KiB/目标`：理论 LCD 约 84 MiB，再通过真实 v2c/v3
组合压测校正。若修改默认值，必须同时给出目标条目内存实测，不能只提高阈值。

### 6.2 凭据 scope 与日志

- v1/v2c 继续共用 community Engine；
- v3 继续按用户名、安全级别、协议和密钥材料摘要隔离；
- 摘要只存在于内存字典键，不进入日志和指标；
- 删除永久增长的 `_scope_labels` 映射；日志 scope 只使用低基数 `community|v3`，generation 单独记录；
- 不记录 community、用户名、密钥、摘要、原始 auth 对象或响应正文。

### 6.3 有限配置

| 配置 | 默认值 | 合法范围 | 说明 |
| --- | ---: | ---: | --- |
| `SNMP_ENGINE_MAX_TARGETS` | 2000 | `1..2000` | 单 Engine LCD 目标数，超过即代际轮换 |
| `SNMP_ENGINE_IDLE_SECONDS` | 300 | `(0, 3600]` 且 finite | 空闲回收时间 |
| `SNMP_ENGINE_TOTAL_TARGET_BUDGET` | 4000 | `160..10000` | 全部 live holder 的目标条目预算 |

Engine 总数直接从 `MAX_ACTIVE_TARGETS` 派生，不新增第二份可漂移的 Engine 数量配置。非法、NaN、Inf 或
超范围值在启动配置校验时 fail-fast。

### 6.4 行为测试

- 160 个不同 v3 scope 不超过 160 个 live Engine；
- 第 161 个 acquisition 在没有空闲 holder 时有界等待，释放后继续；
- 空闲 v3 holder 按 LRU 回收，不能逐凭据永久增长；
- scope 标签和指标保持低基数；
- total target budget 达限时回收/等待正确；
- cancel、timeout、旧代排空和 shutdown 唤醒等待者且无僵尸 Future；
- `NaN/Inf/0/负数/超上限` 配置全部拒绝；
- 敏感哨兵不出现在模板、参数、格式化日志和异常正文。

## 7. RunResultSink 流式结果生命周期

### 7.1 Interface

```python
class RunResultSink:
    async def accept(self, index: int, result: TargetCollectionResult) -> None: ...
    async def finish(self) -> RunFinalization: ...
```

### 7.2 所有权契约

```text
目标完成
  +-- 失败 / 不可达 / 空结果
  |    -> 更新固定计数、错误类型和最多 3 条样本
  |    -> 立即释放 TargetCollectionResult
  |
  +-- 成功且非空
       -> 等待有界 Metrics 队列接收
       -> 发布子系统（DeliveryCoordinator + Publisher）成为 payload 唯一长期所有者
       -> Scheduler / Executor / Sink 清除引用
       -> PubAck / 最终失败 / 发布状态未知
       -> 更新发布终态计数
       -> 立即释放 payload、receipt 和临时编码对象

targets_terminal == total_targets
and pending_deliveries == 0
  -> 只生成一次 RunSummary
  -> 写终态汇总日志
  -> 满足既有条件时发布 round-complete
```

Run 只保留固定计数、最多 8 类错误、最多 3 条采集失败样本、最多 3 条发布失败样本和排空信号；不得
保留目标数等长的结果数组、状态字典、receipt 列表或 waiter Task。

“立即释放”指删除业务强引用，不承诺操作系统 RSS 同步下降；通过对象驻留统计、heap retained-path 和
连续三轮 RSS 平台验证。

### 7.3 测试 Seam

生产使用现有 Publisher Adapter，测试使用内存 Publisher Adapter。测试只通过 `RunResultSink` Interface
断言唯一所有权、终态计数、排空屏障和 round-complete，不锁定内部容器实现。

## 8. SNMP 协议降本与失败语义

### 8.1 合并 probe/collect

SNMP 通过可选 capability 合并执行，非 SNMP 插件保持现有契约：

```text
credential A
  -> 一次 system GET，同时承担 access probe 和正式数据首包
  +-- 认证明确失败：冷冻 A，按策略尝试 B
  +-- no response：不冷冻，按既有策略决定是否继续 B
  +-- success：保留 system 结果，直接进入 interface WALK
```

同一凭据尝试不得重复 system GET；成功亲和、凭据顺序和单目标单终态不变。

### 8.2 配置采集 GETBULK

- v2c/v3 interface table 默认 GETBULK；v1 继续 GETNEXT；
- `tooBig` 先降低 repetitions，再按当前目标回退 GETNEXT；
- 非递增 OID、异常游标、越出 subtree 和畸形 varBind 有界终止；
- 保留最大行数、PDU 数、响应字节和总 deadline；
- fallback 不关闭共享 Engine，不影响其他目标；
- 不逐 varBind 打日志。

MR 已有的网络拓扑 bulk 不等于配置采集 `snmp_facts` 的 GETBULK，本项仍需单独实施。

### 8.3 失败分类

| 场景 | 最终错误码 | 冷冻凭据 |
| --- | --- | --- |
| 所有候选均明确认证失败 | `credentials_exhausted` | 仅明确失败凭据 |
| 未收到 SNMP 响应 | `snmp_no_response` | 否 |
| 协议错误或畸形响应 | `snmp_protocol_error` | 否，除非有明确认证证据 |
| collection deadline 到期 | `plugin_timeout` | 否 |
| GETBULK 回退 GETNEXT 后成功 | 成功 + fallback 指标 | 否 |

`snmp_no_response` 不等同于 `unreachable`，本轮不引入跨轮次退避。

## 9. 分阶段实施

### 阶段 A：吸收 MR 并加固 Engine 池

1. 以 `1a6068ddf` 为唯一 Engine 池实现来源，不复制相同功能；
2. 先保留 `SNMP_MAX_IN_FLIGHT=100`；
3. 增加第 6 节 Engine/Scope/目标条目预算和有限配置；
4. 用行为测试替代仅检查源码字符串的实现细节测试；
5. 保留 MR 的 Engine 并发、v3 隔离、MIB compiler、轮换、取消和敏感日志测试。

### 阶段 B：MR 基线 160 生产等价门禁

测试时显式覆盖 SNMP 技术上限为 160，但暂不修改生产默认值：

1. 160 个全 no-response 目标；
2. 30% 成功/70% no-response；
3. 160 个全成功小结果；
4. 160 个全成功高接口数结果；
5. 多 Run 合计 5000/10000/20000 目标；
6. 160 个不同 v3 scope；
7. Engine 代际轮换、空闲回收和目标总预算压力；
8. 连续三轮相同负载；
9. 真实 TLS JetStream 正常和 PubAck 变慢场景。

门禁：

- Sanic event-loop lag P99 `<1s`；
- `active_targets <=160`；
- no-response 连续三轮 RSS 不单调增长，Engine/LRParser/目标条目受预算约束；
- 成功大 payload 的驻留链和 RSS 曲线有 heap profile；
- NATS PING/PONG、PubAck 和 HTTP 在压力下及时；
- 无无界 Task、Future、Engine、Scope、TimerHandle、FD 或 socket；
- cgroup quota/throttling 缺失时不得签字。

### 阶段 C：RunResultSink

1. 建立 5000 目标大 payload 红灯，证明当前整轮结果保留；
2. 实现第 7 节 Interface 和流式所有权；
3. 删除 Scheduler/Executor 整轮结果、状态和回执容器；
4. 保持 RunSummary、PubAck 和 round-complete；
5. 证明驻留 payload 数由 160、Publisher 队列、微批和 PubAck 窗口约束。

### 阶段 D：协议降本和错误分类

1. 合并 probe/collect system GET；
2. 配置采集 GETBULK + GETNEXT fallback；
3. 修正 no-response/credential/protocol/timeout 分类；
4. 对比 system GET 次数、PDU 数、CPU time、目标时延和失败分布。

### 阶段 E：生产默认 SNMP 100→160

只有 A～D 全部通过后：

1. 让 SNMP 技术容量使用全局 scheduler limit，不再保留低于 160 的第二层默认值；
2. 保持其他 capacity group 不变；
3. 用同一矩阵重新执行默认配置压测；
4. 灰度观察 RSS、P99、Engine 预算、丢包率、PubAck 和任务吞吐；
5. 达标后确认生产默认 160。

## 10. 默认代码影响范围

| Module/文件 | 计划变更 |
| --- | --- |
| MR #5115 的 12 个文件 | 作为基线吸收，不重复实现 |
| `core/infra/snmp_engine_pool.py` | Engine/Scope/目标条目总预算、有限配置、低基数 scope、等待/唤醒 |
| `core/collection/scheduler.py` | handler 不再返回整轮结果数组；公平调度和全局 160 不变 |
| `core/collection/executor.py` | 逐目标转交 Sink，删除整轮结果/状态/回执保留 |
| `core/collection/result_delivery.py` | 收敛为 Sink 内部实现或有界发布 Adapter |
| 新增 `core/collection/run_result_sink.py` | 唯一所有权、固定汇总和完成屏障 |
| `core/collection/contracts.py` | 增加 Run finalization 与 SNMP 合并 capability 契约 |
| `core/collection/credential_attempt.py` | 使用可选合并 capability，通用状态机不写 SNMP 特例 |
| `plugins/inputs/network/snmp_facts.py` | 合并 system GET、GETBULK/fallback、错误分类 |
| `core/collection/application.py` | Engine 预算装配；最终让 SNMP 使用全局 160 |
| capacity/metrics 与 benchmark | Engine、target budget、结果驻留和 160 门禁 |

本方案不新增 `snmp_execution_runtime.py` 或任何 SNMP 子进程/IPC Module，不修改 `server/apps/cmdb/**`、
monitor/Host Remote、Worker 启动、企业版插件和 NATS 架构。

## 11. 验收标准

### 11.1 Engine 与事件循环

- Engine/LRParser 数不随目标数线性增长；
- live Engine、scope、LCD 目标条目和 TimerHandle 均有硬上界；
- 160 压力下 event-loop lag P99 `<1s`；
- cancel、timeout、轮换和 shutdown 不产生晚到 callback 错误；
- community/v3 敏感材料不进入日志、指标和异常正文。

### 11.2 结果生命周期

- Scheduler/Executor 不存在与目标总数等长的结果、状态和 receipt 容器；
- Scheduler、Executor 和 RunResultSink 不持有成功 payload；只有发布子系统为重试/PubAck 长期持有；
- PubAck/最终终态后 payload 可回收；
- 5000 大 payload 目标驻留量受并发和 Publisher 窗口约束；
- 连续三轮 RSS 进入稳定平台，并保存 heap retained-path。

### 11.3 协议与 160

- probe/collect 每凭据只执行一次 system GET；
- GETBULK PDU/callback 数显著低于 GETNEXT 基线，fallback 契约通过；
- 错误分类不再把 no-response 笼统记为 credentials_exhausted；
- 默认配置下 SNMP 可以达到 160，但全局 active targets 永不超过 160。

### 11.4 NATS 与既有契约

- 失败、空结果、凭据结果和 RunSummary 的 metrics NATS 消息数为 0；
- 成功结果继续使用现有微批和 PubAck；
- 正常网络发布失败为 0，故障恢复后有界排空；
- 重入、RunLease、RunSummary 和 round-complete 语义不变。

## 12. 回滚

独立回滚单元：

1. MR EnginePool 基线；
2. EnginePool 资源预算加固；
3. RunResultSink；
4. probe/collect 合并；
5. GETBULK/fallback；
6. 错误分类；
7. SNMP 100→160。

若 160 灰度失败，先把 SNMP 技术默认值回滚到 100，保留全局产品上限 160、MR EnginePool、流式结果和
协议优化；不得回滚到每目标创建 Engine，也不得恢复失败/credential metrics NATS。

## 13. 已确认决策

- [x] V2-C1：以社区版 MR #5115 为 Engine 修复基线，不重复实现 Engine 复用；
- [x] V2-C2：补齐 Engine/Scope/目标条目预算和有限配置；
- [x] V2-C3：放弃 SNMP 子进程和 IPC 路线，仅实施进程内 EnginePool；
- [x] V2-C4：实施 RunResultSink 流式结果生命周期；
- [x] V2-C5：实施 probe/collect 合并和配置采集 GETBULK；
- [x] V2-C6：实施失败分类修正；
- [x] V2-C7：按用户明确口径保留全局及 SNMP 默认 160，并补本地 160 门禁；
- [x] V2-C8：保持第 2 节排除范围；
- [x] V2-C9：不实施子进程兜底。

## 14. 本次实施结果

### 14.1 已落地

1. 吸收 MR #5115 的进程级共享 `SnmpEngine`、共享 MIB compiler、代际轮换、空闲关闭和 Sanic shutdown；
2. 增加 `live_engines <= 160`、全池目标条目预算、LRU 回收、容量等待、有限配置和低基数标签；Engine
   shutdown 进入关闭态，容量等待者收到稳定异常，不会在停机过程中重新开池；
3. Scheduler 生产路径不再构造整轮结果数组；`RunResultSink` 只保存有界计数和最多 3 条样本；成功 payload
   立即移交发布子系统，由 `BoundedResultDeliveryObserver` 的固定 4 个 worker 和容量 160 队列处理，不再按目标
   创建 waiter Task；
4. 5000 个 32 KiB 成功 payload 的生命周期测试证明：Run 未结束时强引用驻留量不超过 160，发布终态后为 0；
5. SNMP probe 与 collect 复用同一 Service、Executor 和 Collector，成功凭据只发送一次五项 system GET；
6. 接口采集默认 GETBULK；`tooBig` 按 `25→12→6→3→1` 降低 repetitions 后回退 GETNEXT，并增加
   非递增 OID、PDU、行数、响应字节和 60 秒 walk deadline 边界；
7. `snmp_no_response`、`snmp_protocol_error`、明确认证/能力拒绝和 `plugin_timeout` 分开统计；无响应不会再汇总为
   `credentials_exhausted`，普通 SNMP error-status 不再一律冷冻凭据；
8. `SNMP_MAX_IN_FLIGHT` 默认值改为 160，单独的 SNMP=100 硬限制已解除。
9. 健康/容量快照与周期日志新增 `snmp_live_engines`、Engine capacity、draining Engine、LCD 目标条目/预算及
   `result_deliveries_pending`，灰度时可直接判断是否逼近硬上界。

### 14.2 本地并发与压力结果

| 场景 | 结果 |
| --- | --- |
| 真实 PySNMP UDP 无响应，800 目标、160 并发、同进程连续 3 轮 | 全部 800/800 终态；Engine 峰值 1；Task 峰值 164；callback error 0 |
| 上述三轮 Event Loop lag P99 | `26.8 ms / 20.3 ms / 18.3 ms`，均远低于 1 秒门禁 |
| 上述三轮进程 max RSS 增量 | `22.1 MiB / 4.0 MiB / 6.4 MiB`，没有按 800 目标线性增长 |
| 5000 目标调度，`100/30/30` 与 `100/20/20`，连续 3 轮 | 全部通过；峰值 active=160；借用后 configuration=120；lag P99 最大 `0.924 ms` |
| 5000 网络设备×20 行、模拟 5 ms PubAck | 100000/100000 行确认；失败 0；队列峰值 160；lag P99 `33.19 ms`；峰值 RSS `96.69 MiB` |

真实 SNMP 压测使用 PySNMP Engine、UDP socket、timeout callback 和 OID 编解码，不再用未完成 Future 替代
transport。由于本机没有生产 TLS JetStream、cgroup CPU quota 和授权的高接口数真实设备，真实 TLS PubAck、
cgroup throttling、成功高接口数设备及生产 heap retained-path 仍属于灰度验收，不伪装成本地已验证。

### 14.3 回归状态

- 本次直接受影响的 Engine、Scheduler、Sink、Executor、容量观测、插件和协议测试共 200 项通过；
- 仓库 `tests/` 全跑存在与本轮无关的既有失败，包括已删除 legacy `task_queue/plugin_handler/host_remote`
  Module、缺少 MSSQL fixture 和 Windows WMI schema 断言；
- 从仓库根全量收集还会被 `common/.../test_sync.py` 对不存在的 `home_application` 依赖中断。
