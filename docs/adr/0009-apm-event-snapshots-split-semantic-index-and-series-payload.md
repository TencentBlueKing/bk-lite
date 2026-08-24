# ADR 0009：APM 事件快照拆分语义索引与指标序列载荷

Status: accepted

APM 的每次告警状态变化都必须留下不受后续策略修改、遥测保留期和实时查询影响的历史证据。我们选择按 Event 一一创建不可变快照：PostgreSQL 保存策略、对象、评估、阈值、Trace 检索上下文和组织等可解释语义，压缩对象存储只保存体积较大的指标序列；通知投递另走 APM outbox。相比把整个生命周期反复覆盖到一个对象，逐 Event 索引能用 `event_id` 数据库唯一约束仲裁并发追加，也能独立表达 payload 的 `pending/available/unavailable/expired` 状态。

Event Snapshot 只解释状态变化事件，不承担“每次策略扫描一个点”的 Alert 生命周期趋势；后者由与 Alert 一对一的告警指标快照集合承担。

对象存储是运行期可降级依赖。上传前在语义行中保留最多 240 点的有界 staging；上传成功立即清空，失败则保留到有界补偿成功或保留期到期。上传失败不回滚已经成立的 Alert/Event 和 PostgreSQL 语义快照；保留期清理只有在对象删除成功后才标记 `expired`，删除失败保留索引供后续任务重试，避免形成不可追踪的孤儿对象。遥测或 payload 保留期已过时仍展示语义快照并明确 `expired`，禁止重新查询当前策略或 VictoriaTraces 伪造历史趋势。这一取舍接受短期内可能没有趋势序列，以避免 MinIO 故障吞掉告警事实，并保持 ADR 0004 的 APM source-of-truth 与 ADR 0006 的控制面/遥测面分离。
