# APM 告警能力

APM 独立拥有策略、Alert 生命周期、Event、告警指标快照、事件原始证据和通知投递记录。Monitor 是交互和模型设计的参照，但 APM 不复用 Monitor 的业务表。

模块入口：[[apm-architecture.md#职责与边界]] · [[apm-product.md#告警]] · [[apm-function-list.md#3. 可靠性]]

## 长期契约

- 策略指标类型是 `error_rate / error_count / p50 / p75 / p90 / p95 / p99 / latency_avg / latency_max / slow_request_count / slow_request_rate / apdex / throughput / no_traffic / slo_burn_rate`；禁止任意表达式、MonitorObject、采集插件、LogSQL 和日志组。`request_count` 只作前置门槛，不进常规条件指标。
- 一条策略最多 3 条常规条件，必须全部满足；级别合成取最轻的一档。前置条件最多 2 条，只做绝对门槛，不满足时走恢复。非锚点缺数据保持活动告警且连续计数不变。策略内不同对照窗不超过 2 个。
- 作用范围是单服务、2..20 个服务或一个应用。端点模式是服务整体、手选或全部端点；全部端点每轮从 `service_endpoints` 展开，消失端点连续 `recover_after` 轮后结束告警并删状态。实例维度是不拆或按实例。每个服务的目标上限 100。单服务策略不按组织交集跳过；多服务和应用范围里，与策略组织不相交的服务本轮跳过，试算记 `service_not_visible`。
- 目标类型可以是入口或下游依赖。依赖不按端点或实例拆，指标不含 Apdex 和无流量；空列表每轮按调用量展开，上限 40。
- `slo_burn_rate` 绑定一个 SLO 和一组长短窗。燃烧率是 `(1 − 合规率) / (1 − 目标)`，两窗都越过阈值才命中，级别取较轻的一档。长窗无样本记 `no_data`，短窗无样本记 `insufficient_samples`。删除 SLO 时停用引用它的策略并结束活动告警。
- 比较基准是 `absolute / previous_window / offset_hours / offset_days / baseline_days`（旧值 `offset_1h / offset_24h` 仍可读）。`baseline_days` 的 N 为 2..7，对照是近 N 天同窗的算术均值；可用天数不足 `⌈N/2⌉` 记 `missing_baseline`（reason `baseline_days_insufficient`）。`compare_value_kind=sigma` 只对 `baseline_days` 且 N ≥ 3 开放，比较值是 `(当前 − 均值) / 样本标准差`，阈值 k 为 0.5..5，可用天数不足 3 同样记 `missing_baseline`。相对计算用等长 RED 窗，不用 MetricsQL。`percent` 在对照值为 0 或对照窗样本不足时记 `missing_baseline` 并保持活动告警；错误率、慢请求占比、Apdex 和时延族可设最低请求数，不足记 `insufficient_samples`，同样保持态。试算是只读内部端点，不写告警、事件、快照或目标状态。`replay_hours` 只允许 0 或 24；为 24 时每个目标追加按汇聚周期分桶的只读回放，返回窗口数、命中数和命中时刻，不读前轮状态，也不写任何记录。
- 基线按天查询失败并回退到逐日查询时，该轮评估的目标上限从 100 收到 20。
- 策略创建必填所属组织，列表 / 详情按策略组织 fail-closed；存量策略从当时服务组织回填，之后改服务组织不改写策略组织。
- Alert / Event 的 `organizations` 在首次生成时从当时策略组织快照，之后不随服务或策略组织变更改写。已有告警组织不变。
- Alert 状态统一为 `active / recovered / closed`；Event 动作统一为 `triggered / escalated / claimed / assigned / reassigned / recovered / closed`。Alert 聚合完整生命周期，Event 只记录不可变状态变化。
- 空处理人的活跃告警支持认领与分派；已有处理人的活跃告警由当前处理人转派，整表替换 `handlers`。认领 / 分派 / 转派收敛到 `DjangoApmAlertService`，与处理人名单同一事务写入 `claimed` / `assigned` / `reassigned` Event，不走评估写事件入口，不建 Event Snapshot，不上指标图。空单不能转派。手工关闭：没有处理人时具备操作权限即可关；已有处理人时只有当前处理人（id 或 username）能关，其他人 409 且状态不变。已结束告警保持幂等返回。策略删除和自动恢复不走这条限制。
- 手工分派与转派对 `delivery_mode=message` 且 `recipient_mode=system_user` 的目标建 outbox，接收人为本次 `handlers`；转派出箱键按次唯一，不得复用首次分派键。`recipient_mode=none` 与告警中心副本不发。创建与认领不发分派通知。
- 告警列表与分布图 `my_alert=1` 在当前组织可见集合上再筛处理人包含当前用户（id 或 username）的记录，不靠 `operator`。分布图只统计 `triggered` / `escalated` / `recovered` / `closed`，不含 `claimed` / `assigned` / `reassigned`。
- 策略处理人可空、多选，必须是该策略所属组织内未禁用用户；组织变更后越界处理人拒绝。
- 每个 Alert 只有一份告警指标快照。自触发扫描起至自动恢复扫描止，每次成功策略扫描追加一个阈值对比点；点类型与 Monitor 一致使用 `event / info / no_data`，以扫描时间幂等。人工关闭不是策略扫描，不追加点。
- 快照点固化当次评估值、当时阈值、数据状态和可选 Event 关联。相对计算再记下 `current_value`、`baseline_value` 和 `result_unit`；`value` 仍是和阈值比较的数。无数据点没有伪造的数值；数据恢复后的点使用当前数值阈值，不沿用 `no_data` 条件。
- 告警详情主趋势只读取告警指标快照，一个点表示一次策略扫描；需要诊断时再按所选 Event 读取更细的原始证据。两者都不得用当前策略或实时 VictoriaTraces 重建历史。
- 所有策略、Alert、Event、快照与投递读取均按当前组织 fail-closed。通知投递是可变、可补偿记录，不属于不可变快照；告警中心副本不得回写 APM。
- 策略修改只影响未来评估并重置目标计数；策略删除使用可空关系保留历史 Alert、Event 与快照。
- 当前模型不提供旧单阈值、旧周期、旧通知字段或旧聚合状态的兼容读写。

## 事实入口

- 变更设计：`specs/changes/apm-policy-conditions-and-scope/spec.md`（implemented）；先前 `specs/changes/apm-policy-alert-snapshot/spec.md`
- 相对计算与试算：`specs/changes/apm-alert-calc-enrichment/spec.md`
- 事件原始证据存储：`docs/adr/0009-apm-event-snapshots-split-semantic-index-and-series-payload.md`
- 生产实现：`server/apps/apm/services/{policies,alerts,metric_snapshots,snapshots}.py`
- 页面实现：`web/src/app/apm/events/{policies,alerts}/`
