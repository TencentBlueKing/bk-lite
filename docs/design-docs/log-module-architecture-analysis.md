# Log 模块架构与代码结构分析

> 分析日期：2026-08-21
> 分析范围：`server/apps/log/`，以及直接相连的 HTTP/NATS、Celery/Beat、NodeMgmt、VictoriaLogs、中心 Vector、MinIO、SystemMgmt 与 Alerts 边界。
> 分析方式：按“采集配置控制面—日志查询数据面—策略扫描—告警事实—通知收敛”完整模块分析，不按单个 tech-debt 或大文件逐项罗列。

## 1. 结论摘要

Log 不是一个单纯的 VictoriaLogs 查询代理，而是五类能力叠加的复合控制面：

1. 管理 CollectType、CollectInstance、组织关系和 NodeMgmt 配置引用；
2. 编译 LogExtractor 规则并发布中心 Vector 全局配置；
3. 以可信团队和 LogGroup 作为查询访问边界；
4. 为每个 Policy 建立 Beat 任务并扫描关键字/聚合条件；
5. 维护 Alert、Event、原始证据、快照和跨模块通知生命周期。

模块已经具备多个值得保留的可靠性基础：HTTP/NATS 查询都从服务端解析可信团队；查询日志分组失败时请求链路 fail-closed；策略扫描有延迟窗口、有界回补、singleton、游标 CAS 和确定性 Event ID；中心 Vector 发布用 generation 与 checksum 丢弃陈旧任务；通知补偿有时间窗、批量和重试上限。

最重要的结构性问题是，这些正确机制尚未形成统一协议：

- **策略扫描的范围语义与请求查询相反。** 配置了日志分组的策略在分组构建异常时，会回退为仅按 collect_type 查询，原本应停止的错误被扩大为更宽日志扫描；同时 `alert_condition` 只作为 JSON 保存，`group_by` 和聚合字段未经统一 schema/标识符白名单便进入 LogsQL。
- **采集配置只有本地引用，没有跨模块收敛事实。** Django 事务可以回滚 Log 数据库，却不能回滚已成功的 NodeMgmt RPC；创建、更新和删除分别存在远端成功/本地失败、父配置成功/子配置失败等漂移窗口，模型又没有 desired generation、effective generation、operation、checksum、状态和错误用于对账。
- **容量以单策略和单连接隐式放大。** 分组关键字策略先取最多 1000 组，再为每组发一次样本查询，单策略一次扫描最多产生 1001 次 VictoriaLogs 请求；每个 SSE tail 连接占用独立 daemon 线程。返回条数虽有上限，但没有统一的查询跨度、复杂度、团队/策略预算和 SSE 并发配额。
- **领域事务与外部 I/O 混合。** EventRawData 的 MinIO 上传发生在 DB 事务内；通知在 Event/Alert 行锁覆盖期间同步调用外部通道并 sleep 重试；AlertSnapshot 每次读写一份最多 500 项的 S3 JSON 列表。它们牺牲数据库锁时间，仍无法获得真正的 exactly-once。

建议短期不拆微服务，先在同一 Django app 内建立三个深模块接口：`ScopedQueryPlan`、`CollectorConfigOperation/Reconciler`、`AlertLifecycleReducer + DeliveryOutbox`。中期引入 VictoriaLogs 共享预算和 typed query AST；长期统一采集配置及 Vector 配置的 desired/effective generation，并把不可变 Evidence 与可重建 Snapshot 分离。

## 2. 模块规模与职责边界

本次统计生产 Python 约 11,421 行（排除 migrations/tests），测试目录有 64 个 Python 文件；HTTP 注册 17 个 Router，NATS 侧注册 6 个 handler。最大的单文件是约 1,395 行的 `tasks/services/policy_scan.py`，但文件大小只是多条变化轴交叉后的结果，不是拆分依据。

| 能力域 | 当前实现 | 主要外部事实 |
|---|---|---|
| 采集目录 | CollectType、CollectInstance、组织关系 | 节点来自 NodeMgmt，权限组织来自 SystemMgmt |
| 配置下发 | CollectConfig 仅存 ID、文件类型和父子角色 | 配置正文与实际下发状态在 NodeMgmt |
| 提取规则 | LogExtractor、compiler、SystemVectorConfigState | 中心 Vector 通过 token 拉取全局 YAML |
| 查询 | AccessScope、LogGroupQueryBuilder、SearchService | VictoriaLogs 是日志事实源 |
| 策略检测 | Policy、PeriodicTask、LogPolicyScan | Celery/Beat 执行，VictoriaLogs 提供窗口结果 |
| 告警事实 | Alert、Event、EventRawData、AlertSnapshot | DB 保存生命周期；MinIO 保存大对象 |
| 通知 | LogAlertLifecycleNotifier、补偿任务 | SystemMgmt 渠道、Alerts 生命周期接入 |

Log 应拥有“日志访问范围、查询计划、日志策略和日志告警事实”；NodeMgmt 应拥有“节点配置期望/实际状态”；VictoriaLogs 应是日志内容事实源；MinIO 只应保存不可变大对象，不应成为一个 Alert 可变列表的并发协调器。

## 3. 现状架构图

- [Log 现状架构（Archify HTML）](./log-current.architecture.html)
- [Log 现状架构最终规格](./log-current.architecture.json)
- [Log 现状架构静态图](./log-current.architecture.light.png)

现状有三条主要路径：

```text
Collector Control → NodeMgmt Config
                    Extractor generation → 中心 Vector → VictoriaLogs

HTTP / NATS → Access Scope → Search Service → VictoriaLogs

Policy / Beat → LogPolicyScan → VictoriaLogs → Alert / Event / Snapshot → 通知
```

三条路径共享 CollectInstance、LogGroup 和 VictoriaLogs，却采用不同的失败语义、容量控制与外部副作用协议。因此目标不是按文件夹拆成三个服务，而是让三条路径共享同一组小而完整的领域 Interface。

## 4. 应保留并深化的架构基础

### 4.1 查询入口已经使用可信服务端范围

HTTP 查询先调用 `LogAccessScopeService.resolve_scope()`，要求请求中的每个日志分组都属于当前可信团队且用户有权访问；NATS 查询从服务端 SystemMgmt 数据范围解析 actor，不信任消息体声明的 superuser，并在异常时返回 DENY_ALL。这应成为策略扫描、搜索条件和未来 OpenAPI 的统一基础。

后续不要让调用方直接传 `team`、拼接好的 scope query 或“是否超管”；应用层入口应统一接收 `ActorContext`，再生成不可覆盖的 `ScopeSnapshot`。

### 4.2 策略扫描已有稳定重试身份

扫描窗口先减去 ingest delay，并保留 overlap；长时间中断只按 `MAX_BACKFILL_SECONDS` 和 `MAX_BACKFILL_COUNT` 有界追赶。一个成功游标后的所有重试共享 `execution_key`，Event ID 由 policy、execution key 和 source identity 确定，数据库主键是最终幂等门禁。窗口全部完成后才以 CAS 单调推进游标，见 [policy.py:17](../../server/apps/log/tasks/policy.py#L17)。

这套设计应保留。未来分片执行时，execution identity 需要扩展为：

```text
ScanRun(policy, cursor, scope_digest, query_plan_digest)
ScanPartition(run, partition_key, lease, attempt, outcome)
```

游标只能由 Run reducer 在所有必需分片达到可接受终态后推进，单个 worker 不直接修改策略游标。

### 4.3 Vector 发布已有 generation 裁决

规则变更在事务提交后投递 generation；发布任务只处理仍等于 desired generation 的版本，过期任务返回 stale；编译结果保存 checksum、published generation 和 contract version，见 [publication.py:68](../../server/apps/log/services/log_extractor/publication.py#L68)。

这是正确的 last-write-wins 基础，但当前 `published` 只表示数据库快照生成成功，并不表示中心 Vector 已拉取、解析和应用。后续应在不破坏现有 generation 的前提下增加 consumer effective generation、last fetch、last apply、checksum 和 error ACK。

### 4.4 告警并发写入已有数据库裁决点

事件创建通过 Policy 行锁串行化同一策略，写入前重新锁定 Event/Alert 并拒绝陈旧窗口覆盖；AlertSnapshot 更新也用行锁和 event_time 比较避免旧 worker 回写更新事实。通知 created/closed 的迟到回执通过状态和关闭时间条件更新避免反向覆盖。

这些 fencing 条件应集中到 `AlertLifecycleReducer`，不能在新增手工关闭、重开、确认、通知或外部回调路径时各自复制一部分规则。

## 5. 策略扫描与告警生命周期数据流

- [Log 策略扫描与告警生命周期（Archify HTML）](./log-policy-lifecycle.dataflow.html)
- [Log 数据流规格](./log-policy-lifecycle.dataflow.json)
- [Log 数据流静态图](./log-policy-lifecycle.dataflow.light.png)

### 5.1 范围构建存在 fail-open 降级

`_build_query_with_log_groups()` 配置了 log_groups 时调用 builder；任何异常都被捕获并回退为 `_add_collect_type_filter(base_query)`，见 [policy_scan.py:399](../../server/apps/log/tasks/services/policy_scan.py#L399)。这不是普通容错：日志分组通常比 collect_type 更窄，故障会改变策略业务范围。

正确语义应是：

```text
configured groups + build failure → ScanRun failed → cursor unchanged → observable retry
no configured groups             → explicit collect_type scope
```

两者必须在配置和运行事实中可区分。禁止把“配置为空”和“配置解析失败”映射为同一查询。

### 5.2 alert_condition 缺少完整 typed contract

PolicySerializer 验证 schedule、period 和 log_groups，但 `alert_condition`、`show_fields` 仍直接使用模型 JSON，见 [policy.py:9](../../server/apps/log/serializers/policy.py#L9)。扫描器将 `group_by`、聚合 field 和函数组合为 `stats by (...)`、`sum(field)` 等 LogsQL，见 [policy_scan.py:447](../../server/apps/log/tasks/services/policy_scan.py#L447)。

短期必须在写入边界验证：

- alert type 对应的 discriminator schema；
- query 最大长度与禁止/允许的 pipe；
- field/group_by 的标识符格式、数量和允许字段；
- function/operator/mode 白名单；
- keyword sample limit、group result limit、窗口上限；
- alert name token 只能引用已声明字段。

运行时仍需重新编译并校验已存配置，因为迁移、历史数据或直接写库可能绕过 API。

### 5.3 grouped detection 具有乘法查询放大

关键字分组先请求最多 1000 个聚合结果，再为每一组请求样本；每个 PolicyScan 自建最多 10 线程的 ThreadPoolExecutor。活动策略数增加时，总并发约为：

```text
active policy workers × per-policy pool × per-group sample queries
```

当前没有团队、策略、VictoriaLogs 集群或时间窗级共享预算；1000 组之外也没有明确截断事实。这会让增加 Celery worker 同时放大 VictoriaLogs 压力。

短期应降低并明确最大 group/sample 数并返回 truncation；中期将 scan 编译成 QueryPlan 与 partitions，由共享 scheduler 领取预算，记录实际 query count、duration、bytes/rows 和 rejected/throttled 原因。

### 5.4 事务和外部 I/O 边界过深

Event/Alert 数据库事务中逐条保存 EventRawData，而 `S3JSONField.pre_save()` 会上传 MinIO，见 [policy_scan.py:903](../../server/apps/log/tasks/services/policy_scan.py#L903)。MinIO 失败可以阻止 DB 提交，却无法在 DB 最终提交失败时撤回已经上传的对象，且远端 I/O 延长了行锁持有时间。

通知更直接：代码锁住 Event 和 Alert 后调用外部通知，并在线性退避中 sleep，直到保存通知结果才释放锁，见 [policy_scan.py:1322](../../server/apps/log/tasks/services/policy_scan.py#L1322)。这样可降低并发双投概率，但仍存在“下游成功、DB commit 前退出”的重复窗口。

应改为：领域事务只写 Event/Alert/Evidence metadata 和唯一 DeliveryIntent；worker 通过短 lease 领取，外部调用不持有领域行锁；结果以 intent token 条件更新；Beat 重扫 broker 投递失败、过期 lease 和待重试 delivery。下游支持 idempotency key 时直接使用 intent ID。

### 5.5 AlertSnapshot 是有界但昂贵的可变对象

每个 Alert 只有一条 AlertSnapshot，更新时读取整个 S3 列表、按 event_id 建 map、追加或覆盖、裁剪至 500，再上传整个对象，见 [policy_scan.py:1144](../../server/apps/log/tasks/services/policy_scan.py#L1144)。虽然空间有界，但连续事件的累计传输与序列化成本接近 O(number_of_events × snapshot_size)，并发又集中在一行和一个对象键。

EventRawData 已经是逐 Event 对象，长期应把它作为不可变 Evidence；AlertSnapshot 只保存摘要/索引或按页构建的读模型，失败时可由 Event facts 重建。

## 6. 采集配置与 Vector 发布控制面

### P0：Django 事务不能保证 NodeMgmt RPC 原子性

`batch_create_collect_configs()` 在 `transaction.atomic()` 内创建 CollectInstance/Organization，再调用 Controller，注释称外层事务和 savepoint 可保证原子性，见 [collect_type.py:38](../../server/apps/log/services/collect_type.py#L38)。但 Controller 最终调用 NodeMgmt 创建配置；远端提交后若本地事务失败，NodeMgmt 结果不会回滚。

删除方向相反：先调用 NodeMgmt 删除父/子配置，再开始本地事务删除 CollectConfig/CollectInstance 和标记 Vector dirty，见 [collect_config.py:630](../../server/apps/log/views/collect_config.py#L630)。本地失败会留下引用已删除远端配置的记录。父配置更新成功、子配置更新失败也会形成混合版本。

短期新增：

```text
CollectorConfigOperation(
  operation_id, instance_id, kind, desired_generation, payload_digest,
  status, attempt, lease_token, lease_expires_at, last_error
)
```

本地事务只写 desired state 和 operation；reconciler 以稳定远端 ID 幂等 create/update/delete，再读取 NodeMgmt effective state 对账。接口响应可返回 accepted/operation_id，不再声称跨系统原子完成。

### P1：Vector 发布缺少自动恢复与 rollout 可见性

任务投递失败会把 SystemVectorConfigState 标为 failed，管理接口可以手工 retry；任务在设置 GENERATING 后进程退出时，没有 lease/heartbeat/reaper 自动回收。配置 endpoint 只返回最新快照和 generation，没有消费者 ACK，见 [system_vector.py:9](../../server/apps/log/views/system_vector.py#L9)。

短期增加 Beat reconciler：扫描 desired > published、FAILED 和超时 GENERATING，按 generation 幂等重投；中期记录每个中心 Vector consumer 的 effective generation/checksum/last_seen/apply_error，并区分 compiled、available、fetched、effective 四个状态。

## 7. 查询与 SSE 容量模型

现有查询有三项正确保护：默认无时间参数时使用 15 分钟窗口；结果 limit、field values limit、hits fields limit 有环境可配置上限；同步 HTTP 请求有 10 秒 timeout。SSE 使用独立 daemon thread，避免长期占用 ASGI 默认线程池，并使用 maxsize=256 的队列提供连接内背压。

仍缺少的系统级保护是：

- start/end 只是 CharField，显式请求可跨任意时间范围；
- query 没有最大长度、复杂度评分和允许 pipeline contract；
- step 未做结构和最小粒度约束；
- 单用户、团队、策略和 VM 集群没有并发/速率预算；
- SSE 每连接一个线程，但没有全局连接上限和团队配额；
- 请求 limit 只限制返回行，不限制 VictoriaLogs 扫描工作量。

建议用统一 `ScopedQueryPlan` 表达逻辑 query、scope digest、storage query AST、time range、result limit、estimated cost 和 budget key。HTTP、NATS、策略扫描与 dashboard 统计都经过同一 compiler，区别只在调用方可用的 profile。

## 8. 代码结构与深模块建议

当前 `views/policy.py` 同时承担权限、组织更新、serializer、Beat 编排、Crontab 解析、告警操作和通知触发；`policy_scan.py` 同时承担窗口查询、LogsQL 拼装、分组线程池、规则判断、Alert/Event reducer、MinIO 快照和通知。直接把文件拆小不会降低认知成本。

建议在同一 app 内形成以下深接口：

```text
LogCommandGate.authorize(actor, command) -> ScopedCommand
QueryPlanCompiler.compile(scope, condition, window, profile) -> ScopedQueryPlan
QueryExecutor.execute(plan, budget) -> QueryPage / PartitionResult

CollectorConfigService.set_desired(command) -> OperationRef
CollectorConfigReconciler.run(operation) -> EffectiveState

AlertLifecycleReducer.apply(scan_result) -> Facts + DeliveryIntents
DeliveryWorker.deliver(intent) -> DeliveryOutcome
```

HTTP、NATS、Beat 和管理命令只做 Adapter；查询字段映射、范围合并、幂等身份、状态裁决和重试策略进入上述 Module，调用方不需要知道拼接顺序或隐含失败降级。

## 9. 不合理设计要素与优先级

| 优先级 | 设计要素 | 影响 | 优化方向 |
|---|---|---|---|
| P0 | 策略 LogGroup 构建异常回退宽查询 | 范围扩大、误报、容量放大，且错误不显式 | fail-closed；ScanRun 失败且游标不前进 |
| P0 | `alert_condition` 无 typed schema，字段直接进入 LogsQL | 查询注入/无效配置/高成本计划在运行时暴露 | discriminator schema、字段和函数白名单、复杂度限制 |
| P0 | Log DB 事务包裹 NodeMgmt RPC | 创建/更新/删除可形成跨系统漂移且无法自动对账 | durable operation + desired/effective + reconciler |
| P1 | grouped scan 每组样本查询且无共享预算 | 单策略 1001 查询，多 worker 乘法放大 | QueryPlan 分片、截断事实、团队/VM 预算和背压 |
| P1 | 通知与 MinIO I/O 位于 DB 锁/事务内 | 长事务、锁竞争、连接池占用，仍可能重复 | Evidence metadata + DeliveryOutbox + lease worker |
| P1 | Vector 状态只有 compiled/published，无 reaper/consumer ACK | 卡住需手工恢复，无法判断实际生效范围 | publication reconciler + effective generation ACK |
| P1 | 查询只限制返回条数 | 大时间窗/复杂查询仍可耗尽 VM；SSE 线程数无界 | 时间/复杂度/速率/连接并发预算 |
| P2 | AlertSnapshot 单对象读改写 | 热告警写放大和对象锁热点 | 不可变 Evidence；Snapshot 变为可重建分页读模型 |
| P2 | SearchCondition 先流式遍历团队记录再过滤 embedded group IDs | 页大小不降低过滤成本 | 规范化 SearchConditionLogGroup 关系并 DB 下推 |

## 10. 分阶段优化路线

### 短期：0—2 个迭代

1. 将策略日志分组异常改为 fail-closed，并增加“配置分组不存在、规则损坏、数据库异常均不执行 VM 查询且不推进游标”的回归测试；
2. 为关键字/聚合 alert_condition 增加 typed serializer 和运行时 compiler，限定字段、函数、operator、group/sample、query 长度和时间跨度；
3. 增加 `CollectorConfigOperation`，先覆盖 create/delete 的跨模块故障窗口，再覆盖父子配置 update；
4. 把通知外发从 Event/Alert 行锁事务移到唯一 DeliveryIntent；保留现有补偿任务作为迁移期 consumer；
5. 增加 Vector publication reaper，自动恢复 failed、desired gap 和超时 generating；
6. 加入最小 VM/SSE 保护：团队并发、策略并发、最大窗口、SSE 连接数、group/sample 上限和可观察 rejection 指标。

### 中期：2—5 个迭代

1. 建立 ScopedQueryPlan 与 QueryBudget，统一 HTTP/NATS/Policy 的 scope、AST、cost、timeout 和执行统计；
2. grouped detection 改为可分片 ScanPartition，使用共享 scheduler 而不是每策略私有线程池；
3. 建立 AlertLifecycleReducer，把 created/update/closed、陈旧结果保护、notice intents 统一到单一状态机；
4. EventRawData 使用不可变 key，Snapshot 改为增量索引/分页读模型；
5. Collector Config 与 Vector Config 共用 desired/effective generation 术语和对账仪表盘。

### 长期：5 个迭代以后

1. 形成可审计 `ScanRun + QueryPlanDigest + ScopeDigest + Evidence`，能回答某告警由哪一版策略、范围和日志窗口产生；
2. Vector/NodeMgmt consumer 上报 effective generation、checksum、apply status，实现灰度和差异对账；
3. 若 VictoriaLogs 查询、配置 reconciler 与告警生命周期在容量和发布节奏上真正需要独立部署，再基于既有 Port 拆进程；不要先以微服务作为代码清理手段。

## 11. 目标架构图

- [Log 目标架构（Archify HTML）](./log-target.architecture.html)
- [Log 目标架构最终规格](./log-target.architecture.json)
- [Log 目标架构静态图](./log-target.architecture.light.png)

目标架构的关键不是增加层数，而是建立三个唯一裁决点：

- **LogCommandGate / QueryPlanCompiler**：唯一决定 actor、scope、查询 AST 和成本边界；
- **ConfigReconciler**：唯一负责跨 NodeMgmt/Vector 的 desired → effective 收敛；
- **AlertLifecycleReducer / DeliveryOutbox**：唯一负责状态事实和外部副作用意图。

## 12. 开发提醒

后续在 Log 模块新增或修改功能时，开发同学需要持续检查：

1. 配置了范围却解析失败时必须拒绝，禁止回退到更宽条件；
2. 调用方不能提交可信 team、superuser 或拼接后的范围语句；
3. 所有 LogsQL 字段、函数、group 和 pipeline 必须从 typed compiler 生成，不在 view/task 中直接插值；
4. `limit` 不是容量保护，必须同时限制时间跨度、复杂度、并发、速率和 SSE 连接；
5. 不要在循环内为每个 policy/group 创建无共享预算的线程池或查询；
6. 数据库事务不能回滚 RPC、broker、MinIO 和通知；事务内写 intent，事务外幂等执行与重扫；
7. 外部 I/O 不持有 Alert/Event/Policy 行锁，不在事务内 sleep 重试；
8. Celery singleton 不是永久锁、租约或 exactly-once；worker 中断必须有数据库状态可恢复；
9. 游标只由完整 ScanRun 成功推进，分片不能各自推进；
10. generation 的 `published`、`fetched`、`effective` 必须区分，不能把“生成成功”描述为“已全量生效”；
11. 大对象使用不可变引用，当前 Snapshot/汇总是可重建读模型；
12. 新增 HTTP、NATS、Beat 或管理命令入口时复用应用用例，不复制权限、范围、查询拼装和生命周期规则。
