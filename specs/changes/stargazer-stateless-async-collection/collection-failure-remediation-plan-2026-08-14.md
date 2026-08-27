# Stargazer 大批量采集失败治理方案

更新日期：2026-08-14
适用变更：`stargazer-stateless-async-collection`
状态：**Implemented / 已确认并在当前分支实施，待部署验证**

> 本文已于 2026-08-14 获用户确认并授权实施。代码、测试、插件 YAML 与运行说明已按本文更新；
> 生产部署参数仍须随镜像发布生效。

## 1. 背景与目标

客户约有 3000 台网络设备，同时下发十多个采集任务。采集日志显示大量设备未完成采集，主要风险集中在：

1. 请求 `params.ip_precheck=false` 时只跳过部分网络短探测，插件 `probe()` 仍然执行；
2. 预检/探测、正式采集和结果发布的超时语义混杂；
3. 单个 Run 可以长时间持有大量 worker，造成跨任务饥饿；
4. 单台设备 NATS 发布失败会抛出到 `gather()`，进而取消同 Run 剩余设备；
5. 当前默认目标并发为 2000，同步 SDK 仍通过线程执行时容易形成大量排队和超时。

本方案的目标是：

- 关闭 IP 预检时，直接进入插件正式采集；
- 单台设备失败不扩大为整批任务取消；
- 只使用现有三个全局并发参数，在插件全面异步化前先降低并发；
- 多个 Run 公平共享全局目标执行能力；
- 结果发布有界、有背压、可批量 flush；
- 四类超时职责清晰，正式采集预算由任务表单 `timeout` 决定；
- 通过 3000 台级别压测证明不会出现任务取消、无界排队和跨任务饥饿。

## 2. 已确认的产品与架构决策

以下决策已确认，后续实施不得自行偏离：

1. 关闭预检代表关闭所有采集前探测，但不关闭出站安全检查。
2. 只保留 `MAX_ACTIVE_RUNS`、`MAX_ACTIVE_TARGETS`、`TARGET_TASK_WINDOW` 三个并发参数；本阶段不增加 SNMP、同步 SDK、remote/job 等独立并发配置。
3. 插件的 `execution_mode` 和 `capacity_group` 写入 YAML，不在框架中硬编码插件名称。
4. `capacity_group` 本阶段只用于分类、日志、指标和未来扩展，不参与独立限流。
5. 调度器跨 Run 公平调度，任何 Run 都不得预占一批 worker。
6. SNMP 底层全面异步化后，通过 YAML 把 `execution_mode` 改为 `async`，再根据压测逐步放大现有全局并发值。
7. 正式采集预算从任务表单 `timeout` 读取，缺失时为 60 秒；SNMP 小于 30 秒时兼容钳制为 30 秒。
8. 发布采用内存有界队列和批量 flush，暂时不做磁盘持久队列。
9. 单台设备发布失败只影响该设备，Run 汇总为 `completed_with_errors`，不得取消剩余设备。
10. `PREFLIGHT_TIMEOUT` 和 `PROBE_TIMEOUT` 默认均为 15 秒。
11. 配置采集运行时在插件到 Publisher 之间保留结构化结果，由 Publisher 直接编码 Influx Line
    Protocol；旧的直接调用接口继续返回 Prometheus 文本，避免破坏兼容性。

## 3. 总体执行流程

```text
HTTP 请求
  → Run 准入（MAX_ACTIVE_RUNS）
  → 薄租约
  → 将 Run 注册到全局公平调度器
  → 调度器按 Run 轮询选择目标
  → 全局目标准入（MAX_ACTIVE_TARGETS）
  → 出站安全检查（始终执行）
  → 根据 request.params.ip_precheck 决定是否执行预检/探测
  → 正式 collect（任务表单 timeout，缺省 60s；SNMP 最小 30s）
  → 写入有界发布队列（容量复用 TARGET_TASK_WINDOW）
  → Publisher 批量 publish + flush
  → 记录目标采集状态与发布状态
  → 汇总 Run：completed / completed_with_errors
```

三个需要集中复杂性的深模块及其 seam：

| 模块 | 对外 interface | 隐藏的实现复杂性 |
| --- | --- | --- |
| `ExecutionPlan` | 给定请求和插件配置，返回不可变执行计划 | 四类超时、YAML 缺省值、执行模式与容量分类；不复制任务级开关 |
| `CollectionScheduler` | 注册 Run、产出可执行目标、回收目标槽位 | 跨 Run 公平性、全局并发、窗口背压、取消与关闭 |
| `ResultPublishQueue` / `ResultSink` | 入队回执与最终投递分别建模 | 有界队列、批量 flush、有限重试、失败隔离、结果不确定性 |

调用方只依赖上述 interface，不直接操作 semaphore、worker 预算、NATS flush 或超时优先级。

## 4. P0：正确性修复

### 4.1 关闭预检时跳过全部采集前探测

统一使用单次请求参数 `params.ip_precheck`，不设全局环境开关。

当请求参数未开启时，必须跳过：

- TargetPolicy 中的 TCP/TLS/端口可达性检查；
- SNMP `probe()`；
- 数据库、VMware、云端点等插件的 `probe()`；
- SSH/remote/job responder 的采集前探测；
- 当前和未来所有实现 `AccessProbe` 的插件探测。

关闭后的执行顺序：

```text
安全检查 → 凭据选择 → 直接 collect
```

以下检查无论开关状态都必须保留，因为它们属于安全策略，不属于可达性预检：

- 目标地址和端口是否在允许范围；
- 回环、保留地址和 SSRF 防护；
- 凭据作用域校验；
- 出站访问策略。

当 `params.ip_precheck` 显式为真值时：

```text
安全检查 → TargetPolicy 预检 → 插件 probe（若支持）→ collect
```

禁止再通过“插件是否有 `probe()`”单独绕过总开关。

`params.ip_precheck` 是唯一事实来源；不设置 `PREFLIGHT_REACHABILITY` 等全局回退。SNMP/UDP
在无凭据层不发送裸 UDP 包，只做出站安全检查，随后由带凭据的最小协议 probe 判断。

### 4.2 单设备发布失败隔离

每台设备分别维护两类结果：

- `collection_status`：`succeeded | failed | unreachable | deferred`；
- `publish_status`：`succeeded | failed | unknown`。

规则：

1. 设备 A 发布失败后，记录 A 的 `publish_status=failed/unknown`；
2. A 的异常不得逃逸到负责整个 Run 的 `gather()` 或调度循环；
3. B、C、D 等剩余目标继续采集和发布；
4. 发布失败不能把已经成功的采集结果改写成“采集失败”；
5. Run 存在任一采集失败、发布失败或发布状态不确定时，最终状态为 `completed_with_errors`；
6. 只有运行时自身不可恢复故障、租约失效或主动关闭等 Run 级异常才允许标记 Run `failed/cancelled`。

Run 汇总至少包含：

```text
total
collection_succeeded
collection_failed
unreachable
deferred
publish_succeeded
publish_failed
publish_unknown
```

### 4.3 发布重试与幂等语义

- 发布重试只保留一层，默认总尝试次数仍为 2 次；
- `collection_result_id` 作为单目标结果的稳定幂等键；
- 明确未发送时允许有限重试；
- 已确认成功时不得重复发送；
- 连接中断等无法确认服务端是否收到的情况记为 `publish_unknown`；没有下游去重保证前不得盲目无限重发；
- 本阶段不引入磁盘 spool，进程崩溃时尚未发布的内存结果依赖下一采集周期补偿。

## 5. P1：全局并发、公平调度和背压

### 5.1 只保留三个现有参数

不增加以下一类配置：

```text
SNMP_MAX_CONCURRENCY
SYNC_SDK_MAX_CONCURRENCY
REMOTE_JOB_MAX_CONCURRENCY
```

三个现有参数的最终语义：

| 参数 | 最终语义 |
| --- | --- |
| `MAX_ACTIVE_RUNS` | 单 Pod 已准入且尚未结束的 Run 上限 |
| `MAX_ACTIVE_TARGETS` | 单 Pod 已获调度、正在执行目标流程的总数上限 |
| `TARGET_TASK_WINDOW` | 单 Pod 已物化但尚未派发的目标工作项上限；同一数值同时作为发布队列容量 |

`0=不限制` 的兼容语义可以保留，但生产环境禁止配置为 0；启动日志应明确告警。

### 5.2 同步插件过渡期建议值

第一阶段建议部署值：

```env
MAX_ACTIVE_RUNS=16
MAX_ACTIVE_TARGETS=150
TARGET_TASK_WINDOW=150
```

理由：

- 客户会同时下发十多个任务，`MAX_ACTIVE_RUNS` 暂时保持 16，避免入口直接拒绝正常任务；
- `MAX_ACTIVE_TARGETS` 从 2000 降到 150，限制同步 SDK、SNMP engine、连接数、Redis 和 NATS 的瞬时压力；
- `TARGET_TASK_WINDOW=150` 限制已物化工作和发布队列规模，不允许把数千台设备全部创建成协程；
- 150/150 是当前实机压测候选值，不是长期性能上限；后续优化 SNMP engine 生命周期并完成压测后，只调整这三个现有值。

调整原则：

1. 先观测事件循环延迟、CPU、内存、线程数、NATS flush 延迟、目标 P95/P99 耗时；
2. 每次只增加一个档位，例如目标并发 `100 → 150 → 200`；
3. 任一容量指标明显恶化或失败率上升时回退上一档；
4. 不以“协程数量能创建成功”作为容量通过标准。

### 5.3 跨 Run 公平调度

当前“Run 一次 reserve 多个 worker，直到整个 Run 结束才 release”的方式必须删除。

建议调度语义：

1. 每个 Run 只向调度器暴露尚未处理目标的迭代器；
2. 调度器在活跃 Run 之间 round-robin，每轮每个 Run 最多派发一个目标；
3. 只有拿到全局目标槽位后才创建实际执行任务；
4. 单目标在采集流程结束并将发布请求交给有界队列后，立即释放目标槽位；
5. 单个 Run 不拥有固定 worker 配额，也不能长期持有一批空闲 worker；
6. 新到达的小任务必须在已有大任务持续执行时获得调度机会；
7. Run 取消或租约失效时，只移除该 Run 尚未派发的目标，不影响其他 Run。

公平性验收要求：

- 一个 3000 台的大 Run 执行期间新提交 10 台的小 Run，小 Run 不能等大 Run 完成后才开始；
- 16 个活跃 Run 下，每个仍有待处理目标的 Run 都必须持续获得调度机会；
- 不允许任何 Run 预占 `MAX_ACTIVE_TARGETS` 的全部槽位。

### 5.4 同步到异步的过渡约束

本阶段不建设按插件拆分的线程池或独立容量组限流。为避免同步 SDK 在默认线程池中无界堆积：

- 全局目标并发先从 2000 降到 150；
- 调度排队发生在超时计时之前；
- 不允许提前为全部目标调用 `to_thread()`；
- 插件内部仍必须配置真实 socket/read/SDK timeout；
- 外层协程取消不等于阻塞线程已经停止，监控必须包含残留线程和实际在途调用数量。

如果在 SNMP 全异步改造完成前的压测中仍证明线程池排队吞噬探测超时，则暂停放大并发，优先完成异步插件改造；不在本方案中临时增加新的插件级并发参数。

### 5.5 YAML 执行元数据

每个 executor 增加：

```yaml
executors:
  protocol:
    type: protocol
    timeout: 60
    execution_mode: sync
    capacity_group: snmp
```

允许值：

```text
execution_mode: sync | async | remote
capacity_group: snmp | sync_sdk | remote_job | default
```

本阶段：

- `execution_mode` 用于执行计划、日志、指标和阻塞调用审计；
- `capacity_group` 用于分类指标和未来扩展；
- 两者都不产生新的独立并发上限；
- 框架不得根据插件名称、目录名或 collector 类名推断分类；
- 未声明字段的旧 YAML 在兼容期按保守模式处理，并记录一次告警；
- 实施时应补齐仓库内全部插件 YAML，兼容缺省只用于外置/旧插件。

SNMP 改为全异步后：

```yaml
execution_mode: async
capacity_group: snmp
```

`capacity_group` 可以继续保留，用于比较 SNMP 与其他插件的吞吐和失败率。

## 6. P1：有界结果发布

### 6.1 发布队列

`BufferedResultPublisher` 作为 `ResultPublishQueue` 使用内存有界队列，内部通过 `ResultSink`
执行最终投递：

- 队列容量复用 `TARGET_TASK_WINDOW`，不增加新的容量环境变量；
- 采集 worker 提交结果时获得一个完成句柄；结果被队列接受后释放目标槽位，由 Run 的结果账本异步等待该句柄，不继续占用 active target；
- 队列满时产生背压，等待时间计入 `PUBLISH_TIMEOUT`；
- 超时只标记当前目标发布失败，不取消 Run；
- shutdown 时在 grace period 内排空队列，超时后将未完成项记为发布失败/不确定。

### 6.2 批量 publish 与 flush

- 一个或少量 writer 从队列取出小批结果；
- 逐条调用 NATS publish，但同一批只执行一次 flush；
- flush 成功后完成该批结果的发布句柄；
- flush 明确失败时，该批各目标独立记录发布失败；
- 结果不确定时记为 `publish_unknown`；
- NATS 连续失败时允许短期熔断，熔断只快速失败发布，不阻断后续采集调度。

批大小和聚合等待时间属于内部实现细节，先通过压测确定，不新增部署容量参数。必须保证低流量时不会因为等待凑批而明显增加单目标延迟。

## 7. P2：四类超时

### 7.1 定义与默认值

| 配置 | 默认值 | 计时范围 |
| --- | ---: | --- |
| `PREFLIGHT_TIMEOUT` | 15s | TargetPolicy TCP/TLS/端口等可达性预检 |
| `PROBE_TIMEOUT` | 15s | 插件 `probe()` / AccessProbe |
| `COLLECTION_TIMEOUT` | 60s | 正式插件 `collect()` 的全局缺省值 |
| `PUBLISH_TIMEOUT` | 30s | 提交发布队列、队列等待、publish 和 flush 确认的端到端阶段 |

规则：

- 调度器等待全局目标槽位的时间不计入上述阶段超时；
- 每个阶段独立计时，一个阶段的剩余时间不得传递给下一阶段；
- `params.ip_precheck` 未开启时不执行可选连通性 preflight 和 probe，因此前两项不计时；
- `RUN_DEADLINE` 仍是可选 Run 总截止时间，包含调度等待；`0` 表示关闭；
- 所有超时必须为大于 0 的有限数值，非法配置在启动/插件加载时失败并给出明确字段名。

### 7.2 配置优先级与兼容

```text
preflight：
YAML target_policy.timeout
→ PREFLIGHT_TIMEOUT
→ 兼容期 CONNECT_TIMEOUT
→ 15s

probe：
YAML executor.probe_timeout
→ PROBE_TIMEOUT
→ 兼容期 CONNECT_TIMEOUT
→ 15s

collection：
任务表单 timeout
→ COLLECTION_TIMEOUT
→ 兼容期 PLUGIN_TIMEOUT
→ 60s

publish：
PUBLISH_TIMEOUT
→ 30s
```

兼容策略：

- 新配置优先；
- `CONNECT_TIMEOUT`、`PLUGIN_TIMEOUT` 只作为一个发布周期的兼容回退；
- 使用旧变量时启动日志只打印一次废弃告警；
- 完成部署迁移后再单独确认删除旧变量，不在本次直接破坏兼容。

### 7.3 正式采集预算来自任务表单

解析规则：

1. 表单传入合法正数：作为单目标正式 Collector 采集预算；
2. 表单缺失、空值或 0：使用 `COLLECTION_TIMEOUT`，默认 60 秒；
3. 通用任务钳制到 1～86400 秒，SNMP 任务额外保证最小 30 秒；
4. 插件 YAML executor 的旧 `timeout` 字段不再覆盖任务表单预算；
5. SNMP 内部 `timeout=10s`、`retries=1` 保持不变，外层 30 秒最小预算容纳其重试窗口；
6. 其他 SDK 内部网络超时应小于或等于外层 collection timeout，避免外层返回后后台线程仍长期阻塞。

## 8. 状态、错误和可观测性

### 8.1 Run 状态

| 条件 | Run 状态 |
| --- | --- |
| 所有已调度目标采集和发布均成功 | `completed` |
| 任一目标采集失败、不可达、发布失败或发布状态不确定 | `completed_with_errors` |
| Run 自身不可恢复异常、租约丢失或关闭取消 | `failed` / `cancelled` |

HTTP 已接受的 Run 不应因为一个目标异常改变为整轮取消。

### 8.2 必须补充的指标

- 当前/峰值 active runs、active targets、target window；
- 每个 Run 首次获得调度的等待时间；
- 各 Run 已调度/待调度目标数；
- `execution_mode`、`capacity_group` 维度的执行量、成功率和 P95/P99；
- preflight、probe、collection、publish 四阶段耗时和超时数；
- 发布队列深度、队列等待、批大小、flush 耗时；
- `publish_succeeded/failed/unknown`；
- NATS 重试、熔断打开次数；
- 事件循环 lag、线程数和同步阻塞调用在途数。

日志必须包含 `task_id`、`target`、`plugin_ref`、`collection_result_id`、阶段、最终错误码，且不得记录凭据。

## 9. 实施切片（获确认后执行）

实施采用测试先行，每个切片独立通过后再进入下一切片：

### Slice A：预检总开关

- 先写覆盖不同插件类型的失败测试；
- `off` 时禁止调用 TargetPolicy 可达性探测和所有插件 `probe()`；
- 验证出站安全拒绝仍然生效；
- 请求显式开启时保持预检与 probe 正常工作。

### Slice B：发布失败隔离

- 先证明当前单目标发布异常会取消兄弟目标；
- 修改目标结果和 RunSummary 契约；
- 发布异常转换为目标级发布状态；
- 验证后续目标继续执行，Run 为 `completed_with_errors`。

### Slice C：ExecutionPlan 与四类超时

- 从环境变量、任务表单和 YAML 元数据一次解析不可变执行计划；
- 增加四类超时与旧变量兼容；
- 正式采集读取任务表单 `timeout`；
- 补齐 YAML 的 `execution_mode`、`capacity_group` 和目标策略。

### Slice D：公平调度与低并发默认值

- 删除 Run 级 worker 预占；
- 引入全局 round-robin 调度；
- 目标完成即释放槽位；
- 默认部署建议改为 16/150/150；
- 增加跨 Run 公平性、取消、关闭和窗口测试。

### Slice E：有界批量发布

- 引入复用 `TARGET_TASK_WINDOW` 的发布队列；
- 批量 flush、有限重试和短期熔断；
- 覆盖队列满、NATS 延迟、明确失败和不确定结果；
- 验证发布故障不会降低采集调度器可用性。

### Slice F：压测、文档和部署

- 运行固定单元、集成和契约测试；
- 完成 3000～10000 台 mock 压测；
- 在允许的测试环境完成真实 SNMP 分档压测；
- 更新 `spec.md`、README、环境变量和运维说明；
- 给出推荐生产值、扩容阈值和回滚方式后再部署。

## 10. 验收标准

### 正确性

- 预检关闭后所有类型的 `probe()` 调用次数为 0；
- 出站安全校验在预检关闭时仍能拒绝非法目标；
- 任意一台设备 NATS 发布失败不会取消其他目标；
- 发布失败的 Run 最终为 `completed_with_errors`；
- YAML 未配置 collection timeout 时为 60 秒，配置后使用 YAML 值；
- preflight 和 probe 默认超时均为 15 秒，且二者互不覆盖。

### 容量与公平性

- 任意时刻 active targets 不超过 `MAX_ACTIVE_TARGETS`；
- 已物化但尚未派发的目标工作项不超过 `TARGET_TASK_WINDOW`；
- 发布队列深度不超过 `TARGET_TASK_WINDOW`；
- 16 个 Run 并发时无 Run 长期拿不到调度；
- 3000 台大 Run 期间提交小 Run，小 Run 可及时开始；
- 不为 3000 台目标一次性创建 3000 个任务；
- NATS 变慢时发布队列有界，内存不随目标数持续增长。

### 稳定性

- 3000 台、十多个 Run 的整轮执行中不存在单目标异常导致整轮取消；
- 模拟大量超时、错误凭据和 NATS 故障后，事件循环仍可响应健康检查；
- shutdown 可在 grace period 内停止接收新工作并尽量排空已接收发布项；
- 压测报告包含吞吐、成功率、阶段超时、P95/P99、CPU、内存、线程数、事件循环 lag 和发布队列峰值。

## 11. 回滚方案

各切片保持可独立回滚：

- 预检开关异常时可临时设为 `on`，但不得关闭出站安全检查；
- 公平调度器上线前保留一次发布周期的旧调度回滚路径，不长期双轨；
- 批量发布异常时可退回逐条发布，但必须保留“目标级失败隔离”；
- 新超时变量异常时可通过兼容期旧变量回退；
- 并发值通过部署配置回退，优先回退到 16/150/150；若压测证明事件循环延迟仍不可接受，可回退到 16/100/100；
- 数据契约如新增字段必须保持下游对旧字段的兼容，回滚不得造成结果无法解析。

## 12. 已确认的生产过渡值

除以下一项数值建议外，其余方案已按讨论结论写定：

```env
MAX_ACTIVE_RUNS=16
MAX_ACTIVE_TARGETS=150
TARGET_TASK_WINDOW=150
```

上述值已获确认并写入代码默认值与 README。Redis 连接池保持既有
`REDIS_MAX_CONNECTIONS=2560`、`REDIS_POOL_TIMEOUT=2`，本次未缩小。

## 13. 实施与验证记录

- 已实现关闭预检时跳过所有 AccessProbe/remote responder 探测，并保留出站安全策略；
- 已实现目标级发布失败/不确定状态隔离和 `completed_with_errors`；
- 已实现 `ExecutionPlan`、四类超时及旧变量兼容；
- 已实现跨 Run round-robin 公平调度，默认容量为 16/150/150；
- 已实现容量 150 的内存发布队列、目标结果批处理及同 subject 批量 flush；
- 已为 57 份插件 YAML 补充 `execution_mode`、`capacity_group`，全部 YAML 解析成功；
- 2026-08-14 原生异步插件合入后复核：`network`、`network_topo`、MySQL、PostgreSQL、
  Oracle、InfluxDB、FusionInsight、OceanStor 的 protocol executor 已标记为 `async`；MSSQL 仍为
  `sync_sdk`，通过同步适配路径隔离；
- 发布器新增 `enqueue → receipt` interface：队列接收结果后释放目标调度槽位，Run 账本继续等待
  最终发布结果，队列满时仍保持有界背压；
- 批量发布按 `collection_result_id` 返回逐目标结果；转换失败和 subject 级发布失败不再抛出并
  取消其他 subject，失败目标进入 `failed/unknown` 汇总；
- 配置采集运行时新增结构化指标载荷，Publisher 直接生成既有 Influx Line Protocol，避免
  `dict → Prometheus 文本 → Influx` 往返解析；旧入口仍返回 Prometheus 文本；
- 未预期的单目标框架异常收敛为 `target_execution_error`，不取消同 Run 其他目标；
- 生产路径由 `CollectionScheduler` 统一执行目标准入，不再叠加第二套 semaphore/worker budget；
- 增加采集、入队、发布 P95/P99、线程数、文件描述符和目标框架异常指标；
- SNMP GET/GETNEXT/GETBULK 的 engine transport dispatcher 在成功、异常和取消路径显式关闭；
- 本轮核心采集、调度、发布、SNMP 与兼容性回归：119 passed；E2E 回归：6 passed、1 skipped；
  SNMP 256 目标超时
  压测首次受本机调度抖动超过 200ms，独立重跑通过，256/256 结果均发布；
- 3000 目标容量门禁使用当前 150 上限，目标仅在获得槽位后从迭代器取出并创建 Task；
- 全仓 `pytest` 仍被任务外历史测试的缺失模块阻断：`home_application`、`core.task_queue`、
  `core.nats`，以及 collect fixture 中未注册的 mssql 基线；
- 本轮改动文件 Black、isort、Flake8 检查以最终交付时的新鲜命令结果为准。

### 13.1 2026-08-14 复审修复补充

- 保持 `MAX_ACTIVE_RUNS=16`、`MAX_ACTIVE_TARGETS=150`、`TARGET_TASK_WINDOW=150`，不调整
  Redis 连接池；
- 出站安全检查与可达性探测解耦：`skip`、SNMP/UDP 等非拨号模式也必须先通过
  `OutboundTargetPolicy`；逻辑云目标只接受 plugin YAML 声明并由框架标记可信的 SDK 域名后缀，
  外部请求不能注入该可信标记；非 TLS 目标把策略解析后的地址固定传给插件，DNS 返回允许与
  禁止地址混合时 fail-closed；
- NATS 重试只保留目标执行器一层，总尝试次数默认 2 次；底层 helper 单次发送并报告
  `delivery_detected`；
- 发布按单目标流式编码，再按指标行数和 UTF-8 字节数形成有界 flush；不再先汇总同 subject
  的全部目标，超大单行、编码失败和传输失败仅归因到对应目标；
- Publisher shutdown 复用应用级 grace deadline，超时后取消 writer 并把未确认回执标记为
  `publish_unknown`；
- 公平调度器不再把目标 Iterable 转为完整 tuple，只在获得全局槽位后消费下一个目标；
- 网络配置插件的连接关闭异常不再覆盖主采集结果；
- 补充调度等待、发布队列等待、批大小、flush、重试、shutdown 以及 execution mode / capacity
  group 的低基数指标，并增加待调度目标/Run、四阶段超时、发布行数和发布字节数；
- `PUBLISH_TIMEOUT` 重试复用首次入队生成的绝对 deadline，不因第二次尝试重新获得完整预算；
- IP 发现复用 `MAX_TARGETS_PER_RUN` 限制 CIDR 展开，探测与 ARP 查询共享固定 worker 边界；
- `.env.example` 已改为四类独立超时变量；兼容变量只保留在运行时代码的一个发布周期回退中；
- 当前树不包含真实 SNMP community；旧远端历史中的两个 community 必须由运维轮换，并在维护窗口
  评估历史清理，仓库修改不代替设备侧凭据轮换。
- 本轮固定采集、调度、发布、SNMP、VMware、Host Remote、执行元数据及异步契约回归：
  `201 passed, 1 skipped`；修复后关键聚焦回归：`132 passed`；
- 全量测试的剩余失败来自已删除的旧 task queue/worker 模块、collect fixture 的 MSSQL 基线、
  外部 SNMP 连通性及任务外 WMI 配置断言；真实 SNMP community 已改为环境变量注入。
