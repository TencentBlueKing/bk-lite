# APM 告警能力

APM 独立拥有策略、Alert 生命周期、Event、告警指标快照、事件原始证据和通知投递记录。Monitor 是交互和模型设计的参照，但 APM 不复用 Monitor 的业务表。

模块入口：[[apm-architecture.md#职责与边界]] · [[apm-product.md#告警]] · [[apm-function-list.md#3. 可靠性]]

## 长期契约

- 策略只表达 APM Service、Endpoint、必选环境和受控版本维度，只允许 `error_rate / p95 / p99 / throughput / no_traffic`；禁止任意表达式、MonitorObject、采集插件、LogSQL 和日志组。
- Alert 状态统一为 `active / recovered / closed`；Event 动作统一为 `triggered / escalated / recovered / closed`。Alert 聚合完整生命周期，Event 只记录不可变状态变化。
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
