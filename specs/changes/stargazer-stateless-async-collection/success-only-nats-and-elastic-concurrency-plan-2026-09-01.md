# Stargazer 成功数据唯一出站与 160 弹性并发实施方案

Status: implemented；待生产等价压测签字（2026-09-01）

## 1. 结论摘要

本方案收敛 Stargazer 的采集结果出站和目标并发模型：

1. Stargazer 只向 metrics NATS/JetStream 发布**正常采集成功且包含有效数据**的结果；
2. 普通采集失败、不可达、超时、空成功结果、凭据成功/失败、全部凭据冷冻和 Run 汇总均不进入
   NATS；
3. 配置采集入口明确为 `agents/stargazer/api/collect.py` 的 `api.collect.collect`，该入口继续接收
   有序 `credentials_pool`；
4. 多凭据的解析、按目标串行轮换、认证失败冷冻、成功即停止以及成功亲和全部保留；
5. credential/result 的即时 Core NATS、定时 NATS 重放、Redis 结果事件流和 HTTP 状态投影全部删除；
6. 凭据亲和/冷冻仅存在于 Stargazer Redis，并通过有界日志观测，不回写 CMDB；
7. 单 Stargazer 进程目标并发硬上限由 `250` 降为 `160`；
8. `configuration`、`monitoring` 和既有 `network_topology` 在竞争时按 `100/30/30`
   分享容量，任一类别独占时可借满 `160`；
9. `monitoring` 以 [`api/monitor.py`](../../../agents/stargazer/api/monitor.py) 入口为准，
   网络拓扑继续复用既有识别，其余入口统一归为 `configuration`；
10. 预期失败只进入有界 DEBUG 诊断和单 Run 终态汇总，不再产生逐目标 ERROR traceback 风暴；
11. metrics 与 control/RPC 继续使用独立 NATS 连接；生产 metrics 为 JetStream-only，不允许回退到
    Core NATS，control 只暴露 request/callback/deferred 明确 Interface；
12. 业务公平、技术资源、成功结果编码和 JetStream 传输分别拥有独立容量，插件内部 fan-out 逐步
    接入共享资源 Module；不新增 credential Stream、Consumer 或底层依赖。

本方案不是把 credential 事件从 Core NATS 迁移到 JetStream。credential NATS 出站链路确定删除；
多凭据当前状态在 Stargazer Redis 内部闭环，不进入 metrics/control NATS，也不通过 HTTP 同步到 CMDB。

## 2. 决策与范围

### 2.1 已锁定决策

| 编号 | 决策 |
| --- | --- |
| D1 | 只有正常成功数据可以进入 metrics NATS/JetStream |
| D2 | 配置采集和监控采集的失败指标全部停止发送 |
| D3 | credential success/failure 不发送 NATS，也不迁移 JetStream |
| D4 | Run 汇总只写 Stargazer 本地日志，不发送 NATS |
| D5 | Stargazer 本地 Redis 凭据冷冻和成功亲和继续保留 |
| D6 | 单进程全局目标并发为 160，竞争份额为 configuration 100、monitoring 30、network_topology 30 |
| D7 | 份额是软配额；没有其他类别排队时，任一类别可借满 160 |
| D8 | 已在途目标不抢占、不取消；新类别通过自然完成逐步取回份额 |
| D9 | monitoring 由 `api/monitor.py` 可信入口注入，其他普通采集默认 configuration |
| D10 | 网络拓扑沿用既有识别，不在本方案重复设计其插件和入口 |
| D11 | configuration 的产品入口是 `api.collect.collect`，`_submit_collection_run()` 只是其内部提交 seam |
| D12 | 多凭据池、稳定顺序、逐目标轮换、成功即停、S1 冷冻和成功亲和属于必须保留的采集能力 |
| D13 | 删除 `api.collect.get_credential_results`、Redis 凭据事件流和所有 CMDB 状态投影同步 |
| D14 | `CollectTaskCredentialHit` 仅保留给暂缓处理的 Server 配置文件直执行链路，本轮不接收 Stargazer 状态 |
| D15 | Stargazer Redis 是普通配置/监控多凭据运行时亲和与冷冻的唯一权威 |
| D16 | 扫描一枪的 `receive_scan_credential_result` 是独立业务协议，继续保留，不写 `CollectTaskCredentialHit` |
| D17 | 生产 metrics 只允许 JetStream；配置未启用时 fail-fast，运行时不可用时 readiness 失败，不回退 Core NATS |
| D18 | control NATS 只暴露 request/callback/deferred 等明确 Interface，不再向业务代码暴露通用批量 publish |
| D19 | 容量拆为业务公平、技术资源、成功结果编码、JetStream 传输四层，每层只拥有一种容量 |
| D20 | metrics 编码使用独立有界执行器和全局字节预算，不与同步 SDK 共用默认线程池 |
| D21 | `capacity_group` 成为真实准入条件；插件内部线程池和 fan-out 分阶段接入共享资源 Module |
| D22 | 空闲槽继续允许借满 160；新 workload 到来后按借槽债务非抢占归还，槽位释放后优先派发 |
| D23 | 增加瞬时 1000/2500/5000 任务突发压测，并分别验证 100/30/30 与 100/20/20 并发形态 |

### 2.2 待确认决策

| 编号 | 决策点 |
| --- | --- |
| C2 | `cmdb_round_complete` 是否仅在存在成功数据且发布已确认时保留；见第 8.4 节 |

### 2.3 保留的协议

以下不属于“失败指标/凭据结果事件”，继续保留：

- 正常成功数据的 metrics JetStream 发布；
- 必要的 control/RPC 请求响应；
- 明确声明 `callback_subject` 的既有业务 callback/deferred 协议；
- Redis RunLease、凭据冷冻/亲和、Deferred callback 上下文；
- 成功快照所需的 round metadata 存储。
- `api.collect.collect` 对单凭据和多凭据入站的兼容；
- `credentials_pool` 的顺序、稳定 `credential_id`、目标匹配和 SNMP v2/v2c/v3 混合凭据语义。

显式 callback 是调用方要求的业务控制协议，不得通过“成功数据唯一出站”规则静默删除；它必须和
普通采集 metrics、credential 事件分别路由和计数。

### 2.4 非目标

- 不新增 credential JetStream Stream、Consumer 或第三条数据连接；
- 不升级或替换 NATS Server、`nats-py`、Redis；
- 不引入 Kafka、Celery 或新的任务队列；
- 不处理主机/网络设备配置文件的双插件触发与 callback execution 问题；该问题独立记录于
  [`config-file-collection-chain-deferred-issues-2026-09-01.md`](config-file-collection-chain-deferred-issues-2026-09-01.md)；
- 不重做网络拓扑已经存在的入口识别和基础调度能力；
- 不用延长 NATS flush timeout 掩盖事件循环延迟；
- 不承诺单靠本方案即可证明所有事件循环延迟都低于 1 秒；
- 不建立跨 Pod 的分布式 160 容量池。本文的 160 是单 Stargazer 进程上限。

## 3. 被替代的旧设计

本方案确认后，以下旧条款在冲突范围内失效：

1. [`spec.md`](spec.md) 中 `MAX_ACTIVE_TARGETS=250`、`TARGET_TASK_WINDOW=250` 的默认容量；
2. [`configuration-failure-delivery-and-logging-plan-2026-08-28.md`](configuration-failure-delivery-and-logging-plan-2026-08-28.md)
   中“配置失败仍记录 credential/result event”的要求；
3. 同一旧方案中“monitor 失败继续生成 `monitor_collection_status`”的要求；
4. [`nats-result-publishing-final-plan-2026-08-17.md`](nats-result-publishing-final-plan-2026-08-17.md)
   中失败结果微批和 credential/control 结果发布的冲突部分；
5. credential/result event 通过 NATS 作为扫描失败进度或 CMDB 凭据命中状态回写协议的要求；
6. 任何“失败目标没有 metrics 时仍必须通过 result event 确认发布”的回执语义。

`/collect/credential_results` HTTP Interface、凭据事件 Redis ZSET、CMDB 拉取任务和投影模型均删除；
扫描一枪的凭据结果协议不在删除范围内。

旧文档的正常成功 metrics 批量、JetStream PubAck、有界队列、安全日志和 callback/deferred 契约
仍然有效。

## 4. 问题与证据

2026-08-31 生产日志显示：

- 约 3370 个插件失败，绝大多数为 SNMP 无响应；
- 944 条 `credential_result_publish_failed`；
- metrics 批量发布持续成功；
- 事件循环从毫秒级恶化到当前延迟约 10.7 秒、随后出现约 14.25 秒样本；
- CPU 接近 100%，RSS 约 4.8 GiB，结果队列达到 `250/250`；
- 第一次 `FlushTimeoutError` 与 10.7 秒事件循环延迟出现在同一秒；
- nats-py 收到晚到 PONG 后对已取消 Future 执行 `set_result()`，产生 `InvalidStateError`。

当前通用 credential 发布执行：

```text
nc.publish()
nc.flush()  # nats-py 默认 timeout=10s
```

而 `NatsResultPublisher.publish_batch()` 对 non-metrics 结果使用 `asyncio.gather()` 并发逐条发布。
在 `PUBLISH_WORKERS=4`、每批 50 的配置下，理论上可同时形成约 200 个逐事件 flush。真实路径的
最小验证中，100 个失败目标产生 100 次 credential publish，峰值并发为 100。

因此本次瓶颈不是已证明的 NATS Server 吞吐上限，而是：

```text
高并发失败和同步诊断工作
  -> 单进程 CPU/GIL 与事件循环饥饿
  -> credential 逐事件 flush Future 无法及时处理 PONG
  -> flush timeout / late PONG / read loop error / 断连重连
  -> 重复 traceback 和重试继续放大事件循环压力
```

上一次 NATS 优化有效解决了 metrics 的批量、连接复用、连接隔离和 JetStream 异步 PubAck，
但没有覆盖 credential/result event 这条后加入的旁路。

## 5. 目标架构

```text
Ingress
  |-- api/monitor.py -----------------------> workload=monitoring
  |-- api.collect.collect ------------------> workload=configuration
  `-- 既有 network_topology 识别 ----------> workload=network_topology
                         |
                         v
               UnifiedCollectionScheduler
               业务公平：global=160，weights=100/30/30
               技术资源：snmp/sync_sdk/remote_job/network_scan/default_async
                         |
                         v
              TargetPolicy / CredentialPolicy
                         |
                         v
                  CollectionPlugin
                         |
        +----------------+------------------+
        |                                   |
        v                                   v
  success + data                    failure / unreachable /
        |                           empty / credential state
        v                                   |
  SuccessfulMetricsResult                   v
        |                             LocalRunDiagnostics
        v                                   |
  MetricsDeliveryPipeline                   v
  bounded ingress + dedicated         one bounded summary log
  encode workers + encoded-byte budget
        |
        v
  metrics JetStream Adapter
  dedicated connection + bounded PubAck

CredentialPolicy <-> RedisCredentialStateStore
  - affinity
  - auth failure cooldown
  - no credential body

Control/RPC/callback -> typed ControlTransport -> dedicated Core NATS control connection
```

模块职责必须单向：

- 调度模块同时核对 workload 公平份额和 capacity group 资源，但不识别业务结果或 NATS；
- 凭据模块只决定凭据可用性、轮换、冷冻和亲和，不发布结果事件；
- 结果路由模块只决定 `metrics | callback | local_only`；
- metrics pipeline 只接受 `SuccessfulMetricsResult`，隐藏编码公平、字节背压和回执聚合；
- JetStream Adapter 只拥有传输信贷、PubAck、有限重试和连接状态；
- control Adapter 只实现 request/callback/deferred，普通业务代码不能调用通用 publish；
- 日志汇总模块只聚合有界状态，不成为消息传输 Adapter。

四层容量不得合并或互相代替：

```text
业务公平容量：谁可以开始，保证 workload/Run 公平
技术资源容量：开始后可以占用多少 SNMP、同步 SDK、remote job 等真实资源
编码容量：同时有多少成功结果执行 CPU/GIL 密集编码、可占多少待编码字节
传输容量：JetStream 同时有多少消息/字节等待 PubAck
```

## 6. 工作负载分类

### 6.1 可信入口分类

`monitoring` 的唯一产品入口是：

```text
agents/stargazer/api/monitor.py
```

当前 `/monitor/vmware/metrics`、`/monitor/qcloud/metrics`、`/monitor/oceanstor/metrics`、
`/monitor/windows/wmi/metrics` 和 `/monitor/host/metrics` 最终都经过 `_submit_monitor_request()`。
该函数是统一注入 `WorkloadClass.MONITORING` 的正确 seam。

配置采集的产品入口是
[`api.collect.collect`](../../../agents/stargazer/api/collect.py)，对应
`GET /collect/collect_info`。该入口完成 header/query 解析后调用 `_submit_collection_run()`；因此
`collect()` 是需要锁定行为的外部入口，`_submit_collection_run()` 是内部统一注入
`WorkloadClass.CONFIGURATION` 的 seam。网络拓扑继续复用既有识别。

HTTP headers、query 和普通 `params` 不得覆盖工作负载类别，防止调用方通过提交
`workload_class=monitoring` 抢占监控份额。

建议接口：

```python
def build_collection_request(
    *,
    task_id: str,
    params: Mapping[str, Any],
    workload_class: WorkloadClass,
) -> CollectionRequest:
    ...
```

`CollectionRequest` 保存规范化后的不可变字段：

```python
@dataclass(frozen=True)
class CollectionRequest:
    ...
    workload_class: WorkloadClass
```

### 6.2 与 capacity_group 解耦

现有 `capacity_group` 的 `snmp`、`sync_sdk`、`remote_job`、`network_topology`、`default`
描述技术执行成本；`workload_class` 描述业务公平份额。二者不可复用：

| 示例 | workload_class | capacity_group |
| --- | --- | --- |
| 网络设备配置采集 | configuration | snmp |
| monitor.py 的 VMware | monitoring | sync_sdk 或插件现状 |
| monitor.py 的 Host | monitoring | remote_job |
| 既有网络拓扑 | network_topology | network_topology |

执行器调用调度器时不得继续把 `self._plan.capacity_group` 当成工作负载类别。

### 6.3 多凭据能力影响复核

当前多凭据能力不是一个函数，而是以下连续链路：

```text
Server 有序凭据池
  -> cmdbcredential_N_* 下发
  -> api.collect.collect
  -> parse_credentials_pool / build_collection_request
  -> CollectionRequest.credentials
  -> CredentialPolicy.eligible_credentials
  -> CredentialAttemptRunner 串行轮换
  -> RedisCredentialStateStore 冷冻/亲和
  -> 成功业务数据进入 metrics JetStream
```

本方案必须锁定以下不变量：

| 能力 | 当前实现 | 本方案影响 |
| --- | --- | --- |
| 配置 1..3 个有序凭据 | Server credential pool | 不改 |
| 单凭据向后兼容 | 无池时规范化为一个凭据 | 不改 |
| 平铺 header 还原凭据池 | `parse_credentials_pool()` | 不改 |
| SNMP v2/v2c/v3 混合 | 每条凭据携带自己的 version | 不改 |
| 目标级凭据匹配 | `CredentialPolicy.matching_credentials()` | 不改 |
| 冷启动按池顺序尝试 | `eligible_credentials()` | 不改 |
| 认证失败换下一凭据 | `CredentialAttemptRunner` | 不改 |
| 成功立即停止后续尝试 | `CredentialAttemptRunner` | 不改 |
| 成功凭据下轮优先 | `RedisCredentialStateStore` affinity | 保留 |
| 明确认证失败进入 S1 冷冻 | `RedisCredentialStateStore` failure | 保留 |
| 凭据编辑隔离旧状态 | 任务 scope + 每凭据 revision | 补齐并锁定精确失效语义 |
| NATS 推送逐凭据结果 | `credential_result_subject` | 删除 |
| Redis 逐尝试结果事件流 | `CredentialStateCache` | 删除 |
| HTTP/CMDB 凭据状态投影 | `/credential_results`、同步任务和投影模型 | 删除 |
| Server 配置文件直执行命中表 | `CollectTaskCredentialHit` | 暂时保留，随配置文件链路另行处理 |

多凭据执行只依赖 `api.collect.collect` 下发的有序凭据池和 Stargazer 内部策略。凭据尝试不再构造
跨服务事件；成功亲和和认证失败冷冻只更新本地 Redis 引用状态，任务终态以有界日志汇总。CMDB
不需要知道哪一把凭据命中或冷冻，也不会参与 Stargazer 的候选排序。

#### 现存隔离缺口（本方案必须顺带修正）

当前 Server 下发 `collect_task_id` 和部分 `channel_config_version`，但未下发 `scope_id`、
`credential_set_version`，也没有每条凭据的内容修订号；`request_builder.py` 会将前两者回退为
`"default"`。这意味着现有
`RedisCredentialStateStore` 理论上可能在相同 `plugin_ref + target_id + credential_id` 的不同任务间
共享状态，而且凭据正文修改但 credential ID 不变时，旧冷冻可能继续生效。

本方案要求增加独立且非敏感的状态版本契约：

```text
scope_id = collect_task_id
credential_set_version = 任务级兼容 epoch（普通增删改和排序保持稳定）
credential_version = 每条凭据的非敏感内容修订号
```

新增凭据使用新的稳定 ID 和初始 `credential_version`；编辑凭据只递增该凭据版本；删除凭据只让该
ID 不再进入候选；仅调整顺序不改变任何版本。这样不会因为编辑 A 而丢失 B 的成功亲和或冷冻。
新输入顺序仍决定没有有效亲和时的尝试顺序。不得通过记录或哈希明文密码、community、token、
authkey、privkey 来生成版本。Server 在 `api.collect.collect` 的可信入站参数中下发这些字段，
Stargazer 只消费已验证值，不能让普通外部参数伪造其他任务的作用域。若发生凭据身份规则整体迁移，
才递增任务级 `credential_set_version`，使整池状态显式失效。

## 7. 160 弹性并发调度

### 7.1 不变量

对单 Stargazer 进程：

```text
configuration_active
+ monitoring_active
+ network_topology_active
<= 160
```

配置：

```text
MAX_ACTIVE_TARGETS=160
TARGET_TASK_WINDOW=160
CONFIGURATION_BASE_SLOTS=100
MONITORING_BASE_SLOTS=30
NETWORK_TOPOLOGY_BASE_SLOTS=30
COLLECTION_IDLE_SLOT_BORROW_ENABLED=true

# 技术资源容量的保守起始范围，最终由生产等价压测锁定
SNMP_MAX_IN_FLIGHT=100
SYNC_SDK_MAX_IN_FLIGHT=16
REMOTE_JOB_MAX_IN_FLIGHT=20
DEFAULT_ASYNC_MAX_IN_FLIGHT=160
```

启动时验证：

- 全局上限大于 0；
- 三个基础份额均大于 0；
- 三个基础份额总和等于全局上限；
- workload class 必须属于固定枚举；
- 配置非法时 fail-fast，不静默回退 250。

### 7.2 软配额和借槽

三类均持续积压时，稳态目标为：

```text
configuration=100
monitoring=30
network_topology=30
```

某类没有运行或排队目标时，其份额进入共享空闲池。只有一个类别时，该类别可以使用全部 160。
两个类别同时积压时，对仍活跃的权重重新归一，例如：

```text
configuration + monitoring ~= 123 / 37
monitoring + network_topology ~= 80 / 80
```

这些是长期调度目标，不要求每个瞬间严格相等。

### 7.3 自然再平衡

借槽不产生抢占。假设 configuration 已使用 160 个槽位，monitoring 新到达：

1. 现有 configuration 目标继续执行；
2. 后续释放的槽位优先补给 monitoring；
3. 达到当前活跃类别的权重目标后恢复公平轮转；
4. 不取消 SNMP、SSH、SDK 或 callback 在途任务。

### 7.4 两级公平

调度器使用两级策略：

1. workload 级加权公平轮询，负责份额、借槽、归还和防饿死；
2. 同 workload 内按 CollectionRun round-robin，避免单个大 Run 饿死新 Run。

每派发一个目标后保留事件循环让步，避免一次填满 160 个 Task 而长期不让定时器和 I/O 运行。

### 7.5 统一调度 Interface

```python
class UnifiedCollectionScheduler:
    async def execute(
        self,
        run_id: str,
        workload_class: WorkloadClass,
        capacity_group: CapacityGroup,
        items: Iterable[T],
        handler: Callable[[T], Awaitable[R]],
    ) -> tuple[R, ...]:
        ...
```

调用方不感知份额计算、借槽债务、再平衡、技术资源许可、active 计数和 Run 内轮询。调度器只有在
workload 份额和 capacity group 容量同时可用时才创建目标 Task，不能先占用全局 160 再等待技术
资源，否则会形成“160 个目标都在等待线程池”的假活跃。测试也只通过这个 Interface 验证可见行为。

### 7.6 技术资源准入

`capacity_group` 必须从观测标签升级为真实准入条件：

```text
snmp             原生异步 SNMP socket、重试和 timeout callback
sync_sdk         VMware/云厂商/数据库等同步 SDK 专用线程池
remote_job       Host/作业平台提交、回调与远端占用
network_scan     单目标内部多 IP/端口探测
default_async    未命中特殊成本模型的普通异步采集
```

一个多凭据目标在整个串行轮换期间只占一个 workload 槽和一个 capacity group 许可；不得为每条凭据
创建独立目标 Task。许可必须在取消、超时和异常路径统一释放。

技术容量初值只是上线压测起点，不是产品份额：`snmp` 可先从 `100~120`、`sync_sdk` 从 `16~32`、
`remote_job` 从 `20~30` 验证；最终值写入部署配置，并由启动校验保证为正数且不超过允许上界。

许可生命周期必须分开，避免某一层替另一层背压：

```text
workload/target permit
  获取：目标开始 probe 前
  释放：local-only 终态完成，或成功结果被 MetricsDelivery 入口队列接纳后

capacity-group permit
  获取：进入对应 probe/collect 技术操作前
  释放：该技术操作结束后；等待 metrics 队列和 PubAck 时不得继续占用

encode byte credit
  获取：编码产生 chunk 时
  释放：chunk 交给传输阶段或被终止清理后

JetStream credit
  获取：消息进入 publish/PubAck 窗口前
  释放：PubAck、明确失败或取消清理后
```

当 JetStream 变慢时，背压按传输窗口、encoded bytes、成功结果入口队列逐级传回；入口队列满后，
成功目标最多占住既有 160 个 target permit 等待有界接纳，不再创建无界 `queue.put()` waiter，也不
持有 `sync_sdk`/`snmp` 技术许可。等待超过交付总预算后返回明确的 retryable/unknown 状态，不能无限
阻塞或转投 Core NATS。

### 7.7 插件内部 fan-out

外层 160 不能代表真实 socket、线程和协程数量。插件不得继续无约束地自行创建
`ThreadPoolExecutor` 或大批 `asyncio.create_task()`：

- 同步 SDK 统一通过 `PluginExecutionResources.run_sync_sdk()` 使用进程级专用有界线程池；
- IP/端口扫描通过 `PluginExecutionResources.map_network_io()` 使用共享网络 I/O 预算；
- 插件声明期望并行度，实际并行度取声明值与当前共享预算的较小值；
- 未迁移的内部 fan-out 插件先归入保守 `legacy_sync`/专用 capacity group，避免绕过总资源上限；
- 优先迁移 SNMP、monitor 入口使用的 SDK 和高频配置采集插件，再分批治理其他插件。

### 7.8 借槽债务与监控派发

“单类可借满 160”和“新类别立即拥有保留槽”在非抢占条件下不能同时保证。本方案选择非抢占借槽
债务：新 workload 排队后，借用方立即停止获得新槽；后续每个释放槽优先偿还债务，直到恢复当前
权重目标。验收拆成：

```text
first_dispatch_wait_seconds                 # 含在途目标剩余执行时间，只观测和告警
slot_released_to_entitled_dispatch_seconds  # 调度器自身归还延迟，p99 < 100ms
```

若未来产品要求 monitoring 到达即有硬容量，只能永久保留部分槽位或引入可取消任务；这与当前“无
任务时其他类别可占满 160”的口径冲突，不属于本方案。

## 8. 结果路由与交付语义

### 8.1 路由决策

| 结果 | 冷冻凭据 | 成功亲和 | metrics | credential event | 本地汇总 |
| --- | --- | --- | --- | --- | --- |
| success 且有有效数据 | 否 | 是 | 是 | 否 | 是 |
| success 但数据为空 | 否 | 是 | 否 | 否 | 是 |
| auth/capability failure | 是 | 否 | 否 | 否 | 是 |
| 全部凭据冷冻 | 否 | 否 | 否 | 否 | 是 |
| no response / unreachable | 否 | 否 | 否 | 否 | 是 |
| plugin timeout / expected failure | 否 | 否 | 否 | 否 | 是 |
| unexpected framework error | 否 | 否 | 否 | 否 | 一次 ERROR |

显式 callback/deferred 请求按其业务协议路由，不使用上表的普通 metrics 交付回执。

### 8.2 失败不进入发布队列

失败结果在 TargetCollection 完成时直接：

```text
更新 RunSummary
记录有限失败样本
返回 local_only 终态
```

它不得：

- 进入 `BufferedResultPublisher`；
- 等待发布队列；
- 触发发布重试；
- 被计为 `publish_succeeded`；
- 被计为 NATS/JetStream 发布失败；
- 生成伪 `collection_status`、`monitor_collection_status` 或 error metric。

建议显式交付状态：

```text
metrics_delivery = confirmed | retryable_failed | permanent_failed | unknown | not_applicable
```

普通失败的 `metrics_delivery=not_applicable`，不是发布成功，也不是发布失败。

### 8.3 成功数据发布

只有成功且非空结果进入：

```text
Result validation
  -> bounded metrics queue
  -> batch encode / byte split
  -> metrics JetStream publish window
  -> PubAck
```

继续复用现有 [`jetstream_publish_window.py`](../../../agents/stargazer/core/infra/jetstream_publish_window.py)
的稳定 message ID、消息数/字节数双窗口、PubAck timeout、有限重试和 shutdown 排空。

结果路由必须先构造不可变 `SuccessfulMetricsResult`，`MetricsDelivery` Interface 只接受该类型：

```python
class MetricsDelivery:
    async def enqueue(
        self,
        result: SuccessfulMetricsResult,
    ) -> DeliveryReceipt:
        ...
```

`MetricsDeliveryPipeline` 在这个 seam 后隐藏四项实现：

1. 按目标数和估算/实际字节数双重限制成功结果入口队列；
2. 使用独立于同步 SDK 的专用编码执行器，初始 `METRICS_ENCODE_WORKERS=2`；
3. 单次编码同时完成格式校验、分块和稳定 message ID 生成，避免同一结果完整转换两次；
4. 按 `task_id + subject` 公平轮转有界 chunk，再交给全局 JetStream 消息/字节信贷窗口。

建议起始预算为成功结果队列不超过 160、encoded pending bytes `32~64 MiB`、JetStream pending
messages `256`、pending bytes `32 MiB`。最终值必须满足：原始成功结果、已编码结果和 JetStream
pending 的合计稳态内存不超过容器预算约 30%，并以全成功大结果压测为最终证据。

### 8.4 round-complete 约束

现有 `cmdb_round_complete` 是成功快照提交协议，不作为失败结果或 Run 汇总通道。本方案建议：

- 只有本轮至少产生一条成功业务 metrics，且这些 metrics 均完成发布确认时，才允许发布既有
  round-complete marker；
- 全失败、全不可达、全空结果的 Run 不发布 marker；
- marker 不包含失败数、凭据信息或 Run 汇总；
- marker 失败不得把已成功发布的数据改写为失败，但必须有有界诊断。

这一条需要在确认本方案时单独确认，因为它是“只推成功数据”规则下唯一保留的成功数据完整性
控制标记。

## 9. 凭据冷冻与 Redis 边界

### 9.1 保留

保留 [`credential_policy.py`](../../../agents/stargazer/core/collection/credential_policy.py) 和
[`RedisCredentialStateStore`](../../../agents/stargazer/core/collection/redis_state.py)：

- 目标级可用凭据筛选；
- 成功凭据亲和；
- 认证/权限失败连续计数；
- `5m -> 30m -> 4h -> 24h` 冷冻梯度和有限 jitter；
- 成功后清除当前凭据失败；
- 多 Stargazer 实例通过 Redis 共享状态；
- Redis 中只保存凭据 ID 摘要和状态，不保存凭据正文。

只有明确认证或权限失败才冷冻。SNMP 无响应、网络不可达、插件超时、服务不可用、协议不匹配、
NATS/Redis 错误不得冷冻凭据。

### 9.2 任务作用域与凭据状态版本

冷冻/亲和身份包含：

```text
scope_id + plugin_ref + target_id
+ credential_set_version
+ credential_id + credential_version
```

`credential_version` 变化只隔离被编辑凭据的旧状态；`credential_set_version` 只用于显式整池迁移。
版本由可信调用方生成，不记录凭据正文。该身份只服务 Stargazer Redis 内部亲和/冷冻隔离，
不形成对外状态协议。

### 9.3 三类状态必须分开

凭据状态分为两个互不连通的范围：

| 状态 | 作用 | 处理原则 |
| --- | --- | --- |
| `RedisCredentialStateStore` | Stargazer 普通配置/监控执行时的凭据亲和和冷冻 | 必须保留，是该运行时唯一权威 |
| CMDB `CollectTaskCredentialHit` | 暂缓的配置文件 Server 直执行链路 | 本轮不改，不接收 Stargazer 状态 |

旧 `CredentialStateCache` 已确认只服务被删除的结果事件流与旧查询，因此整体删除。多凭据运行时
继续使用 `RedisCredentialStateStore`，二者不是同一个 Module。扫描一枪继续使用自己的
`ScanHit/ScanFamilyRun` 状态，不写 `CollectTaskCredentialHit`。

确定删除的 NATS 部分：

```text
result_publisher credential Core NATS immediate publish/flush
CollectCredentialResultPushService.push_once NATS publish
collect credential result push loop
bklite.receive_collect_credential_result NATS handler
credential_result_subject 下发字段
CredentialStateCache 结果事件流、游标和生命周期
GET /collect/credential_results
CMDB credential projection Celery/HTTP 同步与模型迁移
```

### 9.4 Redis 最小状态 Interface

普通配置/监控采集只允许以下 Redis 操作：

- 每个目标开始前一次 `MGET`：读取成功亲和和本次候选凭据的冷冻状态；
- 明确认证/权限失败时一次 `SET EX`：写非敏感失败状态和到期时间；
- 成功时一次两键 Lua：原子更新成功亲和，并只清除当前成功凭据自身的失败状态；
- 凭据版本变化后自然使用新 key，旧状态按 TTL 回收。

不使用进程级全局 `asyncio.Lock`，不写事件 ZSET、revision、cursor、tombstone，也不做 CMDB/HTTP
投影。SNMP 无响应、不可达、插件超时、普通失败和空成功不会产生凭据 Redis 写操作。

以下基础状态继续保留：

```text
RedisRunStateStore
RedisCredentialStateStore
RedisRoundMetadataStore（仅成功快照需要）
Deferred callback context
```

## 10. 日志契约

### 10.1 复杂度上界

失败日志从：

```text
O(失败目标数 * traceback 行数)
```

收敛为：

```text
O(Run 数 + 固定失败样本数)
```

### 10.2 单目标预期失败

认证失败、凭据冷冻、冷冻跳过、无响应、不可达、插件超时等使用 DEBUG 单行，不带 traceback。
不得记录 payload、响应正文、凭据正文或无界目标列表。

### 10.3 Run 汇总

每个 Run 输出一条有界 INFO/WARNING 终态日志：

```text
event=collection_run_summary
task_id=...
workload_class=configuration|monitoring|network_topology
total=3370
success=0
failed=3370
unreachable=0
auth_failed=0
credential_frozen=0
protocol_no_response=3370
duration_seconds=...
peak_active_targets=160
metrics_published_targets=0
```

失败样本最多 3 个，失败类型最多 Top 8，其余合并为 `other:<count>`。

### 10.4 ERROR 所有权

预期协议失败没有 traceback。只有框架不变量破坏、状态损坏等非预期程序错误由一个运行边界记录
一次 ERROR traceback。NATS 发布窗口失败也只由发布边界记录一次终态错误。

## 11. NATS 与底层依赖

### 11.1 最终连接拓扑

```text
metrics connection
  -> 只发成功业务数据和已确认保留的成功快照 marker
  -> JetStream bounded PubAck window

control connection
  -> typed ControlTransport
  -> request/reply
  -> explicit callback/deferred control protocol
```

credential/result event 不再使用 control 连接。

业务代码不再直接依赖通用 `nats_publish(subject, payload)`。对外只保留小而明确的 Interface，例如：

```python
class ControlTransport:
    async def request(...): ...
    async def publish_callback(...): ...
    async def publish_deferred(...): ...
```

底层 Core NATS `publish + flush` 只允许隐藏在这些低频 Adapter 后；subject allowlist 或等价的固定
方法必须阻止凭据结果、逐目标失败、Run 汇总、状态同步和普通业务批量重新接入 control 连接。

### 11.2 JetStream-only 与就绪语义

生产模式下 metrics 只允许 JetStream：

- JetStream 默认启用；若把 `NATS_METRICS_JETSTREAM_ENABLED` 显式关闭，生产装配在启动配置校验时 fail-fast；
- 不允许 `nats_publish_lines()` 静默回退到 Core NATS 批量 publish/flush；
- Stream、subject 或 ACL 暂不可用时进程可以完成基础启动，但 collection readiness 不通过；
- 已进入发布流程的结果按有界队列、PubAck timeout 和有限重试返回明确交付状态；
- JetStream 故障不占用 control 连接，也不能触发 Core NATS fallback；
- 测试环境如需 Core NATS 兼容路径，必须显式使用 test-only Adapter，生产装配不能引用。

### 11.3 不需要的基础设施改动

- 不新增 `CMDB_CREDENTIAL_RESULTS` Stream；
- 不新增 durable credential Consumer；
- 不修改 NATS 集群副本和存储架构；
- 不新增 Python 依赖；
- 不把 nats-py 升级作为实施前置；
- 不增加 flush timeout。

metrics JetStream 继续使用现有部署和 ACL，但发布窗口从当前宽松默认值调整为生产压测确认的消息数/
字节数双预算。control NATS ACL 可在旧 credential 协议下线后移除对应 subject 发布权限。

## 12. 代码影响清单

### 12.1 Stargazer

| 文件/模块 | 计划变更 |
| --- | --- |
| `api/monitor.py` | 在 `_submit_monitor_request()` 可信注入 monitoring |
| `api/collect.py` | 锁定 `api.collect.collect` 为 configuration 入口；保护多凭据解析；删除凭据状态查询端点 |
| `core/collection/contracts.py` | 增加 `WorkloadClass`、`CapacityGroup`、`SuccessfulMetricsResult` 和请求字段；明确 not_applicable 交付语义 |
| `core/collection/request_builder.py` | 接收可信 workload 参数，不接受 HTTP 覆盖；保持 credentials_pool 顺序和身份 |
| `core/collection/scheduler.py` | 实现统一双维准入：全局 160、三类权重、借槽债务、Run 公平和 capacity group 许可 |
| `core/collection/application.py` | 装配 160/100/30/30、技术资源预算、专用编码执行器；不注入任何凭据结果 sink |
| `core/collection/executor.py` | 同时按 request workload 和 plan capacity group 调度；失败 local-only；round marker 新条件 |
| `core/collection/plugin_execution_resources.py` | 新增共享同步 SDK 执行器和网络 I/O 预算，替代插件私有线程池/无界 fan-out |
| `core/collection/result_delivery.py` | 失败不入队、不重试、不计发布成功；callback 单独处理 |
| `core/collection/credential_policy.py`、`credential_attempt.py` | 保留目标匹配、亲和排序、S1 冷冻、串行轮换和成功即停 |
| `core/collection/result_publisher.py` | 收敛为 `MetricsDeliveryPipeline`：只接受成功类型、编码/字节背压、公平分块和回执聚合 |
| `tasks/utils/metrics_helper.py` | 删除 monitor/config 失败伪指标生成 |
| `tasks/utils/nats_helper.py` | 删除 credential result publish helper；编码改为一次完成并使用专用执行器 |
| `core/infra/nats_utils.py` | 生产 metrics JetStream-only；删除静默 Core fallback；control 普通 publish 收口到 typed Adapter |
| `core/infra/control_transport.py` | 新增 request/callback/deferred 小 Interface 与固定 subject 装配，不暴露通用批量 publish |
| `core/infra/credential_state_cache.py` | 整体删除；运行时冷冻/亲和由 `RedisCredentialStateStore` 独立承担 |
| `service/collect_credential_result_push_*` | 整体删除，不保留 NATS 或 HTTP 替代通道 |
| 日志与指标模块 | 增加 workload active/pending/borrowed 观测，收口失败日志 |

### 12.2 Server

为保证多凭据状态正确隔离，必须新增：

- `CollectModels` 或其任务参数中的任务级兼容 epoch，以及每条凭据的 `credential_version`；
- `collect_service.py` 在凭据内容编辑时只递增该凭据版本；新增、删除、重排不清空其他凭据状态；
- `node_configs/base.py` 下发 `scope_id=collect_task_id`、兼容 epoch 和每条凭据版本；
- 单凭据、多凭据、跨任务隔离和编辑失效回归测试。

确定停用或删除：

- `bklite.receive_collect_credential_result`；
- 只服务于 NATS credential push 的测试和协议代码。

明确保留：

- `receive_scan_credential_result` 扫描一枪协议及其 `ScanHit/ScanFamilyRun` 进度；
- `CollectTaskCredentialHit` 及 `CollectHitStateService` 暂时只服务配置文件 Server 直执行链路；
- 多凭据池版本生成和 NodeParams 下发，不回写 Stargazer 运行状态。

Server 自己在同步业务流程中直接维护的状态不应因删除 Stargazer 异步事件而被误删，实施前按真实
调用者做引用检查。

### 12.3 文档与配置

- 更新 `.env.example` 的 `250/250/50` 旧默认；
- 增加 capacity group、编码 worker/字节预算和 JetStream 双窗口的生产配置及启动校验；
- 明确生产禁止 metrics Core NATS fallback，测试兼容 Adapter 不进入生产装配；
- 更新 `README.md` 容量、Redis用途和日志查询说明；
- 在 `spec.md` 顶部登记本方案替代关系；
- 更新 NATS生产部署文档，明确不需要 credential Stream；
- 更新运维告警，删除 credential event backlog 指标。

## 13. 实施阶段

### 阶段 0：反馈环与基线

先把现有最小验证固化为自动化测试：100 个配置失败目标不得产生 100 次 credential publish。
记录当前 160/250 对照基线：事件循环、CPU、RSS、结果队列、metrics PubAck 和 control RTT。

### 阶段 1：工作负载分类与统一双维调度器

1. 增加 `WorkloadClass`；
2. monitor/collect 入口可信注入；
3. 接入既有网络拓扑分类；
4. 补齐 `scope_id=collect_task_id`、任务兼容 epoch 和每凭据 revision 下发；
5. 实现 160/100/30/30、借槽债务和非抢占自然再平衡；
6. 让 `capacity_group` 成为真实准入条件，保证目标只在 workload 与技术资源同时可用时启动；
7. 增加共享同步 SDK/网络 I/O 资源 Module，优先迁移 SNMP、monitor 和高频配置插件；
8. 增加调度、多凭据隔离、技术资源上限和取消释放行为测试；
9. 此阶段不改变结果发布，便于单独回滚。

### 阶段 2：成功数据唯一出站

1. 在结果路由 seam 增加 `metrics | callback | local_only`；
2. 配置和监控失败统一 local-only；
3. 失败不进入 `BufferedResultPublisher`；
4. 删除 `monitor_collection_status` 和其他失败伪指标；
5. 只有成功非空结果可以构造 `SuccessfulMetricsResult` 并进入 `MetricsDelivery` Interface；
6. 按确认结论调整 round-complete 条件。

### 阶段 3：credential 事件断流

1. 无条件停止即时 Core NATS publish/flush；
2. 无条件停止定时 NATS 推送；
3. 无条件保留多凭据解析、轮换、冷冻和亲和；
4. 停止生成逐尝试 credential events，删除旧 Redis event 代码，存量 key 由 TTL/运维清理；
5. 删除凭据 HTTP 查询、CMDB 拉取任务和未发布的投影迁移；
6. 保留多凭据解析、轮换、冷冻和亲和，不保留 CMDB 状态展示。

### 阶段 4：metrics pipeline 与 NATS Interface 收口

1. 建立有界 `MetricsDeliveryPipeline`，拆分入口队列、专用编码执行器、已编码字节预算和 JS 传输窗口；
2. 编码 worker 初始为 2，单次编码完成校验、分块和 message ID，避免完整转换两次；
3. 按 `task_id + subject` 公平轮转 chunk，不允许单个大结果长期占用发送器；
4. 生产 metrics 改为 JetStream-only，禁止静默 Core NATS fallback；
5. 将 control 收敛为 request/callback/deferred typed Interface，删除业务层通用 publish 入口；
6. 加入 Stream/ACL readiness、消息/字节窗口和 encode/SDK 隔离测试。

### 阶段 5：日志收口

1. 预期失败改为 DEBUG 单行；
2. 删除逐目标插件预期异常调用链；
3. 保留每 Run 一条汇总和最多 3 个样本；
4. 锁定单一 ERROR traceback 所有权；
5. 验证敏感哨兵和完整 payload 不泄漏。

### 阶段 6：Server 兼容清理

1. 确认没有旧 Stargazer 继续发送 NATS credential events；
2. 停用旧 Core NATS handlers；
3. 删除 CMDB 凭据投影服务、Beat 配置和未发布迁移；
4. 按保留期处理旧历史 Redis event keys，不主动扩大部署风险；
5. 不清理配置文件直执行仍使用的状态表或扫描一枪协议。

### 阶段 7：生产等价压测

使用生产等价 CPU/memory quota 验证全失败、全成功、混合成功、三类任务并发、借槽归还、慢 PubAck
和 control RPC 隔离。必须覆盖瞬时 `1000/2500/5000` 的 Run/目标任务突发，以及 `100/30/30`、
`100/20/20` 两种执行并发形态。未达到验收线时，不得通过延长 NATS timeout 或放宽线程/字节窗口
放行。

## 14. 灰度与回滚

建议迁移期开关：

```text
COLLECTION_SCHEDULER_V2_ENABLED=true
SUCCESS_METRICS_ONLY_ENABLED=true
CREDENTIAL_RESULT_PUBLISH_ENABLED=false
CREDENTIAL_RESULT_HISTORY_EVENT_STORE_ENABLED=false
CREDENTIAL_STATE_PROJECTION_ENABLED=true
CREDENTIAL_STATE_PULL_ENABLED=true
NATS_METRICS_JETSTREAM_ENABLED=true
METRICS_ENCODE_WORKERS=2
```

规则：

- 开关默认值和删除时点分阶段提交，避免一个版本同时改变所有路径；
- 新代码不做 Core NATS + 另一通道双写；
- 生产回滚不得启用 metrics Core NATS fallback；如需回退发布实现，只能回退到上一版 JetStream Adapter；
- Server旧消费者保留到旧Stargazer全部退出；
- Redis旧事件 key 在回滚窗口结束前不物理删除；
- 调度器回滚不自动恢复 250，容量上限变更需显式配置和授权；
- 回滚不得清除凭据冷冻状态。

## 15. 测试计划

### 15.1 调度器 seam

1. 三类持续积压时 `active_total <= 160`，分配收敛到 `100/30/30`；
2. 任一类别独占时可以达到 160；
3. configuration + monitoring 收敛到约 `123/37`；
4. 借满 160 后新类别到来不取消在途任务，并通过自然完成取回份额；
5. 同类别多个 Run 不饥饿，新 Run 能获得首个槽位；
6. 取消一个 Run 不泄漏 active/borrowed 计数；
7. `api/monitor.py` 所有路由归入 monitoring；
8. `api/collect.py` 不能通过外部参数伪造 monitoring。

### 15.2 技术资源准入 seam

1. workload 有空闲但 `capacity_group` 已满时不得创建目标 Task，也不得占用 active target；
2. `snmp`、`sync_sdk`、`remote_job`、`network_scan` 分别不超过各自配置上限；
3. 多凭据 A/B/C 串行轮换始终只占一个 target 和一个 capacity group 许可；
4. 取消、timeout、插件异常和 shutdown 均不泄漏许可；
5. 插件声明内部并行度 50 时，实际 fan-out 不超过共享剩余预算；
6. 多个同步 SDK 插件并发时只使用共享专用执行器，不创建每目标私有线程池；
7. configuration 借满 160 后 monitoring 到来，首个槽释放至应得派发延迟 p99 `<100ms`。

### 15.3 结果路由 seam

1. configuration/monitoring 的 failed、unreachable、empty 均不调用 metrics Adapter；
2. 失败不调用 credential Adapter、Redis event sink 或 control flush；
3. 成功非空数据仍批量进入 metrics Adapter；
4. callback/deferred 保持原业务回执；
5. local-only 不计 publish success/failure；
6. 全失败 Run 不发布 round marker；
7. 有成功数据时按确认规则发布 round marker。

### 15.4 metrics pipeline 与 NATS seam

1. `MetricsDelivery.enqueue()` 拒绝任何不能构造为 `SuccessfulMetricsResult` 的输入；
2. 生产装配关闭 JetStream 时 fail-fast，JetStream 故障时不调用 Core NATS fallback；
3. metrics 慢 PubAck/断连时入口队列、encoded bytes 和 JS pending 均不超过配置上限；
4. 编码并发跨全部 publish worker 始终不超过 `METRICS_ENCODE_WORKERS`；
5. 编码使用专用执行器，不能挤占 `sync_sdk` 线程池；
6. 一个大结果和多个小结果并存时，按 lane 轮转，小结果无饥饿；
7. 单个结果只执行一次完整格式转换，超行数/字节数在任何 NATS 投递前失败；
8. control Adapter 只接受 request/callback/deferred，普通结果和动态 subject 无法通过其 Interface；
9. metrics 拥塞时 control RPC 仍可用，延迟不随 metrics pending 线性恶化；
10. shutdown 在 grace 内排空已接纳结果，超时后返回明确的未知/失败回执且不无限等待。

### 15.5 凭据状态 seam

1. `api.collect.collect` 能从平铺 header 和兼容 payload 还原有序凭据池；
2. 单凭据任务行为不变；多凭据冷启动按稳定输入顺序尝试；
3. SNMP v2/v2c/v3 混合凭据保持各自 version 和字段；
4. 认证失败按 `5m/30m/4h/24h` 冷冻并继续下一未冷冻凭据；
5. SNMP no response、unreachable、timeout 不冷冻；
6. 成功后立即停止本目标后续凭据尝试；
7. 成功只清当前凭据失败并记录亲和，下轮优先该凭据；
8. 多应用实例共享 Redis 状态；
9. Redis 不保存密码、community、token、auth/priv key；
10. 两个任务使用相同 target/credential ID 时，由 `scope_id=collect_task_id` 隔离状态；
11. 编辑凭据只使该凭据 revision 变化；新增、删除、重排不清空其他凭据状态；
12. 版本生成和日志不读取、不哈希、不输出凭据正文；
13. Redis故障保持既有安全降级语义；
14. 代码和运行时均不存在 credential NATS/HTTP/CMDB 投影适配器；
15. 扫描一枪协议仍正常，但不写普通采集的 `CollectTaskCredentialHit`。

### 15.6 日志

1. 3370 个相同预期失败没有逐目标 ERROR traceback；
2. 每 Run 只有一条终态汇总；
3. 失败样本最多 3，类型最多 Top 8 + other；
4. 模板使用独立惰性参数；
5. 完整格式化日志不含敏感哨兵、payload、响应正文；
6. 一个非预期失败只有一个 traceback owner。

### 15.7 建议定向命令

```bash
cd agents/stargazer
uv run pytest -q -o addopts='' \
  tests/test_collection_scheduler.py \
  tests/test_collection_request_builder.py \
  tests/test_collection_end_to_end.py \
  tests/test_result_publisher.py \
  tests/test_credential_policy.py \
  tests/test_redis_collection_state.py \
  tests/test_collect_multicred.py \
  tests/test_collect_credential_push.py \
  tests/test_plugin_error_logging.py \
  tests/test_windows_wmi_monitor.py \
  tests/test_capacity_usage_reporter.py
```

Server 清理阶段必须运行 credential pool、SNMP 混合凭据、节点参数下发、配置文件直执行 hit-state
和扫描一枪测试；不能用删除旧 NATS 测试来代替证明多凭据执行能力未回归。

### 15.8 瞬时突发与并发组合压测

“任务”必须按两个 seam 分开压测，避免把 Run 接纳能力和目标执行能力混为一个数字：

1. **Run/API 瞬时突发**：在不超过 1 秒的提交窗口内向 Stargazer 提交 `1000`、`2500`、`5000`
   个生产等价请求，验证解析、Redis RunLease、`MAX_ACTIVE_RUNS`、重复提交和明确过载响应；
2. **目标任务瞬时突发**：在一个或多个已接纳 Run 中一次性提供 `1000`、`2500`、`5000` 个目标，
   验证 pending 表示、target task window、双维调度和完成排空，不能在入口为全部目标立即创建 Task。

瞬时突发的定义是负载发生器完成提交的实际窗口 `<=1s`。如果压测端自身无法达到，应记录真实
提交窗口和实际 requests/s，不得把较长的渐进加压标记为瞬时突发。

主矩阵共六组，每组至少重复三次并报告冷启动一次、预热后两次：

| Burst | 并发形态 A | 并发形态 B |
| --- | --- | --- |
| 1000 | configuration/monitoring/topology=`100/30/30` | `100/20/20` |
| 2500 | configuration/monitoring/topology=`100/30/30` | `100/20/20` |
| 5000 | configuration/monitoring/topology=`100/30/30` | `100/20/20` |

形态语义：

- `100/30/30`：持续补充三类 backlog，使 active 稳态达到 160，验证正式竞争份额；
- `100/20/20`：生产全局上限仍为 160，压测端第一阶段只提供 140 个可运行目标，验证 20 个槽确实
  空闲而不是被虚假 active/waiter 占用；第二阶段再增加 20 个 configuration 目标，验证其可借槽达到
  `120/20/20=160`；不得把该用例误写成生产基础份额改为 `100/20/20`。

每个主矩阵至少覆盖四种结果分布：

1. 全部 SNMP no-response：普通结果 NATS 为 0，专门复现本次事故的反证；
2. 30% 成功、70% 失败：验证失败 local-only 与成功 JetStream 并存；
3. 全成功小结果：验证稳态吞吐和 PubAck；
4. 全成功大结果：验证编码 worker、GIL、RSS、encoded bytes 和 JetStream 窗口。

补充故障注入不必与所有组合做笛卡尔积，但至少在 `2500 + 100/30/30` 和
`5000 + 100/30/30` 下各执行一次：

- JetStream PubAck 变慢；
- metrics 连接断开并恢复；
- Redis 延迟升高/短暂不可用；
- control RPC 与 metrics 高峰同时发生；
- 多凭据 A 认证失败、B 成功。

Run/API 突发必须记录每个提交的唯一终态：`accepted`、`duplicate_active`、`busy/retryable` 或明确
失败，四类总数必须等于提交总数。当前 `MAX_ACTIVE_RUNS` 语义允许容量满时返回 `BUSY`，但不允许
5xx 风暴、超时无响应、已返回 accepted 后静默丢失，或同一 `task_id` 在幂等重试后执行两次。若产品
要求 5000 个 Run 一次全部 accepted，则需要另行设计 Redis 持久 Run 队列；不得用扩大进程内
`MAX_ACTIVE_RUNS` 或创建 5000 个 Task 实现。

每组采集以下时序和资源数据：

```text
实际提交窗口、requests/s、API p50/p95/p99/max
accepted/duplicate/busy/retryable/5xx/timeout 数量
active/pending Run，active/pending/completed target
各 workload active/pending/borrowed/first-dispatch
各 capacity group active/pending/limit
event-loop lag p50/p95/p99/max、timeout overshoot
CPU、cgroup throttling、RSS、线程、FD、默认/专用线程池队列
Redis pool wait、命令 p99、RunLease acquire/finish/heartbeat
成功结果入口、encode queue、encoded pending bytes
JS pending messages/bytes、PubAck p95/p99/timeout/retry
control RPC p95/p99、disconnect/reconnect
总排空时间、吞吐 targets/s、终态对账、测试后残留 Task/permit/key
```

## 16. 验收标准

### 16.1 3370 个 SNMP 无响应

```text
metrics business messages              = 0
credential NATS messages                = 0
credential Core NATS flush              = 0
Redis credential history event writes  = 0
Redis credential state changes          = 0
SNMP no-response credential freezes     = 0
Run terminal summaries                  = 1
```

不得出现：

- `credential_result_publish_failed`；
- 由采集失败结果触发的 `FlushTimeoutError`；
- credential 事件导致的 control disconnect；
- 数千条重复 ERROR traceback；
- 失败结果占满 metrics发布队列。

### 16.2 混合 300 成功、700 失败

- 只有 300 个成功目标的有效数据进入 metrics；
- 700 个失败目标不进入任何普通结果 NATS subject；
- 明确认定的认证失败仍写 Redis 冷冻；
- Run 只有一条有界终态汇总；
- metrics PubAck 可对账，control/RPC 不受失败结果影响。

其中“凭据 A 明确认证失败、凭据 B 成功”的目标必须满足：

```text
credential attempts                     = A, B
Redis state transitions                 = A frozen + B affinity
HTTP/CMDB credential projection         = absent
credential NATS messages                = 0
metrics NATS                             = only B successful business data
```

### 16.3 调度

- 单进程 active targets 永不超过 160；
- 三类持续积压时长期分配接近 `100/30/30`；
- 单类独占时可以使用 160；
- 新类别到来不抢占，且能在自然完成后获得份额；
- workload 和 Run 均无饥饿；
- 借用方存在债务时不再获得新槽，槽释放至应得 workload 派发的 p99 `<100ms`；
- 每个 capacity group 的在途量不超过配置值，等待技术资源的目标不计入 active 160；
- 插件内部共享 fan-out 和同步 SDK 线程数均不超过进程级资源预算。

### 16.4 多凭据回归

- `api.collect.collect` 仍是配置采集入口；
- 单目标可按稳定顺序尝试多个凭据；
- 明确认定认证失败后继续下一未冷冻凭据；
- 任一凭据成功后停止该目标后续尝试并正常发布成功数据；
- 下一轮优先最近成功凭据；
- 冷冻期跳过错误凭据，被编辑凭据不继承自己的旧状态；
- 不同采集任务的相同 target/credential ID 不共享亲和或冷冻；
- SNMP v2/v2c/v3 混合凭据正常工作；
- credential NATS 消息和 flush 始终为 0；
- 不产生逐尝试 result events，也不存在 HTTP/CMDB 凭据状态投影。

### 16.5 性能

生产等价压测目标：

```text
event loop lag p99 < 1s
CPU 不长期保持 100%
RSS 达到稳态，不随 Run 持续线性增长
metrics queue 不长期 100%
metrics encode workers 不超过配置值
encoded pending bytes 不超过配置值
control RPC 在采集高峰可用
metrics PubAck timeout/reject 在正常网络下为 0
```

160 是业务设定的上限，不是未经压测即可宣称安全的结论。如果仍不满足事件循环目标，应继续定位
PySNMP timeout callback、同步日志、Python编码和线程池 GIL 竞争，必要时降低具体工作负载并发。

### 16.6 NATS 架构

- 生产 metrics 未启用 JetStream 时配置校验失败，不存在静默 Core NATS fallback；
- 普通采集结果、凭据结果、失败结果和 Run 汇总均无法通过 control Interface；
- control Core NATS flush 只可能来自显式 callback/deferred 等低频协议；
- metrics 慢 PubAck 或断连只消耗有界 metrics 信贷，不占用 control 连接；
- 一个全失败 Run 的 metrics/credential NATS 消息和普通结果 flush 均为 0；
- 一个全成功大结果 Run 的 CPU、RSS、编码并发、encoded pending 和 JS pending 均达到稳态；
- 不依赖增加 NATS timeout、连接数、Stream 或服务端资源才能通过验收。

### 16.7 瞬时 1000/2500/5000 压测

所有六组主矩阵都必须满足：

- 进程无 OOM、崩溃、非预期重启、事件循环永久失去响应或连接风暴；
- 每个 Run/API 提交都有明确返回分类，分类总数等于提交数，HTTP 5xx 和无响应 timeout 为 0；
- accepted 的 Run 最终有且只有一个终态；busy/retryable 使用相同 task ID 重试后最多执行一次；
- 目标任务总数等于 completed + 明确取消/失败数，无静默丢失、重复执行或无界残留；
- `100/30/30` 时 active 总数不超过 160，并在持续 backlog 下收敛到正式份额；
- `100/20/20` 第一阶段 active 不超过 140、20 个槽保持真实空闲；追加 20 个 configuration 后可借到
  `120/20/20=160`；
- `MAX_ACTIVE_RUNS`、各 capacity group、编码 worker、encoded bytes、发布队列和 JS 双窗口均不超过
  配置硬上限；
- event-loop lag p99 `<1s`，不得再出现接近 Core NATS flush timeout 的约 10 秒延迟；
- CPU、RSS、线程、FD、Redis连接、pending Task 和队列深度在排空后回到稳定基线，不随三次重复线性增长；
- 全 no-response 用例的普通 metrics、credential NATS 和普通结果 Core flush 均为 0；
- 正常网络下成功结果 PubAck timeout/reject 为 0，control RPC 在 metrics 高峰保持可用；
- 慢 PubAck/断连故障注入下所有队列仍有界、control 不被占用，恢复后可以继续排空。

结果报告必须逐组列出原始指标、失败样本和环境 CPU/memory/NATS/Redis 配置；不能只给平均值或一句
“5000 任务通过”。任一硬不变量失败即判定该组合不通过，再根据瓶颈调整 capacity group 或编码/JS
预算后重测，不能通过增加 timeout 掩盖。

## 17. 可观测性

新增或保留：

```text
stargazer_scheduler_active_targets{workload_class}
stargazer_scheduler_pending_targets{workload_class}
stargazer_scheduler_borrowed_slots{workload_class}
stargazer_scheduler_rebalance_wait_seconds
stargazer_scheduler_first_dispatch_wait_seconds
stargazer_scheduler_slot_release_dispatch_seconds{workload_class}
stargazer_submission_total{status}
stargazer_submission_duration_seconds
stargazer_active_runs
stargazer_run_admission_busy_total
stargazer_capacity_group_active{capacity_group}
stargazer_capacity_group_pending{capacity_group}
stargazer_capacity_group_limit{capacity_group}
stargazer_event_loop_lag_seconds
stargazer_event_loop_lag_p99_seconds
stargazer_metrics_encode_active
stargazer_metrics_encode_queue_depth
stargazer_metrics_encode_duration_seconds
stargazer_metrics_encoded_pending_bytes
stargazer_metrics_encoded_pending_bytes_peak
stargazer_collection_credential_cooldown_total
stargazer_collection_credential_state_redis_error_total
nats_metrics_pending_bytes
nats_js_publish_pending_messages
nats_js_publish_pending_bytes
nats_js_puback_duration_seconds_p99
nats_js_puback_timeout_total
stargazer_control_request_duration_seconds
stargazer_control_publish_total{protocol}
```

删除或废弃：

```text
credential_result_publish_total
credential_result_publish_failed
credential_result_event_stream_depth
credential_result_push_cursor
```

运行日志需要能按 `task_id`、`workload_class`、`plugin_ref` 和终态错误码关联，但不得输出凭据正文。

## 18. 预期效果

- 最大在途目标从 250 降为 160，峰值下降 36%；
- 三类任务竞争时有稳定份额，空闲时不浪费容量；
- workload 公平与技术资源容量同时准入，避免 160 个目标占槽等待线程池或插件内部 fan-out 绕过上限；
- 全失败 Run 对普通结果 NATS 的消息和 flush 压力归零；
- credential/control 共享连接造成的失败放大器被删除；
- 失败不再占用 metrics结果队列、JetStream窗口和VictoriaMetrics容量；
- 成功结果编码与同步 SDK 隔离，编码并发、已编码字节和 JetStream pending 都具有独立硬上限；
- Redis 只提供冷冻和亲和，不承担逐尝试结果事件总线或跨服务投影；
- 失败日志从逐目标 traceback 收敛为有界Run汇总；
- metrics连接只承载有效成功数据且生产不回退 Core NATS，control连接只承载固定的必要控制协议；
- 不需要新增NATS基础设施或底层依赖。

## 19. 确认清单

实施前请确认以下内容：

- [x] 同意本方案替代 credential JetStream 方案；
- [x] 同意 configuration/monitoring 失败均不推送普通采集指标或 NATS 结果事件；
- [x] 同意 Run 汇总只写本地日志；
- [x] 同意保留本地 Redis 凭据冷冻和成功亲和；
- [x] 同意完整保留 `api.collect.collect` 的单凭据/多凭据入站、顺序轮换、成功即停和 SNMP 混合凭据能力；
- [x] 同意补齐 `scope_id=collect_task_id`、任务兼容 epoch 和每凭据 revision，精确修复跨任务隔离与凭据编辑失效缺口；
- [x] 同意单进程 `160` 和竞争份额 `100/30/30`，空闲可互借；
- [x] 同意 monitoring 只由 `api/monitor.py` 可信入口识别；
- [x] 同意 callback/deferred 作为显式控制协议继续保留；
- [x] 确认 `cmdb_round_complete` 仅在存在成功数据且成功数据已确认时保留；全失败不发送；
- [x] 确认删除 `/collect/credential_results`、Redis 结果事件流及 CMDB HTTP 投影同步；
- [x] 确认 `CollectTaskCredentialHit` 暂时只保留给配置文件 Server 直执行链路；
- [x] 确认扫描一枪 `receive_scan_credential_result` 独立保留；
- [x] 确认 Stargazer Redis 是多凭据运行时亲和/冷冻的唯一权威；
- [x] 接受 160 为单进程上限，多进程/多 Pod 总量不由本方案做分布式限制；
- [x] 同意生产 metrics 使用 JetStream-only，不允许静默回退 Core NATS；
- [x] 同意 control 收口为 request/callback/deferred typed Interface，不再承载普通业务批量；
- [x] 同意四层容量模型：业务公平、技术资源、成功结果编码、JetStream 传输分别限流；
- [x] 同意 `capacity_group` 真实准入和插件内部线程池/fan-out 分阶段接入共享资源 Module；
- [x] 同意 metrics 使用专用编码执行器，初始 worker=2，消息/字节预算以生产压测锁定；
- [x] 同意非抢占借槽债务，并以槽释放后的派发延迟而不是绝对首派时间作为调度器硬 SLO。
- [x] 同意增加瞬时 1000/2500/5000 的 Run/API 与目标任务两层压测；
- [x] 同意分别验证 100/30/30 和 100/20/20，其中后者保持生产全局 160，并验证 20 空闲槽及后续借用。

## 20. 2026-09-01 实施记录

本方案已按确认口径进入代码：

- 普通失败、不可达和空成功结果不进入结果发布队列，不产生 metrics/credential NATS；
- configuration 与 monitoring 分别由 `api/collect.py`、`api/monitor.py` 标注可信 workload；
- 调度器使用全局 160、正式竞争权重 100/30/30、空闲借槽和非抢占归还，并在创建目标 Task 前检查
  `snmp/sync_sdk/remote_job/default` 技术容量；
- metrics 生产默认 JetStream-only，使用独立连接、专用 2 线程编码执行器、160 成功结果入口、
  256 messages/32 MiB PubAck 双窗口；生产装配关闭 JetStream 时直接拒绝启动，不存在 Core fallback
  配置；
- credential 普通结果 push service、handler、subject、Redis 事件流和 HTTP 查询均已删除；冷冻/亲和仍由
  Stargazer Redis 权威状态维护：候选读取使用一次 `MGET`，失败使用 `SET EX`，成功使用两键 Lua 原子
  更新亲和并只清除当前成功凭据的失败状态；
- 逐凭据的冷冻和冷冻跳过只写 DEBUG 诊断日志，避免失败风暴把 NATS 压力转移为 INFO 日志 I/O；Run
  终态仍使用一条有界 INFO 汇总，日志不包含凭据正文；
- Server 不再定时拉取或保存 Stargazer 凭据状态；未发布的投影服务、模型字段、cursor 和 migration
  均已删除，现有 `CollectTaskCredentialHit` 只留给暂缓的配置文件直执行链路；
- 多凭据保留稳定顺序、认证失败后继续、成功即停、下一轮成功亲和、冷冻跳过、SNMP 混合版本；
  `scope_id=collect_task_id` 隔离任务，每条凭据内容编辑只递增自己的 `credential_version`。

新增 `agents/stargazer/scripts/benchmark_collection_burst.py`：`scheduler` 模式可直接执行六组目标突发
矩阵，`api` 模式连接隔离压测环境执行真实 1000/2500/5000 HTTP 瞬时提交并对所有响应分类对账。

本机调度 seam 已执行 1000/2500/5000 × 两种形态 × 三轮，共 18 组，全部通过：峰值 active 均为
160；100/30/30 稳定收敛；100/20/20 第一阶段空闲 20，追加 configuration 后达到 120/20/20；
最新一轮 18 组中事件循环 lag p99 最大 19.622 ms。模拟 1 ms PubAck 的 5000 成功小结果发布验证中，结果队列
峰值 160、JS pending 峰值 200 messages/73,842 bytes、5000 条全部确认、timeout/retry/reject 均为 0、
事件循环 lag p99 为 95.300 ms。

定向回归结果以本节后续最新验证记录为准；必须至少覆盖 Stargazer 发布/调度/多凭据/Redis/NATS、
Server 凭据池/节点下发/配置文件直执行状态、扫描凭据协议，以及 Django migration 状态检查。

最新定向验证：Stargazer 发布、控制通道、执行器、凭据策略、Redis 与端到端用例 `157 passed, 1 skipped`；
收紧空成功轮次后，轮次完成标记、端到端与结果发布边界追加验证 `43 passed, 1 skipped`；
Server 凭据池、节点下发、配置文件直执行状态、投影删除和扫描凭据协议 `26 passed`；
`manage.py makemigrations --check --dry-run` 返回 `No changes detected`，本方案没有新增或待部署的数据库
migration；相关 Python 文件通过 Black、isort、排除仓库既有 Black 冲突项后的 flake8，以及
`git diff --check`。

已知测试基线：`agents/stargazer/tests/test_collect_multicred.py` 仍有 20 项历史用例直接依赖已删除的
`TaskQueue`、旧任务展开函数和旧 plugin handler（同文件其余 23 项通过）。本次没有通过恢复旧架构、
跳过或批量删除这些用例制造全绿；当前多凭据执行不变量由 `test_target_collection_executor.py`、
`test_credential_policy.py`、`test_redis_collection_state.py`、`test_collection_request_builder.py` 以及
Server 凭据池/下发/扫描测试锁定。旧文件应在后续测试基线治理中迁移或删除重复的实现细节断言。

以上数据只证明本机调度和模拟 PubAck seam，不冒充生产等价结论。真实 Run/API、Redis、TLS NATS
JetStream、control RPC 并行和断连恢复矩阵仍须在隔离的生产等价环境执行 `--mode api` 与真实
JetStream benchmark，按第 15.8、16.7 节保存原始报告后才能作为上线容量签字证据。

### 20.1 日志复盘后的非配置文件链路加固

再次对照 2026-08-31 故障日志和当前实现后，补充完成以下修复；配置文件 callback/control-rpc
链路按产品决定继续暂缓，本节不改变其协议：

- JetStream 消息数与字节额度移到 `create_task()` 前获取，额度跨单条消息的有限重试持有；多个
  result publisher worker 共享一个真实全局窗口，不再产生 `4 × 256` 隐藏 PubAck Task；
- 新增 waiting messages/bytes 及峰值指标，与真正 in-flight pending 分开观测；
- metrics readiness 除连接状态外，验证 `NATS_JS_STREAM_NAME` 存在且 Stream subjects 覆盖动态
  `metrics.<task_type>`；subscriber 连接也进入 readiness；
- metrics nats-py 重连缓冲默认不小于 32 MiB JetStream 字节窗口，并为协议开销保留 1 MiB；
- `NATS_USERNAME/NATS_PASSWORD` 成为正式显式认证配置，URL 内嵌凭据只作向后兼容；subscriber、
  metrics、control 默认无限重连，连接日志带稳定 `channel`；退出 drain 具有 5 秒上界；
- 官方 `nats-py v2.15.0` 仍未保护晚到 PONG 对已取消 Future 的 `set_result()`；因此不做无效依赖
  升级，在统一 NATS Adapter 内忽略已完成 Future，同时保留 PONG 计数和连接状态；
- SNMP 逐目标开始和 metrics 微批成功降为 DEBUG；插件异常详情由一个 Run 共享最多 3 条采样
  预算，终态失败计数与有界样本仍由 `collection_run_summary` 持有。
