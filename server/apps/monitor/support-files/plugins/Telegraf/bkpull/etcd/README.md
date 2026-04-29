# Etcd 监控说明

## 监控概述

Etcd 监控用于帮助使用者持续观察 etcd 集群的健康状态、容量风险、磁盘性能和一致性处理能力，适合用于以下场景：

- 日常巡检时快速判断集群是否稳定
- 容量评估时判断 Backend 空间是否接近上限
- 性能排查时判断磁盘、提案或读写路径是否出现瓶颈
- 故障定位时识别选主异常、复制异常和请求失败问题

## 监控价值

本监控对象围绕 etcd 的核心运行路径进行设计，重点覆盖以下几个方面：

- 集群是否能够稳定选主，节点间复制链路是否正常
- Backend 空间是否接近配额上限，是否存在明显碎片
- WAL 刷盘与 Backend 提交是否成为写入瓶颈
- Raft 提案是否出现失败、积压或应用落后
- 客户端访问、Peer 通信、Watcher 与压缩活动是否异常

## 功能简介

用于采集 etcd v3 集群的关键运行指标，覆盖 Leader 状态、Backend 容量与碎片、磁盘时延、Raft 提案一致性、客户端与 Peer 流量、Watcher 与压缩活动等核心场景，帮助使用者及时发现异常、评估容量风险并定位性能瓶颈。

## 接入方式

| 项目 | 内容 |
| --- | --- |
| 监控对象 | Etcd |
| 采集方式 | 由 Telegraf Pull 采集器基于 Prometheus 指标端点主动拉取采集 |
| 数据来源 | etcd 实例暴露的 `/metrics` 指标端点 |
| 默认采集地址 | `http(s)://<host>:<port>/metrics` |

## 口径说明

- 本文档中的指标均按 `instance_id` 维度聚合，因此当前“维度”列统一为 `None`。
- 频率类指标大多基于最近 5 分钟窗口计算。
- 容量类指标使用产品标准单位 `bytes`，页面会按 `B/KiB/MiB/GiB` 自动展示。
- 流量类指标使用产品标准单位 `byteps`，页面会按 `B/s`、`KiB/s`、`MiB/s` 自动展示。
- 频率类指标使用产品标准单位 `hertz`，页面会按 `Hz/KHz/MHz` 自动展示。
- `s` 类指标建议按 `ms` 或 `s` 理解其实际耗时水平。

## 建议优先关注指标

如果需要快速判断 etcd 是否处于健康状态，建议优先关注以下指标：

- `etcd_server_has_leader_gauge`：判断集群是否正常选主
- `etcd_backend_allocated_usage_percent`：判断 Backend 配额是否逼近上限
- `etcd_backend_urgent_defrag`：判断是否需要尽快执行碎片整理
- `etcd_server_proposals_pending_gauge`：判断提案是否开始积压
- `etcd_server_proposals_apply_lag`：判断状态机应用是否落后
- `etcd_disk_wal_fsync_p99_seconds`：判断写入路径是否受磁盘刷盘影响

## 快速判断思路

如果只想快速判断当前 etcd 集群是否健康，建议按下面顺序查看：

1. 先看“集群是否有主节点”，确认集群是否正常选主。
2. 再看“提案积压数”和“提案应用落后数”，确认一致性处理链路是否堵塞。
3. 然后看“后端存储使用率”和“是否需要整理碎片”，确认容量是否进入风险区。
4. 最后看 “WAL 刷盘延迟 P99” 和 “后端提交延迟 P99”，确认磁盘是否已经拖慢写入路径。

## 指标清单

### 集群状态

用于判断集群是否能够稳定选主、节点间连接是否正常，以及基础健康状态是否出现异常。

| 指标中文名 | 指标ID | 数据类型 | 单位 | 重点关注 | 指标说明 |
| --- | --- | --- | --- | --- | --- |
| 集群是否有主节点 | `etcd_server_has_leader_gauge` | Enum | `0/1` | 是否为 `1` | 判断当前成员是否能观察到 Leader。返回 `0` 往往意味着选主异常、网络分区或集群短时不可写。 |
| 当前角色 | `etcd_server_is_leader_gauge` | Enum | `0/1` | 当前是 Leader 还是 Follower | 用于确认当前成员在集群中的角色，方便排查请求是否集中在 Leader。 |
| 活跃节点连接数 | `etcd_network_active_peers_gauge` | Number | `counts` | 是否持续下降 | 表示当前成员与其他 etcd 节点间保持活跃状态的连接数量。持续下降通常意味着节点失联或复制链路异常。 |
| 主节点切换频率 | `etcd_server_leader_changes_seen_total_counter_rate` | Number | `hertz` | 是否持续偏高 | 表示最近 5 分钟 Leader 切换速率。持续偏高通常意味着网络抖动、时钟漂移或节点负载不稳定。 |
| 心跳发送失败频率 | `etcd_server_heartbeat_send_failures_total_counter_rate` | Number | `hertz` | 是否持续非零 | 表示最近 5 分钟 Raft 心跳发送失败速率。持续非零说明 Leader 到 Follower 的通信可能存在异常。 |
| 健康检查失败频率 | `etcd_server_health_failures_counter_rate` | Number | `hertz` | 是否出现明显升高 | 表示最近 5 分钟 etcd 内部健康检查失败速率，可用于辅助判断服务是否进入异常状态。 |

### 存储与碎片

用于判断 Backend 容量、碎片、键规模和内存占用情况，是容量规划和 defrag 决策的重要依据。

| 指标中文名 | 指标ID | 数据类型 | 单位 | 重点关注 | 指标说明 |
| --- | --- | --- | --- | --- | --- |
| 后端已分配空间 | `etcd_mvcc_db_total_size_in_bytes_gauge` | Number | `bytes` | 是否持续增长 | 表示 etcd Backend 当前已申请并占用的物理空间，是观察容量压力和碎片增长的基础指标。 |
| 后端实际使用空间 | `etcd_mvcc_db_total_size_in_use_in_bytes_gauge` | Number | `bytes` | 与已分配空间差距是否扩大 | 表示 Backend 中真正承载有效数据的逻辑空间，可与已分配空间结合判断碎片程度。 |
| 后端存储配额 | `etcd_server_quota_backend_bytes_gauge` | Number | `bytes` | 配额上限是否合理 | 表示 etcd Backend 的容量上限配置。接近该值时，写入可能被限制甚至失败。 |
| 后端存储使用率 | `etcd_backend_allocated_usage_percent` | Number | `percent` | 是否接近 80% 或 90% | 表示已分配空间占 Backend 配额的比例，是容量风险最直观的判断指标之一。 |
| 后端剩余容量 | `etcd_backend_remaining_bytes` | Number | `bytes` | 是否快速下降 | 表示距离 Backend 配额上限还剩余多少空间，适合用于评估短期扩容和清理窗口。 |
| 后端碎片率 | `etcd_backend_fragmentation_percent` | Number | `percent` | 是否持续升高 | 表示已分配空间中未被有效数据使用的比例。持续升高通常意味着需要执行 compact 或 defrag。 |
| 是否需要整理碎片 | `etcd_backend_urgent_defrag` | Enum | `0/1` | 是否变为 `1` | 当已分配空间达到配额 80% 及以上时返回 `1`，用于快速标识需要尽快整理碎片的实例。 |
| 键数量 | `etcd_debugging_mvcc_keys_total_gauge` | Number | `counts` | 是否快速增长 | 表示当前 MVCC 存储中的键总数。键数量增长过快通常会推高内存占用、碎片和压缩压力。 |
| 进程常驻内存 | `process_resident_memory_bytes_gauge` | Number | `bytes` | 是否持续升高 | 表示 etcd 进程当前的常驻内存占用，可结合键数量、Watcher 数量和碎片率共同判断内存风险。 |

### 磁盘时延

用于观察写入路径上的关键磁盘延迟，特别适合定位 WAL 刷盘和 Backend 提交是否成为性能瓶颈。

| 指标中文名 | 指标ID | 数据类型 | 单位 | 重点关注 | 指标说明 |
| --- | --- | --- | --- | --- | --- |
| WAL 刷盘延迟 P99 | `etcd_disk_wal_fsync_p99_seconds` | Number | `s` | 是否持续升高 | 表示最近 5 分钟 WAL fsync 延迟的 P99。它直接影响写请求提交路径，是 etcd 磁盘性能最关键的延迟指标之一。 |
| 后端提交延迟 P99 | `etcd_disk_backend_commit_p99_seconds` | Number | `s` | 是否持续升高 | 表示最近 5 分钟 Backend Commit 延迟的 P99。偏高通常说明 BoltDB 提交过程或底层磁盘 I/O 已成为瓶颈。 |
| 快照平均耗时 | `etcd_debugging_snap_save_total_avg_seconds` | Number | `s` | 是否明显高于平时 | 表示最近 5 分钟快照保存的平均耗时，可用于评估磁盘写入能力以及快照动作对业务的潜在扰动。 |

### 提案与一致性

用于评估 Raft 提案的提交、应用和线性一致性读路径是否健康，是判断 etcd 核心一致性能力的重要分组。

| 指标中文名 | 指标ID | 数据类型 | 单位 | 重点关注 | 指标说明 |
| --- | --- | --- | --- | --- | --- |
| 提案积压数 | `etcd_server_proposals_pending_gauge` | Number | `counts` | 是否持续积压 | 表示当前等待提交的 Raft 提案数量。持续积压说明 Leader 的提交链路已受到磁盘、网络或负载影响。 |
| 提案失败频率 | `etcd_server_proposals_failed_total_counter_rate` | Number | `hertz` | 是否持续升高 | 表示最近 5 分钟提案失败速率。持续升高意味着一致性提交链路存在异常。 |
| 提案提交频率 | `etcd_server_proposals_committed_rate` | Number | `hertz` | 是否明显下降 | 表示最近 5 分钟提案进入 committed 状态的速率，可用于衡量集群提交吞吐。 |
| 提案应用频率 | `etcd_server_proposals_applied_rate` | Number | `hertz` | 是否明显下降 | 表示最近 5 分钟提案被状态机应用的速率，可用于衡量最终落地吞吐。 |
| 提案应用落后数 | `etcd_server_proposals_apply_lag` | Number | `counts` | 是否持续扩大 | 表示已提交提案与已应用提案之间的差值。该值扩大说明状态机处理速度跟不上提交速度。 |
| 慢应用请求频率 | `etcd_server_slow_apply_total_counter_rate` | Number | `hertz` | 是否持续升高 | 表示最近 5 分钟慢应用事件速率。持续升高说明 apply 路径已出现明显性能退化。 |
| 读索引失败频率 | `etcd_server_read_indexes_failed_total_counter_rate` | Number | `hertz` | 是否持续非零 | 表示最近 5 分钟 Read Index 失败速率，升高说明线性一致性读路径出现异常。 |
| 慢读索引频率 | `etcd_server_slow_read_indexes_total_counter_rate` | Number | `hertz` | 是否持续升高 | 表示最近 5 分钟慢读索引事件速率，通常与 Leader 压力升高或网络抖动有关。 |

### 请求与流量

用于观察客户端访问压力、Peer 复制通信量以及 RPC 失败情况，是判断外部访问和集群内部通信状态的重要分组。

| 指标中文名 | 指标ID | 数据类型 | 单位 | 重点关注 | 指标说明 |
| --- | --- | --- | --- | --- | --- |
| 客户端请求频率 | `etcd_server_client_requests_total_counter_rate` | Number | `hertz` | 是否突增或骤降 | 表示最近 5 分钟 etcd 处理客户端请求的总速率，可用于衡量业务侧访问压力。 |
| RPC 请求频率 | `etcd_rpc_rate` | Number | `hertz` | 是否与业务峰值一致 | 表示最近 5 分钟 etcd 一元 gRPC 请求的启动速率，可用于观察 API 调用吞吐。 |
| RPC 失败频率 | `etcd_rpc_failed_rate` | Number | `hertz` | 是否明显升高 | 表示最近 5 分钟非 OK 状态的一元 RPC 失败速率，升高说明客户端访问路径已经出现明显错误。 |
| 客户端入站流量 | `etcd_network_client_grpc_received_bytes_total_counter_rate` | Number | `byteps` | 是否异常放大 | 表示最近 5 分钟来自客户端的 gRPC 入站流量，用于评估写入和查询请求的数据输入压力。 |
| 客户端出站流量 | `etcd_network_client_grpc_sent_bytes_total_counter_rate` | Number | `byteps` | 是否异常放大 | 表示最近 5 分钟返回给客户端的 gRPC 出站流量，适合观察查询返回量和 Watch 返回压力。 |
| 节点间入站流量 | `etcd_network_peer_received_bytes_total_counter_rate` | Number | `byteps` | 是否明显失衡 | 表示最近 5 分钟来自其他 Peer 的网络入站流量，是判断复制流量压力的重要指标。 |
| 节点间出站流量 | `etcd_network_peer_sent_bytes_total_counter_rate` | Number | `byteps` | 是否明显失衡 | 表示最近 5 分钟发送给其他 Peer 的网络出站流量，可用于观察复制和同步成本。 |
| 节点间发送失败频率 | `etcd_network_peer_sent_failures_total_counter_rate` | Number | `hertz` | 是否持续非零 | 表示最近 5 分钟 Peer 间发送失败速率。持续非零通常说明复制链路存在网络异常或连接中断。 |

### 监听与压缩

用于观察 Watch 长连接压力、压缩推进情况以及 KV 写删行为，适合辅助分析内存占用和事件分发压力。

| 指标中文名 | 指标ID | 数据类型 | 单位 | 重点关注 | 指标说明 |
| --- | --- | --- | --- | --- | --- |
| 监听器数量 | `etcd_debugging_mvcc_watcher_total_gauge` | Number | `counts` | 是否持续增长 | 表示当前 MVCC Watcher 总数。Watcher 过多会增加内存占用和事件分发压力。 |
| 活跃监听流 | `etcd_watch_streams_active` | Number | `counts` | 是否异常增长 | 表示当前活跃 Watch 流数量，可用于判断长连接监听压力。 |
| 压缩键处理频率 | `etcd_debugging_mvcc_db_compaction_keys_total_counter_rate` | Number | `hertz` | 是否长期偏低 | 表示最近 5 分钟 compaction 处理键的速率，用于观察压缩动作是否正常推进。 |
| 写入频率 | `etcd_mvcc_put_total_counter_rate` | Number | `hertz` | 是否明显上升 | 表示最近 5 分钟 KV 写入操作速率，可用于观察写入负载变化趋势。 |
| 删除频率 | `etcd_mvcc_delete_total_counter_rate` | Number | `hertz` | 是否明显上升 | 表示最近 5 分钟 KV 删除操作速率，可用于判断清理行为和数据变更模式。 |

## 使用建议

- 日常巡检建议优先关注“集群状态”和“提案与一致性”两组指标。
- 容量治理建议重点关注“存储与碎片”分组，尤其是配额使用率、碎片率和是否需要整理碎片。
- 性能问题建议优先结合“磁盘时延”“提案与一致性”“请求与流量”三组指标一起分析。

## 附录：指标与查询对照

如果需要排查指标口径或与查询平台中的表达式进行对照，可参考下表。

| 指标ID | 查询表达式 |
| --- | --- |
| `etcd_server_has_leader_gauge` | `etcd_server_has_leader_gauge{__$labels__}` |
| `etcd_server_is_leader_gauge` | `etcd_server_is_leader_gauge{__$labels__}` |
| `etcd_network_active_peers_gauge` | `sum(etcd_network_active_peers_gauge{__$labels__}) by (instance_id)` |
| `etcd_server_leader_changes_seen_total_counter_rate` | `rate(etcd_server_leader_changes_seen_total_counter{__$labels__}[5m])` |
| `etcd_server_heartbeat_send_failures_total_counter_rate` | `rate(etcd_server_heartbeat_send_failures_total_counter{__$labels__}[5m])` |
| `etcd_server_health_failures_counter_rate` | `rate(etcd_server_health_failures_counter{__$labels__}[5m])` |
| `etcd_mvcc_db_total_size_in_bytes_gauge` | `etcd_mvcc_db_total_size_in_bytes_gauge{__$labels__}` |
| `etcd_mvcc_db_total_size_in_use_in_bytes_gauge` | `etcd_mvcc_db_total_size_in_use_in_bytes_gauge{__$labels__}` |
| `etcd_server_quota_backend_bytes_gauge` | `etcd_server_quota_backend_bytes_gauge{__$labels__}` |
| `etcd_backend_allocated_usage_percent` | `clamp_min(etcd_mvcc_db_total_size_in_bytes_gauge{__$labels__} / etcd_server_quota_backend_bytes_gauge{__$labels__} * 100, 0)` |
| `etcd_backend_remaining_bytes` | `clamp_min(etcd_server_quota_backend_bytes_gauge{__$labels__} - etcd_mvcc_db_total_size_in_bytes_gauge{__$labels__}, 0)` |
| `etcd_backend_fragmentation_percent` | `clamp_min((etcd_mvcc_db_total_size_in_bytes_gauge{__$labels__} - etcd_mvcc_db_total_size_in_use_in_bytes_gauge{__$labels__}) / clamp_min(etcd_mvcc_db_total_size_in_bytes_gauge{__$labels__}, 1) * 100, 0)` |
| `etcd_backend_urgent_defrag` | `((etcd_mvcc_db_total_size_in_bytes_gauge{__$labels__} / etcd_server_quota_backend_bytes_gauge{__$labels__} * 100) >= bool 80)` |
| `etcd_debugging_mvcc_keys_total_gauge` | `etcd_debugging_mvcc_keys_total_gauge{__$labels__}` |
| `process_resident_memory_bytes_gauge` | `process_resident_memory_bytes_gauge{instance_type="etcd", __$labels__}` |
| `etcd_disk_wal_fsync_p99_seconds` | `histogram_quantile(0.99, sum(rate((label_replace({__name__=~"etcd_disk_wal_fsync_duration_seconds_[0-9.]+", __$labels__}, "le", "$1", "__name__", "etcd_disk_wal_fsync_duration_seconds_(.+)"))[5m:]) or label_replace(rate(etcd_disk_wal_fsync_duration_seconds_count{__$labels__}[5m]), "le", "+Inf", "__name__", ".*")) by (instance_id, le))` |
| `etcd_disk_backend_commit_p99_seconds` | `histogram_quantile(0.99, sum(rate((label_replace({__name__=~"etcd_disk_backend_commit_duration_seconds_[0-9.]+", __$labels__}, "le", "$1", "__name__", "etcd_disk_backend_commit_duration_seconds_(.+)"))[5m:]) or label_replace(rate(etcd_disk_backend_commit_duration_seconds_count{__$labels__}[5m]), "le", "+Inf", "__name__", ".*")) by (instance_id, le))` |
| `etcd_debugging_snap_save_total_avg_seconds` | `sum(rate(etcd_debugging_snap_save_total_duration_seconds_sum{__$labels__}[5m])) by (instance_id) / clamp_min(sum(rate(etcd_debugging_snap_save_total_duration_seconds_count{__$labels__}[5m])) by (instance_id), 1e-9)` |
| `etcd_server_proposals_pending_gauge` | `etcd_server_proposals_pending_gauge{__$labels__}` |
| `etcd_server_proposals_failed_total_counter_rate` | `rate(etcd_server_proposals_failed_total_counter{__$labels__}[5m])` |
| `etcd_server_proposals_committed_rate` | `rate(etcd_server_proposals_committed_total_gauge{__$labels__}[5m])` |
| `etcd_server_proposals_applied_rate` | `rate(etcd_server_proposals_applied_total_gauge{__$labels__}[5m])` |
| `etcd_server_proposals_apply_lag` | `clamp_min(etcd_server_proposals_committed_total_gauge{__$labels__} - etcd_server_proposals_applied_total_gauge{__$labels__}, 0)` |
| `etcd_server_slow_apply_total_counter_rate` | `rate(etcd_server_slow_apply_total_counter{__$labels__}[5m])` |
| `etcd_server_read_indexes_failed_total_counter_rate` | `rate(etcd_server_read_indexes_failed_total_counter{__$labels__}[5m])` |
| `etcd_server_slow_read_indexes_total_counter_rate` | `rate(etcd_server_slow_read_indexes_total_counter{__$labels__}[5m])` |
| `etcd_server_client_requests_total_counter_rate` | `sum(rate(etcd_server_client_requests_total_counter{__$labels__}[5m])) by (instance_id)` |
| `etcd_rpc_rate` | `sum(rate(grpc_server_started_total_counter{grpc_type="unary", instance_type="etcd", __$labels__}[5m])) by (instance_id)` |
| `etcd_rpc_failed_rate` | `sum(rate(grpc_server_handled_total_counter{grpc_type="unary", grpc_code!="OK", instance_type="etcd", __$labels__}[5m])) by (instance_id)` |
| `etcd_network_client_grpc_received_bytes_total_counter_rate` | `sum(rate(etcd_network_client_grpc_received_bytes_total_counter{__$labels__}[5m])) by (instance_id)` |
| `etcd_network_client_grpc_sent_bytes_total_counter_rate` | `sum(rate(etcd_network_client_grpc_sent_bytes_total_counter{__$labels__}[5m])) by (instance_id)` |
| `etcd_network_peer_received_bytes_total_counter_rate` | `sum(rate(etcd_network_peer_received_bytes_total_counter{__$labels__}[5m])) by (instance_id)` |
| `etcd_network_peer_sent_bytes_total_counter_rate` | `sum(rate(etcd_network_peer_sent_bytes_total_counter{__$labels__}[5m])) by (instance_id)` |
| `etcd_network_peer_sent_failures_total_counter_rate` | `sum(rate(etcd_network_peer_sent_failures_total_counter{__$labels__}[5m])) by (instance_id)` |
| `etcd_debugging_mvcc_watcher_total_gauge` | `etcd_debugging_mvcc_watcher_total_gauge{__$labels__}` |
| `etcd_watch_streams_active` | `sum(grpc_server_started_total_counter{grpc_service="etcdserverpb.Watch", grpc_type="bidi_stream", instance_type="etcd", __$labels__}) by (instance_id) - sum(grpc_server_handled_total_counter{grpc_service="etcdserverpb.Watch", grpc_type="bidi_stream", instance_type="etcd", __$labels__}) by (instance_id)` |
| `etcd_debugging_mvcc_db_compaction_keys_total_counter_rate` | `rate(etcd_debugging_mvcc_db_compaction_keys_total_counter{__$labels__}[5m])` |
| `etcd_mvcc_put_total_counter_rate` | `rate(etcd_mvcc_put_total_counter{__$labels__}[5m])` |
| `etcd_mvcc_delete_total_counter_rate` | `rate(etcd_mvcc_delete_total_counter{__$labels__}[5m])` |
