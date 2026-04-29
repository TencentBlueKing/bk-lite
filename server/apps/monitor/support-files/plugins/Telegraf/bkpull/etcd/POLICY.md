# Etcd 告警说明

## 文档说明

本文档说明 Etcd 监控默认提供的告警模板。这些告警主要覆盖以下常见运维风险：

- Leader 不稳定或无法选主
- Peer 通信异常
- Backend 配额逼近上限或碎片过高
- WAL 与 Backend 磁盘延迟升高
- Raft 提案失败、积压或应用落后
- 慢应用、慢一致性读
- 客户端 RPC 失败率升高

这些告警用于帮助使用者在 etcd 出现异常征兆时尽早介入，避免问题进一步影响集群稳定性和业务读写。

## 使用建议

- 当前阈值为通用默认值，适合作为 etcd 接入后的初始告警基线。
- 生产环境中应结合集群规模、磁盘性能、业务峰值和节点数量进行二次调优。
- 如果某些集群承担高频 Watch、突发写入或跨地域部署场景，建议单独调整阈值，避免误报或漏报。

## 告警模板

| 告警名称 | 关联指标 | 检测算法 | 触发阈值 | 指标含义 | 告警详细说明 | 处置建议 |
| --- | --- | --- | --- | --- | --- | --- |
| Etcd 集群无 Leader | `etcd_server_has_leader_gauge` | `last_over_time` | `critical: != 1` | 当前成员是否能观察到集群 Leader | 当实例无法观察到 Leader 时触发。该问题通常意味着集群正处于异常选主、网络分区或严重故障状态，可能已经影响写入可用性。 | 立即检查成员存活状态、节点间网络连通性、时钟同步和选主日志，优先恢复多数派。 |
| Etcd Leader 切换频繁 | `etcd_server_leader_changes_seen_total_counter_rate` | `avg` | `critical: >= 0.1` `warning: >= 0.03` | 最近 5 分钟 Leader 切换速率 | Leader 持续频繁切换通常不是单点瞬时抖动，而是网络、磁盘、CPU 抢占或时钟问题在反复触发选举。长期存在会显著影响写入稳定性。 | 检查网络抖动、节点负载、磁盘延迟和时钟同步，确认是否存在单个不稳定成员拖累集群。 |
| Etcd 心跳发送失败 | `etcd_server_heartbeat_send_failures_total_counter_rate` | `avg` | `critical: >= 0.1` `warning: >= 0.01` | Leader 心跳发送失败速率 | 心跳发送失败会直接影响 Follower 对 Leader 的感知，进一步引发误选举、复制延迟和请求抖动。 | 检查 Peer 网络、端口可达性、TLS 证书有效性和节点间丢包情况。 |
| Etcd Backend 配额使用率过高 | `etcd_backend_allocated_usage_percent` | `last_over_time` | `critical: >= 90` `warning: >= 80` | Backend 已分配空间占配额的比例 | 已分配空间接近配额上限时，集群写入会逐步进入高风险区，最终可能因 quota 耗尽导致写入失败。 | 尽快评估 compact/defrag、历史数据清理或扩容方案，并关注键数量与碎片率变化。 |
| Etcd Backend 急需整理 | `etcd_backend_urgent_defrag` | `last_over_time` | `critical: == 1` | Backend 是否已达到紧急整理阈值 | 该告警用于快速标识已分配空间达到预警阈值的实例，通常意味着 defrag 已不再是优化项，而是容量风险处置项。 | 在业务低峰期尽快安排 compact/defrag，并确保磁盘与业务侧有足够缓冲空间。 |
| Etcd Backend 碎片率过高 | `etcd_backend_fragmentation_percent` | `last_over_time` | `critical: >= 50` `warning: >= 30` | 已分配空间中未被有效使用的比例 | 碎片率过高会造成磁盘浪费、内存放大和 Backend 容量误报警，也往往意味着 compact/defrag 不及时。 | 检查历史版本回收是否正常，结合配额使用率与键数量安排 defrag。 |
| Etcd WAL fsync 延迟过高 | `etcd_disk_wal_fsync_p99_seconds` | `avg` | `critical: >= 0.05` `warning: >= 0.02` | WAL 刷盘 P99 延迟 | WAL fsync 是写路径关键步骤。P99 延迟持续升高时，写请求提交时间通常也会同步恶化。 | 检查磁盘 IOPS、延迟、宿主机争用和云盘性能限制，确认是否需要迁移到更高性能存储。 |
| Etcd Backend Commit 延迟过高 | `etcd_disk_backend_commit_p99_seconds` | `avg` | `critical: >= 0.1` `warning: >= 0.05` | Backend Commit P99 延迟 | Backend Commit 延迟偏高意味着 BoltDB 提交过程正在成为瓶颈，会拖慢提案应用与整体状态机推进。 | 检查磁盘性能、碎片率、快照/压缩活动以及系统级 I/O 抢占。 |
| Etcd 提案失败率过高 | `etcd_server_proposals_failed_total_counter_rate` | `avg` | `critical: >= 1` `warning: >= 0.1` | Raft 提案失败速率 | 提案失败直接反映一致性提交链路异常。若持续升高，说明写路径不只是变慢，而是已经开始失败。 | 结合 Leader 状态、心跳失败、Peer 发送失败和 WAL/Commit 延迟一起分析，优先判断是否为集群性故障。 |
| Etcd 提案排队积压 | `etcd_server_proposals_pending_gauge` | `last_over_time` | `critical: >= 32` `warning: >= 8` | 当前等待提交的提案数量 | Pending 持续堆积说明提案进入系统后无法及时完成提交，常见原因是 Leader 压力过高、磁盘慢或网络复制受阻。 | 检查写入突增、Leader 负载、磁盘延迟和 Follower 复制健康度。 |
| Etcd 提案应用落后 | `etcd_server_proposals_apply_lag` | `last_over_time` | `critical: >= 128` `warning: >= 32` | 已提交与已应用提案之间的差值 | 该值持续扩大说明状态机 apply 路径跟不上 commit 路径，会进一步影响一致性读、Watcher 通知和整体稳定性。 | 检查 apply 慢事件、Backend Commit 延迟、快照/压缩行为以及实例 CPU/内存压力。 |
| Etcd 慢应用请求增多 | `etcd_server_slow_apply_total_counter_rate` | `avg` | `critical: >= 1` `warning: >= 0.1` | Slow apply 事件速率 | 表示状态机应用流程已经出现明显性能退化，通常意味着 Backend 写盘或内部锁竞争异常。 | 检查磁盘、CPU、内存、Backend 大小和 compaction/defrag 是否影响 apply。 |
| Etcd 慢读索引增多 | `etcd_server_slow_read_indexes_total_counter_rate` | `avg` | `critical: >= 1` `warning: >= 0.1` | Slow read index 事件速率 | Read Index 是线性一致性读的重要路径。慢读索引增多时，读请求延迟通常会明显升高。 | 检查 Leader 压力、网络抖动、Follower 同步状态和客户端读流量峰值。 |
| Etcd Read Index 失败 | `etcd_server_read_indexes_failed_total_counter_rate` | `avg` | `critical: >= 0.1` `warning: >= 0.01` | Read Index 失败速率 | Read Index 失败表示线性一致性读路径已经出现错误，不再只是慢，而是存在功能异常风险。 | 检查 Leader 选举稳定性、Peer 连通性和请求错误日志。 |
| Etcd Peer 发送失败 | `etcd_network_peer_sent_failures_total_counter_rate` | `avg` | `critical: >= 0.1` `warning: >= 0.01` | Peer 间发送失败速率 | Peer 发送失败会影响复制、日志同步和心跳传播，是集群一致性风险的重要前置信号。 | 检查节点间网络、TLS、连接复位和中间网络设备异常。 |
| Etcd RPC 失败率过高 | `etcd_rpc_failed_rate` | `avg` | `critical: >= 5` `warning: >= 1` | 非 OK unary RPC 的失败速率 | 该告警直接反映客户端访问层面的失败已经明显上升，说明 etcd 已经开始对外暴露错误。 | 检查客户端错误码分布、服务端日志、资源压力以及上游调用突增情况。 |

## 告警判定方式说明

- `last_over_time` 适用于状态类、积压类指标，强调“当前是否持续异常”。
- `avg` 适用于失败率、延迟、异常事件频率等指标，用于降低瞬时抖动造成的误报。
- `warning` 阈值主要用于提前介入，`critical` 阈值通常表示已经接近或进入明显影响服务的状态。

## 重点告警建议优先启用

如果需要先启用一组最关键的 etcd 告警，建议优先启用以下模板：

- `Etcd 集群无 Leader`
- `Etcd Backend 配额使用率过高`
- `Etcd Backend 急需整理`
- `Etcd WAL fsync 延迟过高`
- `Etcd 提案排队积压`
- `Etcd 提案应用落后`
- `Etcd RPC 失败率过高`

## 使用建议

- 如果希望先启用一组高价值告警，建议优先开启“无 Leader”“配额使用率过高”“WAL fsync 延迟过高”“提案排队积压”“提案应用落后”这几类。
- 如果集群规模较小或业务流量较低，可适当提高部分频率型告警的阈值，减少误报。
- 如果集群承载核心控制面或高频写入业务，建议保守调低关键延迟和失败率阈值，提高告警灵敏度。
