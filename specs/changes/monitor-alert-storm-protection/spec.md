# 监控告警兼容性资源保护设计

Status: proposed

Implementation: Slice D（实例移除生命周期收敛）已实现；Slice A～C 保持 proposed，本次最小影响交付不启用。

## 1. 约束与结论

本设计遵守两个硬约束：

1. 除用户明确要求的“实例移除时关闭关联活动告警”外，不改变现有业务语义：策略配置、扫描周期、补偿窗口、Alert 聚合规则、Event/快照产生频率、通知时机、恢复逻辑和接口响应结构保持不变；
2. 不改变现有部署流水线：继续使用 `scan_policy_task`、默认 Celery 队列、现有 threads Worker、Supervisor 配置和 Server 部署单元，不新增独立容器、队列或环境变量。

因此，本方案可以消除代码层无界内存聚合、全表序列化和重试重复写入，使单次扫描的内存与事务规模有上限；但不能消除“业务要求永久保留每轮 Event/快照”带来的数据库长期线性增长，也不能提供独立 cgroup 级故障隔离。

约 170 个 Pod、每分钟一次、连续三天仍会合法产生约 73 万条逐轮 Event。若要求这些 Event 全部保留，任何实现最终都会消耗持续增长的数据库空间。要彻底消除长期存储风险，必须另行接受 Event 合并、保留期或存储扩容中的至少一项；本 change 不擅自作该决定。

## 2. 现状事故链

当前 `MonitorPolicyScan` 在构造时建立完整实例映射、父实例映射、基准映射和活动告警 QuerySet，运行时又同时持有阈值告警、正常事件、无数据事件、Event ORM 对象、新 Alert 和快照原始数据。

主要资源放大点：

1. `_collect_events()` 构造三份全量列表，随后 `alert_events + no_data_events` 再复制一份；
2. `EventAlertManager` 同时建立新旧 Event 列表、Alert 映射、Event ORM 列表和原始数据列表；
3. `SnapshotRecorder` 把所有活动告警及本轮 Event 再次物化，并持续读写单行不断增长的 `snapshots` JSON；
4. 一个任务最多循环补偿 30 个周期，前一轮释放不及时会继续推高 threads Worker 的 RSS；
5. `MonitorAlertViewSet` 的 `type=count` 分支先序列化完整 QuerySet，再返回 count 和完整 results；
6. Celery Singleton 只能减少正常重复投递，不能作为数据库幂等保证；
7. 线程池中的 Python 堆、DataFrame 和 ORM 对象即使释放，也不保证 RSS 立即归还操作系统。

这更接近“高基数任务的无界分配与常驻进程内存高水位”，不能仅用查找传统对象引用泄漏来解决。

## 3. 兼容性不变量

### 3.1 正常业务结果必须等价

1. 同样的策略、指标响应和计划时间，一个扫描窗口完成后新旧实现生成相同的 Alert、Event、快照和通知；
2. 无数据 Alert 继续按“策略 + 监控实例”聚合，阈值 Alert 继续按指标实例区分；
3. 一个持续无数据的指标维度每个扫描窗口仍生成现有业务要求的 Event 和快照；
4. `MAX_BACKFILL_SECONDS` 和 `MAX_BACKFILL_COUNT` 的最终补偿结果不变；
5. API 字段、筛选、排序、分页参数和权限结果不变；
6. 正常容量内不丢弃、合并、抽样或延迟通知。
7. 页面手动删除和自动清理超时都属于实例移除：关闭关联活动告警，但保留 Alert、Event 和快照历史；仅标记 `is_active=False` 不关闭告警。

### 3.2 实现必须有界

1. 任一落库事务最多处理固定批次，不随策略实例总数增长；
2. 同一时刻只保留一个批次的 Event、ORM 对象和原始数据；
3. 同一策略、同一计划窗口、同一告警类型和同一指标身份最多落一条 Event；
4. 任务中断后从 checkpoint 续跑，不重新写入已提交批次；
5. 查询统计不得为取得 count 而序列化完整结果；
6. 达到内存、耗时或响应大小安全阈值时停止当前任务并保留续跑状态，不继续扩大资源占用。

第 6 条只在异常容量下生效，属于可用性熔断：业务结果延迟但不改变，后续任务从 checkpoint 继续完成。

## 4. 深模块与兼容接口

保留 Celery 任务名称和调用方式，任务内部统一进入一个深模块：

```python
@dataclass(frozen=True)
class ScanSummary:
    policy_id: int
    scheduled_at: datetime
    processed: int
    created_alerts: int
    created_events: int
    has_more: bool
    status: str  # succeeded | duplicate | continued | failed


class BoundedMonitorPolicyScan:
    @classmethod
    def run(cls, policy_id: int, scheduled_at: datetime) -> ScanSummary:
        ...
```

`scan_policy_task(policy_id)` 的 interface 不变。模块内部隐藏实例游标、批次查询、窗口幂等、事务提交、快照写入和续跑；Celery 调用者不再编排 `AlertDetector`、`EventAlertManager` 和 `SnapshotRecorder` 的全量中间结果。

内部保留一个真实 seam：VictoriaMetrics adapter。生产 adapter 发出与现有逻辑等价的分片查询，测试 adapter 返回确定性指标；Django ORM 直接作为隔离数据库实现，不额外增加仓储 interface。

## 5. 有界执行设计

### 5.1 固定一行的扫描 checkpoint

新增一对一 `MonitorPolicyScanCheckpoint`，每个策略最多一行：

- `scheduled_at`：正在处理的计划窗口；
- `cursor`：已提交的稳定实例/指标游标；
- `phase`：threshold/no_data/recovery/snapshot/completed；
- `lease_expires_at`：崩溃后的接管时间；
- 本窗口累计处理数和错误摘要。

认领时使用 Django ORM 的 `select_for_update()`。计划窗口已完成时返回 duplicate；lease 未过期时不并发；lease 过期后从 cursor 继续。完成后覆盖同一行，不产生按扫描次数增长的运行记录。

该表只控制执行进度，不改变 `MonitorPolicy.last_run_time` 的业务含义。只有窗口所有 phase 完成后才推进 `last_run_time`。

### 5.2 Event 窗口幂等

为 Event 增加与现有业务一一对应的确定性 `evaluation_key`：

```text
policy_id + scheduled_at + alert_type + metric_instance_id
```

数据库建立唯一约束。正常首次执行仍创建原有 Event；重复消息、并发 Worker或中断重试命中同一键时复用已有 Event，不产生业务外的重复数据。历史 Event 无需回填该键，新写入路径开始生效。

无数据 Event 仍以指标维度为事件身份，不能因为 Alert 按监控实例聚合而误合并同一 Pod 下不同维度的逐轮 Event。

### 5.3 分批扫描

默认批次 200，可作为代码内受控配置：

1. 通过稳定的 `(monitor_instance_id, metric_instance_id)` 游标读取一批基准；
2. VictoriaMetrics adapter 对该批身份执行语义等价的查询；
3. 只加载该批可能命中的活动 Alert 字段；
4. 在内存中计算该批阈值、无数据和恢复结果；
5. 单事务写入该批 Alert、Event、原始数据和 checkpoint；
6. 窗口全部完成后进入 notification phase，按 `scheduled_at` 和通知游标分批读取本窗口需要通知的 Alert，执行与当前相同的通知；checkpoint 不保存无界 ID 列表；
7. 删除批次局部引用，进入下一批。

公式策略或聚合算法只有在能证明分片查询与原查询结果等价时才分片；不能证明时继续执行一次查询，但用迭代解析和紧凑身份集合避免复制响应。不得为了省内存改变聚合结果。

### 5.4 补偿窗口切片

保留最多 30 个周期的最终补偿语义，但一个 `scan_policy_task` 调用只在以下任一条件满足前继续：

- 达到单任务软时限；
- 达到 RSS 高水位；
- 完成当前补偿窗口。

触发前两项时安全提交 checkpoint 并返回 `continued`。下一次现有 Beat 调度会继续剩余窗口。不得在同一任务中越过资源保护强行追赶，也不新增队列或修改路由。

### 5.5 快照存储内部归一化

现有 `MonitorAlertMetricSnapshot.snapshots` 是持续增长的 JSON 数组；每次 append 都要读取、复制和写回整行，是单个长期活动 Alert 的独立内存风险。

新增 `MonitorAlertMetricSnapshotEntry` 明细表，每条现有逻辑快照存一行，Alert、类型、时间和 Event 建索引。写入改为批量 insert，读取层按现有顺序组装原有 `snapshots` 字段，因此页面和接口结构不变。

迁移采用懒迁移：读取旧 JSON 时兼容，首次写入时分批转成 Entry，完成后标记 migrated。schema migration 只建表，不扫描历史数据。旧 JSON 在确认迁移成功前保留，回滚仍可读取。

如果单个详情请求本身包含超大快照数组，服务端使用流式 JSON 输出维持原响应结构，避免在 Server 内存中同时物化全部明细；前端行为不作调整。

## 6. 查询路径优化

### 6.1 `type=count` 保持响应兼容

当前接口同时返回 `count` 和完整 `results`，不能直接删除 results。优化分两步：

1. `count` 使用 QuerySet `count()`，不触发 serializer；
2. `results` 使用数据库 iterator 和流式 JSON 编码，字段、排序及权限结果保持一致。

普通分页继续使用现有参数与响应结构，但禁止内部把 QuerySet 转为无界 list。图表调用方若实际上只读取 count，可在后续单独迁移到聚合接口；本 change 不强制修改 Web。

### 6.2 只读取必要字段

- 活动 Alert 映射只查询批次身份需要的 id、身份、级别和状态；
- 权限策略 ID 使用子查询，不先转换成完整 Python list；
- 原始数据和快照使用 iterator/chunked fetch；
- 日志只输出数量和固定数量样本，不输出完整 Event 或 VM payload。

这些修改不改变返回值，只减少 Python 对象数量和日志 I/O。

## 7. 异常容量保护

不新增产品配置和 UI。使用保守的代码默认值保护共享进程：

- 批次：200；
- 单事务最多 Event：500；
- 单任务软时限：当前调度周期的 80%，上限 45 秒；
- Worker RSS 高水位：从现有容器可用内存计算，预留至少 25%；
- VM 单响应体上限：按现网正常峰值压测后确定。

达到限制后仅停止本次循环、保存 checkpoint 并记录结构化错误，不自动关闭策略、不恢复活动告警、不把查询失败解释为无数据。后续现有调度继续处理。

若相同策略连续无法前进，按固定退避降低重试频率，避免一个高基数策略永久占满 threads Worker。该状态记录在 checkpoint 和日志中，不改变现有页面或通知。

## 8. 实例移除与告警生命周期联动

### 8.1 状态语义

自动发现一次成功查询没有观察到实例时，现有逻辑会先设置 `is_active=False`。该状态只表示“当前不活跃”，可能来自采集延迟、网络波动或 Pod 重建；此时不关闭活动告警，无数据策略继续按现有规则工作。

只有以下两种情况属于“实例移除”：

1. 用户在页面明确执行删除实例；
2. 自动发现累计缺失达到对象清理超时，准备物理删除实例。

实例移除时关闭该实例全部 `status="new"` 的阈值和无数据 Alert。使用 `closed` 而不是 `recovered`，因为没有证据表明指标恢复健康；历史 Alert、Event、快照和通知记录不得物理删除。

### 8.2 统一删除 interface

深化现有 `MonitorInstanceRemovalService`，保留所有删除入口都调用的同一 interface：

```python
class MonitorInstanceRemovalService:
    @classmethod
    def remove(
        cls,
        instance_ids: Iterable[str],
        *,
        operator: str = "system",
        reason: str = "instance_deleted",
    ) -> RemovalResult:
        ...
```

调用规则：

- 页面 `remove_monitor_instance` 传当前用户名和 `manual_instance_deleted`；
- 自动发现超时清理传 `system` 和 `auto_cleanup_instance_deleted`；
- 兼容现有内部调用方，未传参数时采用系统删除原因。

模块内部顺序：

1. 锁定待删除实例并计算真实存在的 ID；
2. 分批锁定 `monitor_instance_id__in=removed_ids, status="new"` 的活动 Alert；
3. 设置 `status="closed"`、`end_event_time`、operator、operation log 和告警中心补偿标志；
4. 删除 `PolicyInstanceBaseline` 中对应实例的基准，并执行现有策略来源清理；
5. 清理采集配置、组织规则并物理删除实例；
6. 数据库事务提交后，按固定批次调用现有 `AlertLifecycleNotifier`，action 为 `closed`；
7. 通知失败沿用现有告警中心补偿，不回滚已经完成的实例移除。

Alert 更新必须按固定批次执行，事务提交回调只捕获当前批次最多 500 个 Alert ID，不能把一个实例集合关联的全部 ORM 对象留在内存。重复删除或重试只查询 `status="new"`，因此已经关闭的 Alert 不会重复关闭或重复通知。

### 8.3 防止关闭后重开

实例、策略来源和策略基准必须在同一删除事务中收敛。删除完成后扫描器无法再从实例范围或基准中选择该实例，因此不会下一轮重新打开无数据 Alert。

如果删除事务失败，Alert 保持活动；如果自动发现查询失败，该监控对象不会进入不活跃或删除流程，更不能关闭告警。

### 8.4 验收场景

- 页面删除一个实例：其全部活动阈值/无数据 Alert 变为 closed，历史 Event/快照仍可查询；
- 页面批量删除：每批实例不超过现有 500 上限，Alert 更新和通知同样分批；
- 自动发现一次未观察到：只设置 inactive，不关闭任何 Alert；
- 缺失达到清理超时：关闭 Alert 后删除实例，reason 为自动清理；
- 实例在超时前重新出现：恢复 active，既有告警按扫描规则恢复，不产生删除关闭；
- VM 发现查询失败、删除事务回滚或重复删除：不误关、不重复通知；
- 删除后执行下一轮策略扫描：该实例不重新产生 Alert/Event。

该联动复用现有页面入口、自动发现任务、删除模块和通知模块，不新增队列、容器或流水线步骤，也不要求新增数据库字段。

## 9. 数据库增长边界

本设计明确不执行以下动作，因为它们会改变现有业务：

- 不把重复 Event 合并为 occurrence_count；
- 不删除或缩短 Event/Alert/快照保留期；
- 不取消无数据历史补偿；
- 不降低 Event 或快照产生频率；
- 不限制用户选择全部 Pod；
- 不改变通知触发规则。

因此数据库容量仍满足：

```text
新增 Event ≈ 缺失指标维度数 × 实际扫描窗口数
```

代码层可保证增长过程不把 Celery 内存和 API 查询拖垮，但无法在磁盘无限的假设下工作。必须配置现有数据库磁盘监控和扩容阈值；如果现有运维体系没有这项能力，则“长期零事故”目标在本约束下不可证明。

## 10. 不需要调整部署流水线的发布方式

1. schema migration 仅新增 checkpoint、快照明细和 Event 唯一键结构，不扫描历史数据；
2. 发布 Server 代码，现有 Supervisor 仍以 threads pool 和原 concurrency 启动；
3. `scan_policy_task` 名称、参数、Beat 配置和 Celery 路由保持不变；
4. 通过代码内兼容开关按策略灰度新执行器，默认先覆盖高基数 Pod 策略；
5. 发现问题时关闭兼容开关回到旧执行器，新表保留且不影响旧代码；
6. 历史快照转换由正常读写懒触发，不加入 `batch_init`，不阻断启动。

这里的“无需流水线配合”指不新增部署单元、步骤、队列和参数；常规 Django migration 仍属于应用版本发布的一部分。如果当前流水线完全不执行 migration，则新增数据库幂等能力也无法安全交付，需要另行缩减设计。

## 11. 验收标准

### 11.1 业务等价

- 对固定 VM 响应执行新旧双跑，Alert、Event、快照、通知和恢复结果逐字段一致；
- 无数据 Alert 继续按策略 + Pod 聚合，Event 数量与现有规则一致；
- 阈值告警、部分恢复、全部恢复和 30 周期补偿结果一致；
- API contract 测试确认字段、排序、权限和分页不变。
- 页面删除和自动清理超时会关闭关联活动告警，单纯 inactive 不会关闭；关闭后下一轮扫描不会重开。

### 11.2 资源有界

- 10,000 Pod 场景中每批 ORM 对象不超过配置批次；
- 单次事务 Event 不超过 500，失败只重试未完成批次；
- 峰值增量 RSS 目标不超过 256 MiB，且不随历史 Event 总行数增长；
- 170 Pod、4,320 轮压测可以产生现有语义要求的约 73 万 Event，但 Celery RSS 保持稳定；
- `type=count` 不存在 `serializer(queryset, many=True)` 的一次性全量物化；
- 单 Alert 十万条快照读取和追加不复制完整历史 JSON；
- 任务在任意批次崩溃后续跑，最终结果与无崩溃执行一致且无额外重复 Event。

### 11.3 现有部署验证

- 使用现有 `--pool threads`、现有 concurrency 和默认队列完成压力测试；
- 不修改 Supervisor、Celery 路由、Beat 或容器清单；
- 监控扫描压力下登录和普通任务响应达到当前基线；
- 明确记录剩余风险：同容器 Worker 极端 OOM 仍可能影响 API，数据库空间仍随 Event 增长。

## 12. 实施切片

### Slice A：零 schema 的低风险优化

- `type=count` 改为 count + iterator 流式响应；
- 删除全量 payload 日志；
- 扫描局部列表改迭代器和批次；
- 增加任务软时限与 RSS 高水位检查。

完成条件：接口 contract 不变，10,000 Pod 峰值内存有界。

### Slice B：窗口幂等和断点续跑

- 新增 checkpoint 与 Event evaluation_key；
- 增加批次事务、过期 lease、崩溃续跑；
- 补偿周期拆分到多次现有任务执行。

完成条件：并发、重投和崩溃不产生业务外重复 Event，最终业务结果不变。

### Slice C：快照内部归一化

- 新增 SnapshotEntry；
- 兼容读取、懒迁移和流式详情响应；
- 增加长期活动 Alert 压力测试。

完成条件：十万快照的追加内存与历史条数无关，接口结果与旧 JSON 一致。

### Slice D：实例移除生命周期收敛

- 扩展统一删除 interface 的 operator 和 reason；
- 关闭活动 Alert、清理基准并在事务提交后发送关闭通知；
- 页面删除、自动超时、失败回滚和删除后不重开测试。

完成条件：所有实例移除入口产生一致关闭结果，不留下活动孤儿告警。

## 13. 决策边界

本版本是“业务和流水线零改动”的最大安全优化：可以解决 Celery 单任务内存峰值、Python RSS 高水位、全量序列化、超大快照 JSON 和重试额外重复写入。

它不能同时满足“每分钟永久新增全部 Event”与“数据库永不增长”，也不能让同一容器内的 threads Worker 获得真正资源隔离。若验收目标仍要求彻底杜绝整站事故，需要产品或运维至少开放一个最小例外：Event 保留/合并，或独立 Worker 资源隔离。
