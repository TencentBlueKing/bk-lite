# APM 告警能力

APM 独立拥有策略、Alert 生命周期、Event、Event Snapshot 和通知投递记录。Monitor、Log 与告警中心只提供机制参考或接收副本，不能成为 APM 状态事实源，也不能与 APM 共用业务表。

## 长期契约

- 策略只表达 APM Service、Endpoint、必选环境和受控版本维度，只允许 `error_rate / p95 / p99 / throughput / no_traffic`；禁止任意表达式、MonitorObject、采集插件、LogSQL 和日志组。
- Alert 状态统一为 `active / recovered / closed`；Event 动作统一为 `triggered / escalated / recovered / closed`。Alert 聚合生命周期，Event 只记录不可变状态变化。
- 每个 Event 必须有以 `event_id` 唯一约束仲裁的快照。数据库保存不可变策略、对象、评估、组织和 Trace 检索上下文；指标序列通过压缩对象载荷异步补齐。
- 对象存储失败不能回滚 Alert/Event。失败序列保留有界 DB staging 供补偿，成功后立即清空；到期后清理 staging/payload 并保留可解释语义索引及 `expired` 状态。
- 告警详情趋势只读取用户所选 Event 的持久化快照，必须展示当时阈值线和事件点。不得用当前策略或实时 VictoriaTraces 查询冒充历史证据。
- 所有策略、Alert、Event、Snapshot 与投递读取均按当前组织 fail-closed。通知投递是可变、可补偿记录，不属于不可变快照；告警中心副本不得回写 APM。
- 策略修改只影响未来评估并重置目标计数；策略删除使用可空关系保留历史 Alert/Event/Snapshot。

## 事实入口

- 变更设计与迁移：`specs/changes/apm-policy-alert-snapshot/spec.md`
- 快照存储决策：`docs/adr/0009-apm-event-snapshots-split-semantic-index-and-series-payload.md`
- 生产实现：`server/apps/apm/services/{policies,alerts,snapshots}.py`
- 页面实现：`web/src/app/apm/events/{policies,alerts}/`
