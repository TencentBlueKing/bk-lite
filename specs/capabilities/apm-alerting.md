# APM 告警能力

APM 独立拥有策略、Alert 生命周期、Event、告警指标快照、事件原始证据和通知投递记录。Monitor 是交互和模型设计的参照，但 APM 不复用 Monitor 的业务表。

模块入口：[[apm-architecture.md#职责与边界]] · [[apm-product.md#告警]] · [[apm-function-list.md#3. 可靠性]]

## 长期契约

- 策略只表达 APM Service、Endpoint、必选环境和受控版本维度，只允许 `error_rate / p95 / p99 / throughput / no_traffic`；禁止任意表达式、MonitorObject、采集插件、LogSQL 和日志组。
- 策略创建必填所属组织，列表 / 详情按策略组织 fail-closed；存量策略从当时服务组织回填，之后改服务组织不改写策略组织。
- Alert / Event 的 `organizations` 在首次生成时从当时策略组织快照，之后不随服务或策略组织变更改写。已有告警组织不变。
- Alert 状态统一为 `active / recovered / closed`；Event 动作统一为 `triggered / escalated / claimed / assigned / recovered / closed`。Alert 聚合完整生命周期，Event 只记录不可变状态变化。
- 空处理人的活跃告警支持认领与分派；认领 / 分派收敛到 `DjangoApmAlertService`，与处理人名单同一事务写入 `claimed` / `assigned` Event，不走评估写事件入口，不建 Event Snapshot，不上指标图。有处理人后本期不可再分派，关闭规则不变。
- 手工分派对 `delivery_mode=message` 且 `recipient_mode=system_user` 的目标建 outbox，接收人为本次 `handlers`；`recipient_mode=none` 与告警中心副本不发。创建与认领不发分派通知。
- 告警列表与分布图 `my_alert=1` 在当前组织可见集合上再筛处理人包含当前用户（id 或 username）的记录，不靠 `operator`。分布图只统计 `triggered` / `escalated` / `recovered` / `closed`，不含 `claimed` / `assigned`。
- 策略处理人可空、多选，必须是该策略所属组织内未禁用用户；组织变更后越界处理人拒绝。
- 每个 Alert 只有一份告警指标快照。自触发扫描起至自动恢复扫描止，每次成功策略扫描追加一个阈值对比点；点类型与 Monitor 一致使用 `event / info / no_data`，以扫描时间幂等。人工关闭不是策略扫描，不追加点。
- 快照点固化当次评估值、当时阈值、数据状态和可选 Event 关联。无数据点没有伪造的数值；数据恢复后的点使用当前数值阈值，不沿用 `no_data` 条件。
- 告警详情主趋势只读取告警指标快照，一个点表示一次策略扫描；需要诊断时再按所选 Event 读取更细的原始证据。两者都不得用当前策略或实时 VictoriaTraces 重建历史。
- 所有策略、Alert、Event、快照与投递读取均按当前组织 fail-closed。通知投递是可变、可补偿记录，不属于不可变快照；告警中心副本不得回写 APM。
- 策略修改只影响未来评估并重置目标计数；策略删除使用可空关系保留历史 Alert、Event 与快照。
- 当前模型不提供旧单阈值、旧周期、旧通知字段或旧聚合状态的兼容读写。

## 事实入口

- 变更设计：`specs/changes/apm-policy-alert-snapshot/spec.md`
- 事件原始证据存储：`docs/adr/0009-apm-event-snapshots-split-semantic-index-and-series-payload.md`
- 生产实现：`server/apps/apm/services/{policies,alerts,metric_snapshots,snapshots}.py`
- 页面实现：`web/src/app/apm/events/{policies,alerts}/`
