# 告警聚合低内存优化：统一分批管线

Status: implemented — 2026-10-19，项目测试库 111 passed

## Problem Statement

周期聚合把一个策略窗口的事件同时放进 Python list、Pandas 和进程内 DuckDB，分组 SQL 再带回整组 `LIST(event_id)`。建警、更新和恢复检查继续把 Event ORM 整组物化。共享 Celery worker 的峰值内存随窗口规模和活跃告警历史成员数上涨。

对应代码：

- `DuckDBConnection.load_events_to_memory`：`list(values(...))` → `DataFrame` → `CREATE TABLE events_table`
- `macros.aggregate_fields`：`LIST(event_id)`、无序 `FIRST(title/description)`、无序 `STRING_AGG(DISTINCT resource_name)`
- `AlertBuilder._get_events_by_ids` / `_resolve_standard_fields`：整组 `event_id__in` 后再 `list(events)`
- 更新路径 `alert.events.select_related("source").all()` 后对同一迭代器做多次全量合并
- `AlertRecoveryChecker.check_and_recover_alert`：`list(alert.events.all())`

产品约束不变：一组 CREATED 在同一事务里挂齐之后，新建 Alert 或本轮更新才对外可见。不截断事件，不先发布半成品，也不异步补挂 CREATED。

## 复核后不再单列的问题

对照当前实现，下面四件事不再作为开放取舍：

1. **分批没有数据库快照，可以接受。** 今天的加载是一次 `SELECT`（语句级快照）。改成按 pk 分批后，加载期间新提交的行可能只出现在尚未扫描的 pk 段。漏掉的行只要仍落在后续轮次窗口内，下轮会进入。不为加载过程加可重复读长事务，也不做提交前第二套资格校验。
2. **代表事件和资源名顺序直接定死。** `FIRST()` 和 `STRING_AGG(DISTINCT)` 在 DuckDB 1.1.3 上没有 `ORDER BY`，现状本身无序。多事件标题通常被 `_normalize_fingerprint` 改写成指纹文案；单事件描述只有一条，顺序无影响。真正可见的是多事件正文里的 `影响范围：资源名`。资源名改为按字符串升序拼接。标题回退和单事件描述取 `received_at DESC, pk DESC`。这不是待确认的产品变更。
3. **组失败后的自动分派沿用现有顺序。** `_create_or_update_alerts` 先收集已提交组，循环结束后调度分派，再因失败组抛错。`_mark_strategy_executed` 因此不会跑，`last_execute_time` 不推进。已提交组照常分派，失败组下轮重试。
4. **会话不补发历史超时，沿用现有顺序。** `event_aggregation_alert` 先跑完聚合（组内恢复检查可以把 observing 改成 recovered），再跑 `TimeoutChecker`。检查器只处理仍为 observing 的告警，没有按截止时刻重演。本轮已经恢复的告警不转正、不补发超时通知。内存优化不新增这套重演。

Outbox 幂等键在上一版里没有写死，这是必须补上的实现约束，见下文。`gap-analysis.md` 不存在，本说明自洽，不再引用它。

## Solution

一条分批管线，不按组大小分流，不引入第二套分组器、成员暂存表、跨 Beat 游标或 generation。

```text
冻结本策略 window_end
  → 按 pk 分批投影，写入本轮 DuckDB 薄表
  → 一次取出组摘要（无 LIST(event_id)）
  → 每组一个事务：
       领取现有指纹租约
       → 按 pk 分批挂齐本窗 CREATED
       → 按 pk 分批合并全部历史成员
       → 分批补挂已提交的恢复并做恢复判断
       → 写入本轮恢复补查 Outbox
  → 该组提交后发布新建告警的 created
  → 组循环结束后，对已成功且需要分派的告警调度自动分派
  → 有失败组则抛错，不推进 last_execute_time
  → 任务末尾仍执行现有 TimeoutChecker
```

小组只有一批。大组和历史成员很多的告警走同一条路径。

本期去掉多份完整事件和整组 ORM 的同时驻留。DuckDB 薄表、分组状态、资源名拼接和监控对象快照仍随规模增长。不承诺常数内存、任意大窗口在一分钟内完成，或无损追赶任意长积压。

## User Stories

1. 运维人员看到新告警或本轮更新时，该组窗口内的 CREATED 已经全部关联。
2. 相同输入得到相同 fingerprint、成员集合和字段合并结果。多事件正文里的资源名顺序改为字典序，标题回退改为最新事件。
3. 本窗只新增少量事件、历史成员很多时，合并和恢复判断按批读取，不把整条告警的 Event 对象一次装进内存。
4. 组事务提交前已经入库、但接入当时看不到未提交关系的恢复，在提交后的补查里挂上。
5. 同规模基线可以比较峰值 RSS、整轮耗时和最大组事务耗时。

## Implementation Decisions

### 1. 一轮一个时钟

- 每个策略在进入查询前取一次 `window_end`。窗口为 `[window_end - window_size, window_end)`。ORM 过滤和 DuckDB `time_filter` 使用同一对上下界。
- 今天 ORM 只用 `received_at__gte`，SQL 又在加载之后调用 `WindowConfig.get_window_start()` 重新取 `now()`。上下界分开之后，加载期间 `received_at >= window_end` 的事件留给下一轮。Beat 间隔小于窗口时，这些事件仍会被下一轮扫到。
- 资格以各批查询当时已提交的行为准。屏蔽、本策略已闭环成员排除、match_rules 仍在查询里。不增加第二套资格校验。
- 相关聚合继续是滑窗。`last_execute_time` 仍不是消费水位，只在全部组成功后按现有方式推进；无匹配事件也沿用现有推进。不修长轮次或停机超过窗口造成的覆盖空洞，也不为超预算窗口截断数据后返回成功。
- 保留 Beat 重叠锁、策略串行、处理中不释放锁。不改缺失检测和 Instant。

### 2. 薄表与分组

- 复用按 pk 的分批读法，批次大小是聚合模块内的一个常量，默认 1000，不新增用户配置。RSS 基线可以改这个常量，不为此加策略参数。
- 投影列：pk、event_id、received_at、action、level、title、description、resource_name、external_id，加上本策略 group_by 实际用到的列。enrichment 只投影分组表达式需要的路径，提取语义与现在的对象路径、历史数组路径一致。
- 去掉整窗 list 和 Pandas。按批 `INSERT` 进本轮 DuckDB 表。策略结束或失败时释放该表和读取资源。DuckDB 版本以 `pyproject.toml` 锁定的 1.1.3 为准。
- 组摘要去掉 `LIST(event_id)`。摘要是每组一行，行内没有成员 ID，可以一次取出。不依赖同一连接上的双游标。
- 成员按与摘要相同的有效分组表达式查询，再按 pk 分批关联。不构造整组 `IN`，不先攒整组 Event 对象。
- 分组规则不变：有效维度、全空降到 external_id、类型转换、fingerprint、级别映射。不新增 Python 分组器。
- 资源名：`STRING_AGG` 的输入改为按资源名排序后的去重结果，正文仍是现有「单事件用描述，多事件用影响范围」规则。
- 标题回退和单事件描述使用 `received_at DESC, pk DESC` 的那一条。多事件标题继续走 `_normalize_fingerprint`。

### 3. 完整组事务与历史合并

- 继续只用 `claim_active_fingerprint` 的租约和行锁。
- 本窗 CREATED 的每一批都在该组事务内挂上。任一批失败，回滚该组本轮的 Alert 和关系。重试以锁内已提交关系为准，不看进程缓存。
- 更新仍按全部历史成员计算字段，不改成只合并本窗增量。标准字段、dimensions、labels、enrichment、enrichment_meta、push_source_ids、monitor_objects、owners 都改成可分批累积的归约，内部不再 `list(events)`，也不把已耗尽的迭代器传给下一个函数。
- 保持现有归约规则：按 pk 的合并顺序、唯一标量、labels 全体一致才保留、enrichment 冲突、监控对象快照、owners 上限。只判断一致性的字段保留「当前值 + 是否冲突」，不收集全部候选值。
- 告警上的真实输出字段不截断。分批降低的是驻留，不是历史成员的读取次数。
- 新建告警仍在该组 `on_commit` 发布 `created`。更新不新增生命周期事件。observing 仍延迟到超时转正后再分派。
- 不把整条策略包进一个事务，也不等所有组完成才发布已经提交的新建告警。

### 4. 恢复与提交交接

- 恢复判断改为分批或条件查询，判断式不变：每个 CREATED 都存在完整匹配键相同、有效事件时间严格更晚的 RECOVERY/CLOSED，才恢复整条告警。
- 时间回退仍是 CREATED 用 `start_time or received_at`，恢复用 `end_time or start_time or received_at`。比较保持 `>`。
- 组事务内按本批 CREATED 补查已经提交的恢复，新建和更新都做。恢复查询不受窗口右端限制，也不套用 CREATED 的 match_rules。
- 匹配键、唯一回退条件和行锁关联沿用 `RecoveryHandler` / `associate_event_with_monitor_sources` 的规则。唯一回退必须在完整候选告警集合上判断，不能因为一批里只看到一个告警就当成唯一。CLOSED 仍走恢复，不接 AutoCloser。
- 不直接调用会 `prefetch_related` 全量事件的 `handle_recovery_events`，也不把 `RecoveryHandler` 的 `on_commit` 检查当成事务内同步检查。重复关联、重复恢复不产生重复生命周期副作用。
- 交接漏洞保持这个时序：组内补查已经结束，恢复事件提交，接入查询看不到尚未提交的关系，然后聚合事务提交。此后现有接入路径不会再试这一次。
- 补偿写在同一组事务里，复用 `enqueue_outbox`。类型为恢复补查。幂等键为 `recovery-reattach:{alert_pk}:{window_end_iso}`。负载只有告警主键和本次 `window_end`，没有成员 ID 列表。
- `enqueue_outbox` 对已存在的键不会再次调度。因此不能只用 `alert_id`：一旦投递成功，以后同一告警的交接就再也排不进去。同一 `window_end` 的重试若事务已提交，补查由已写入的那条 Outbox 负责；事务若回滚，行一并回滚，重试可以再插入。后续轮次只要该 CREATED 仍在窗口内，组内补查仍会再看一次。
- 提交后的消费者按该告警已提交的 CREATED 关系分批补查。锁内重读状态，已闭环则不重新激活。找不到恢复不是失败。查询或写入失败必须抛给 Outbox，重试耗尽保持可见。不新增任务表或 Beat。
- 这条补查允许晚于 `created` 和通知。不阻塞生命周期去等未来的恢复。

### 5. 会话终点

- 新建和 observing 更新的 `session_end_time` 改为本次 `window_end + timeout`。`WindowConfig.get_session_end_time()` 不再在挂接时另取 `now()`。SQL 里选出的 `session_end_time` 与 Builder 使用同一个值。
- 与今天的差别：终点锚在本轮开始，而不是锚在该组写库瞬间。长轮次里，告警更容易在本轮末尾的 `TimeoutChecker` 被转正。这是时钟收拢的结果，不是新的通知策略。
- 本轮组事务里已经恢复的告警，到超时检查时已不是 observing，不转正，不补发历史超时。不增加按历史截止时刻重演通知的逻辑。

### 6. 验收

- 日志只记有界汇总：窗口加载、DuckDB 分组、挂接与历史合并、恢复检查、提交后补查、整轮。不记事件正文和全量成员。
- 在 DuckDB 1.1.3 上确认分批插入、`memory_limit` 和临时目录。引擎限额不是进程 RSS 上限。
- 同数据、同环境给出修改前后的峰值 RSS、整轮耗时、最大组事务耗时、查询次数。没有基线就不写节省比例。代表性负载仍然把内存、组事务或整轮打过调度容量时，容量目标不算完成。
- 只有实测证明单轮方案不够，才另开跨 Beat 续算。本期不预建游标、持久化薄表或 generation。

## Testing Decisions

- 结果对齐：fingerprint、成员集合、count、first/last、映射级别、labels、enrichment、dimensions、来源、监控对象快照。覆盖全空维度、external_id 降级、历史 enrichment 数组。
- 窗口：同一 `window_end` 贯穿 ORM 与 DuckDB；`received_at == window_end` 不进本轮；加载中途提交且 pk 已扫过的事件本轮不进、下轮仍在窗口内时进。
- 顺序：多事件资源名按字典序；标题回退和单事件描述取 `received_at DESC, pk DESC`；多事件标题仍是现有指纹文案。
- 容量形状：单组十万事件；本窗一条、历史十万；大量小组。挂接、合并、恢复和提交后补查不把整组 Event ORM 一次物化。
- 事务：中间批失败回滚整组；部分组成功后，已成功组已经调度分派，`last_execute_time` 不推进，重跑不产生第二条活跃告警、不漏成员。
- 恢复：新建与更新、RECOVERY/CLOSED、来源隔离、唯一回退在完整候选集上有歧义则不关联、相等时间不恢复、更晚时间恢复、无 external_id 保持现有行为。
- 交接：补查结束后、组提交前恢复入库且接入未匹配，提交后 Outbox 补上。覆盖同一 `window_end` 的重复入队不二次调度、投递失败重试、重试耗尽、并发关闭。行锁和提交可见性在支持行锁的数据库上验证。
- 会话：终点不随组处理耗时变化；本轮已恢复的不转正；截止后仍 observing 的由现有 TimeoutChecker 转正。observing 不在聚合循环里分派。
- 容量数字本次不假装已经测过。

## Out of Scope

- 跨 Beat 游标、持久化薄表、连续消费、积压追赶。
- 第二套分组器、异步补挂 CREATED、硬截断、半成品 Alert。
- 为加载过程加可重复读快照或第二套资格校验。
- Instant、缺失检测、策略调度公平性、Celery 池和容器配额。
- 按历史截止时刻重演会话通知。
- 重做 Outbox 投递框架。恢复补查只增加一种 kind。

## Confirmation

确认这一版即可进入实现：统一分批；一轮一个 `[start, end)`；完整组事务；摘要一次取出；资源名和标题回退顺序按上面定死；失败组不阻止已成功组分派，但阻止推进 `last_execute_time`；Outbox 键为 `recovery-reattach:{alert_pk}:{window_end_iso}`；会话终点锚在 `window_end`，恢复仍优先于本轮超时转正。
