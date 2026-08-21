# APM 模块架构与代码结构分析

> 分析日期：2026-08-21
> 分析范围：`server/apps/apm/`，以及直接相连的 OpenTelemetry、NATS JetStream、VictoriaTraces、MinIO、SystemMgmt、Alerts 和 Celery/Beat 边界。
> 分析方式：按“遥测查询—目录与组织授权—策略评估—告警事实—证据与通知”完整模块分析，不以单个 tech-debt 或大文件为拆分依据。

## 1. 结论摘要

APM 不是一个 Trace 查询代理，而是遥测数据面的控制面和消费面：它维护 Application / Service / Instance 目录，把组织访问范围映射到遥测 identity，提供 Trace、Span、RED、拓扑和 SLO 查询，并运行策略、告警、证据快照及通知生命周期。

当前代码已有较好的“深模块”基础：`TelemetryStore` / `MetricStore` / `TraceStore` 隔离 VictoriaTraces 协议；Adapter 对查询窗口、响应大小、唯一 Span 和活动维度设有硬限制；策略以 target cursor、策略版本重检和确定性 Event key 裁决重复任务；EventSnapshot 与 Outbox 在领域事务中 staging；运行期健康探测覆盖 collector、NATS、JetStream、VictoriaTraces 和通知链路。这些都应保留。

结构性风险集中在四个不连续的协议边界：

- **授权在查询之后执行。** Trace/Span 列表先从 VictoriaTraces 分页，再过滤当前组织，导致空页、短页和游标语义错误；Trace 详情只要任意一个 Span 可见，就返回整条 Trace 的所有 Span，跨组织调用链可能泄露其他组织的服务和属性。
- **策略限制是字段上限，不是运行成本上限。** endpoints 与 versions 各允许 100，组合后一个策略最多 10,000 个目标并顺序查询；分钟级 dispatcher 没有 durable ScanRun、分区、补扫和共享 VictoriaTraces 预算。
- **worker lease 没有 fencing identity。** Outbox 只记录 `claimed_at`，过期 worker 可覆盖新 worker 的成功/失败结果；EventSnapshot 上传/删除在数据库行锁事务内执行外部 MinIO I/O，也没有 token 化 claim。
- **投影和快照存在热行与乘法放大。** Catalog 每分钟最多把 10,000 个活动维度逐条进入事务；Dashboard 每请求私建 8 线程并发最多 40 个 RED 查询；AlertMetricSnapshot 把每个成功窗口持续追加到同一无上限 JSON 列表。

短期不建议拆微服务。先在同一 Django app 内深化 `AuthorizedTelemetryScope`、`TelemetryQueryPlanner`、`PolicyScanRun/WorkItem`、`LifecycleReducer` 和 `EffectOutbox` 五个接口，把授权、成本、运行身份、状态裁决和副作用收敛为可审计协议。

## 2. 模块规模与职责边界

本次统计 APM 生产 Python 约 8,846 行（排除 migrations/tests），测试目录有 34 个 Python 文件。最大文件约 997 行，但文件尺寸只是查询、组织、策略、集成等多条变化轴汇聚的结果，不应直接按行数拆分。

| 能力域 | 当前实现 | 应拥有的事实 |
|---|---|---|
| 遥测接入 | OTel pipeline、Open Probe、integration 配置 | APM 只拥有接入期望和健康投影；Collector/JetStream 是运行事实 |
| 遥测查询 | contracts、VictoriaTraces adapter、Trace/Span/RED/Topology | 查询计划、范围摘要、成本和结果语义 |
| 服务目录 | Application、Service、Instance、Catalog reconciler | 规范化 identity、组织可见性、last_seen/archive 投影 |
| 策略运行 | Policy、TargetState、Beat/Celery | policy version、target cursor、ScanRun/WorkItem 结果 |
| 告警事实 | Alert、Event、MetricSnapshot、EventSnapshot | 生命周期事件和不可变窗口证据 |
| 副作用 | Outbox、MinIO payload、SystemMgmt/Alerts dispatch | 投递意图、claim token、attempt 和 outcome |

VictoriaTraces 应始终是 Trace/Span/RED 的事实源；APM 本地目录是身份与授权投影，不应复制遥测内容；MinIO 只保存不可变大对象，不应承担热 Alert JSON 的并发协调。

## 3. 现状架构图

- [APM 现状架构（Archify HTML）](./apm-current.architecture.html)
- [APM 现状架构规格](./apm-current.architecture.json)
- [APM 现状架构静态图](./apm-current.architecture.light.png)

三条主路径是：

```text
Instrumented Apps → OTel regional collector → NATS → system collector → VictoriaTraces

HTTP / Open Probe → Organization Access → Telemetry Query Port → VictoriaTraces

Beat → Policy Target Expansion → VictoriaTraces → TargetState / Alert / Event
                                           └→ EventSnapshot / Outbox → MinIO / SystemMgmt / Alerts
```

问题不是这三条路径存在，而是它们没有共享同一份授权 scope、查询成本、run identity 和 fencing token。

## 4. 应保留并深化的设计

### 4.1 遥测协议已被 Port 隔离

View 和领域服务依赖 query contract，VictoriaTraces 的 LogsQL、HTTP timeout、响应字节、时间窗口、唯一 Span 和维度限制集中在 Adapter。当前通用查询窗口上限 35 天、响应上限 8 MiB、唯一 Span 上限 1,000,000、活动维度上限 10,000，见 [victoriatraces.py:36](../../server/apps/apm/adapters/victoriatraces.py#L36)。

应继续把“支持什么查询”留在 contract，把“如何表达 VictoriaTraces 查询”留在 Adapter；不要让 View、Policy 或 Dashboard 拼协议字符串。

### 4.2 TargetState 与 Event identity 提供了可靠裁决点

策略查询后进入事务，再锁 Policy 和 TargetState，重检 `is_enabled`、`evaluation_cursor` 和 `policy.updated_at`；同一 cursor 不重复推进，策略修改后的旧结果被丢弃，见 [policies.py:216](../../server/apps/apm/services/policies.py#L216)。EventSnapshot 用 source event ID 幂等 staging，并把序列裁剪到 240 点、保留 90 天、最多重试 8 次，见 [snapshots.py:13](../../server/apps/apm/services/snapshots.py#L13)。

这些是目标架构中 `LifecycleReducer` 和不可变 `WindowEvidence` 的基础，不应退化成“Celery 基本只执行一次”的假设。

### 4.3 Outbox 已具备意图唯一性与人工审计

每个事件/渠道的 Outbox 唯一，保存 payload、attempt、退避、终止失败和人工重投信息；下游投递携带稳定 `delivery_key`。需要补的是 claim token 和条件更新，而不是推翻 Outbox。

### 4.4 依赖健康探测是运行期能力

APM 对区域/系统 Collector、NATS 发布、JetStream、VictoriaTraces retention/health 和通知 responder 做有界探测，故障只形成健康状态，不绑架 Server 启动。这个边界正确；后续 ScanRun、CatalogRun 和 Outbox lag 也应进入同一可观测面。

## 5. Trace/Span 查询与组织授权

### P0：任一 Span 可见会放行整条 Trace

Trace 详情先读取完整 Trace；`can_view_detail()` 收集全部 Span identity，只要 `any(...)` 可见就返回 true，View 随后序列化整条详情，见 [trace_access.py:83](../../server/apps/apm/services/trace_access.py#L83) 与 [traces.py:114](../../server/apps/apm/views/traces.py#L114)。分布式 Trace 横跨多个组织时，组织 A 因其中一个 Span 可见，可能看到组织 B 的 Span、服务 identity 和 attributes。字段 sanitizer 不能替代对象授权。

短期必须定义跨组织 Trace 的产品语义，并按 Span 过滤详情：可见 Span 保留；不可见节点替换为 opaque remote node；跨边显式标记 `scope_cut`；错误详情和 attributes 不跨范围返回。不要简单要求“整条 Trace 所有 Span 都属于当前组织”，否则正常跨域调用会不可用。

### P1：分页后过滤破坏列表和游标语义

Trace 列表先查询 store，再调用 `filter_summaries()`，但直接返回原始 `next_cursor`，见 [traces.py:73](../../server/apps/apm/views/traces.py#L73)。未授权条目占用本页 limit，合法用户会看到短页/空页；翻页成本和结果完整性依赖其他组织流量。Span 列表存在同类问题。

应先由目录编译 `AuthorizedTelemetryScope`，再把 namespace/service/instance 条件下推到 QueryPlan。若 VictoriaTraces 无法高效表达大 identity 集，使用服务端 scope handle、分区查询或可信 gateway；不要继续靠响应后过滤补授权。

## 6. 策略评估与告警投递数据流

- [APM 策略评估与投递数据流（Archify HTML）](./apm-policy-lifecycle.dataflow.html)
- [APM 数据流规格](./apm-policy-lifecycle.dataflow.json)
- [APM 数据流静态图](./apm-policy-lifecycle.dataflow.light.png)

### P0：endpoint × version 形成单策略 10,000 次顺序查询

目标展开对 endpoint 和 version 做笛卡尔积；GROUPED version 最多取 100 个，而 serializer 对 endpoints/versions 也分别限制到 100，因此单策略一次最多 10,000 个 target，见 [policies.py:148](../../server/apps/apm/services/policies.py#L148)。`evaluate()` 在一个任务中逐目标执行 VictoriaTraces 查询，外部查询还发生在目标行锁之前。

字段数量上限不等于容量上限。保存策略时必须计算总 target cost，给出硬上限或要求显式分区；运行时形成：

```text
PolicyScanRun(policy_version, cursor, scope_digest, plan_digest)
  └─ WorkItem(target_partition, lease_token, attempt, query_cost, outcome)
```

共享 scheduler 按团队、服务、API 类型和 VictoriaTraces 集群配额调度。Run reducer 只在必需 WorkItem 到达可接受终态后推进 cursor，并能识别调度/broker 丢失后补扫。

### P1：分钟扫描没有 durable run

dispatcher 每分钟全表读取启用策略，以 modulo interval 判断后逐个 `.delay()`，见 [tasks.py:74](../../server/apps/apm/tasks.py#L74)。dispatcher 崩溃或 broker 局部丢失没有可查询缺口；重复 delivery 又会在 cursor 竞争前重复昂贵查询。对于 consecutive window 语义，漏一个窗口不是普通延迟，而是可能改变告警结果。

Beat 应只创建幂等 ScanRun；独立 dispatcher/reaper 负责分区和补扫。运行事实必须能回答“哪个策略、哪个 cursor、多少目标、哪些失败、是否截断、为什么未推进”。

### P1：策略变更可能留下孤立 active alert

更新 Policy 会删除全部 TargetState，但不会显式关闭关联 active alert；disable 只改启用状态，destroy 直接删除 Policy，见 [control_plane.py:703](../../server/apps/apm/views/control_plane.py#L703)。旧 active alert 可以长期保持 active；再次启用/修改后，新 TargetState 也失去原生命周期关联，可能同时生成新 Alert。

Policy update/disable/delete 必须成为 LifecycleReducer 的显式命令，定义 `close(reason=policy_changed|disabled|deleted)`、保留、迁移三种语义之一，并在同一事务产生 Event、Evidence 和 DeliveryIntent。禁止通过删除 TargetState 隐式重置状态机。

## 7. 副作用、快照与并发

### P1：Outbox claim 没有 fencing token

`_claim()` 只写 `claimed_at`；外部 dispatch 完成后按 id 更新，不校验原 claim，见 [policies.py:517](../../server/apps/apm/services/policies.py#L517)。任务超过 lease 后，新 worker 可重新领取；此时旧 worker 仍可把新 worker 的状态覆盖成 delivered/failed，attempt 也可能回退。

claim 必须生成随机 token 或单调 epoch，所有成功/失败更新都使用 `WHERE id=? AND claim_token=? AND status=pending`。过期 worker 的提交返回 lost claim，不得写状态。下游继续使用 intent ID 作为 idempotency key，以覆盖“下游成功、DB 更新前退出”的重复窗口。

### P1：MinIO I/O 位于数据库锁事务内

EventSnapshot `persist()` 锁行后通过 `S3JSONField` 创建 payload，过期任务也在锁内删除对象，见 [snapshots.py:105](../../server/apps/apm/services/snapshots.py#L105)。远端超时会延长事务和连接占用；对象成功但 DB 回滚仍会留下孤儿对象。

正确流程是短事务 claim → 锁外上传/删除 → token 条件完成；对象 key 由 snapshot ID/content digest 确定，重复上传幂等；GC 对账无引用对象。

### P1：AlertMetricSnapshot 是无上限热 JSON

每次成功评估锁住 Alert 的一对一 Snapshot，线性扫描 timestamp 去重，再向 JSON 列表 append 并重写整行，没有容量上限，见 [metric_snapshots.py:19](../../server/apps/apm/services/metric_snapshots.py#L19)。长生命周期 Alert 会持续增大行、锁时间、序列化与复制成本。

将每个评估窗口保存为唯一 `WindowEvidence(alert, cursor, target, plan_digest)`；AlertMetricSnapshot 只保留固定数量的最近点和聚合摘要，作为可重建读模型。

## 8. Catalog 与 Dashboard 容量

### P1：Catalog 固定 TTL 锁和逐条事务对账

Catalog 任务使用 300 秒 cache lock，finally 无条件 delete；任务超过 TTL 后新 worker 可进入，旧 worker结束时还会删除新锁，见 [tasks.py:20](../../server/apps/apm/tasks.py#L20)。Reconciler 对最多 10,000 个活动维度逐条调用 `discover()`，见 [reconciler.py:19](../../server/apps/apm/services/reconciler.py#L19)。同一 Application 的活动会重复锁行、查询组织关系并 upsert Service/Instance。

引入 `CatalogReconcileRun(cursor, partition, token, heartbeat)`；按规范化 identity 批量查询、批量 upsert，组织投影只在 Application organization version 变化时传播。锁释放必须匹配 token，超时由 reaper 回收。

### P1：Dashboard 每请求私有扇出且 7d 语义不一致

Dashboard 加载全部可见 Service 并预取其 Instance，选最多 40 个 target；每个请求创建最多 8 个线程并发查询 RED。用户选择 7d 时，返回的 window 仍是 7d，但 RED 实际回退到近 24h，见 [dashboard.py:227](../../server/apps/apm/services/dashboard.py#L227)。并发用户会线性放大 VictoriaTraces 压力，且同一页面不同 KPI 可能使用不同时间范围。

短期在响应中返回每个 section 的 `effective_window` 和 truncation；中期复用按 team/service/window 的短 TTL rollup/cache，并让 Dashboard 经过共享 QueryBudget。缓存缺失时允许 partial/queued，不为每个 HTTP 请求创建新的容量孤岛。

## 9. 不合理设计要素与优先级

| 优先级 | 设计要素 | 影响 | 优化方向 |
|---|---|---|---|
| P0 | Trace 详情任一 Span 可见即返回全部 Span | 跨组织 Trace 泄露服务 identity、属性和错误细节 | AuthorizedTelemetryScope + per-span 裁剪 + scope-cut 图语义 |
| P0 | endpoint×version 最多 10,000 目标且单任务顺序查询 | 单策略独占 worker，VictoriaTraces 压力不可预算 | 保存期总成本限制 + ScanRun/WorkItem + 共享预算 |
| P1 | Trace/Span 分页后授权过滤 | 短页/空页、游标不完整、其他租户流量放大查询成本 | 授权范围下推 QueryPlan |
| P1 | 策略调度无 durable run | 漏执行不可审计/不可补扫，重复任务先重复外部查询 | 幂等 ScanRun、partition claim、reaper |
| P1 | update/disable/delete 不收敛 active alert | 孤立告警、重复生命周期、通知状态不一致 | Policy command 进入 LifecycleReducer |
| P1 | Outbox/Snapshot claim 无 token | 陈旧 worker 覆盖新结果，attempt/status 回退 | fencing token + 条件更新 |
| P1 | MinIO 上传/删除位于 DB 锁事务 | 长事务、连接池占用、孤儿对象 | 锁外幂等 I/O + intent/outbox + GC |
| P1 | Catalog 10k identity 逐条事务，cache lock 无 owner | 分钟任务重叠、应用行热点、数据库查询放大 | token lease + 批量 upsert + cursor partition |
| P1 | Dashboard 私有线程池，7d RED 实为 24h | 请求乘法放大、指标时间语义误导 | shared query budget/cache + effective_window |
| P1 | AlertMetricSnapshot 无上限 JSON append | 热行、O(n) 去重和整行重写持续恶化 | 不可变 WindowEvidence + 有界 rollup |
| P2 | organizations 以 JSON snapshot 同时承担授权查询 | 跨数据库索引能力不同，列表查询与历史语义耦合 | 保留历史 snapshot，另建规范化 AccessProjection |

## 10. 分阶段优化路线

### 短期：0—2 个迭代

1. 修复跨组织 Trace：列表/Span 查询授权下推；详情按 Span 裁剪并增加跨范围 Trace 回归测试；
2. 在 Policy serializer 增加 endpoint×version 总成本上限，拒绝无法在 SLA 内完成的配置；
3. Outbox 与 Snapshot 增加 claim token，所有结果写使用 token CAS；将 MinIO I/O 移出事务；
4. 为 policy update/disable/delete 定义 active alert 收敛语义并统一写 Event/Outbox；
5. AlertMetricSnapshot 加硬上限和压缩策略，先阻止无限增长；
6. Dashboard 明示 effective window/truncated，并增加团队级请求并发与 VT 查询预算。

### 中期：2—5 个迭代

1. 建立 `AuthorizedTelemetryScope + TelemetryQueryPlanner`，统一 Trace/Span/RED/Topology/SLO/Dashboard 的 scope、AST、成本和审计；
2. 建立 `PolicyScanRun/WorkItem`，支持分区、公平调度、缺口补扫和 cursor reducer；
3. 建立 `CatalogReconcileRun`，按 identity 批量 upsert，使用 token lease/heartbeat；
4. `LifecycleReducer` 统一自动评估、手工关闭、策略变更、恢复和通知意图；
5. 引入不可变 `WindowEvidence`，Snapshot/Dashboard/SLO 变为可重建投影。

### 长期：5 个迭代以后

1. Scope digest、QueryPlan digest、Run identity、Event、Evidence 和 Delivery outcome 形成贯穿查询到通知的审计链；
2. OTel/JetStream/VictoriaTraces 容量、lag、成本和截断进入统一预算及 SLO；
3. 只有当查询、catalog reconciler 或 policy runtime 在容量和发布节奏上确需独立扩缩容时，再沿既有 Port 拆进程；不要先用微服务替代模块设计。

## 11. 目标架构图

- [APM 目标架构（Archify HTML）](./apm-target.architecture.html)
- [APM 目标架构规格](./apm-target.architecture.json)
- [APM 目标架构静态图](./apm-target.architecture.light.png)

目标架构的核心不是增加组件数量，而是让每一次工作都带着四类身份运行：

```text
authorized scope → query plan + cost → run/work-item token → facts/effect intents
```

## 12. 开发提醒

1. **授权必须先于外部查询和分页。** serializer、sanitizer、响应过滤都不能替代 scope 下推；跨组织 Trace 要测试“一个可见 Span + 多个不可见 Span”。
2. **配置上限必须按组合成本验证。** 单字段各 100 不代表安全；新增维度、breakdown、窗口或 SLO 前先计算笛卡尔积和最坏查询数。
3. **Celery 至少一次交付必须有稳定 run identity。** `claimed_at` 不是 fencing；所有外部结果写回必须校验 token。
4. **禁止在数据库锁内调用 VictoriaTraces、MinIO、NATS 或通知接口。** 事务只裁决本地事实和唯一意图。
5. **Policy 变更也是领域事件。** update、disable、delete 不允许绕过 active alert 状态机。
6. **时间窗必须诚实。** 请求 7d、实际查 24h 时，API 和 UI 必须显式展示 effective window；禁止静默回退。
7. **快照必须有容量和重建策略。** JSON/S3 对象先定义最大点数、保留期、分页和重建来源，再允许持续 append。
8. **保留现有 Port、TargetState、EventSnapshot、Outbox 和健康探测。** 优化应深化这些正确边界，不要把协议重新散回 View、task 和 serializer。
