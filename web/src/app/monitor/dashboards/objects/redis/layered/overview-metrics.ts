/**
 * 概览五 KPI 的指标名。query 与单位仍在 config.ts，专业盘只按这个顺序取传统卡。
 * 内存使用率用已有 redis_memory_utilization（used/maxmemory 派生），不另写查询。
 */
export const REDIS_OVERVIEW_METRIC_NAMES = [
  'redis_uptime',
  'redis_memory_utilization',
  'redis_keyspace_hitrate',
  'redis_evicted_keys_rate',
  'redis_clients'
] as const;

export const REDIS_OVERVIEW_KPI_TITLES = [
  '运行时长',
  '内存使用率',
  '缓存命中率',
  '键驱逐频率',
  '客户端连接数'
] as const;

/**
 * 专业态要拉的指标。名字都在 config.ts；未命中频率的 query 是
 * rate(redis_keyspace_misses[window])，不是落盘 __name__。
 * 复制与 Cluster 序列的 query 与 metrics tip 700c32e809 一样，是裸序列。
 */
export const REDIS_REPLICATION_METRIC_NAMES = [
  'redis_connected_slaves',
  'redis_master_link_status',
  'redis_repl_backlog_active',
  'redis_repl_backlog_size',
  'redis_repl_backlog_histlen',
  'redis_master_repl_offset',
  'redis_slave_repl_offset',
  'redis_mem_replication_backlog'
] as const;

export const REDIS_CLUSTER_METRIC_NAMES = [
  'redis_cluster_enabled',
  'redis_cluster_connections'
] as const;

export const REDIS_CATEGORY_METRIC_NAMES = [
  ...REDIS_OVERVIEW_METRIC_NAMES,
  'redis_used_memory',
  'redis_maxmemory',
  'redis_mem_fragmentation_ratio',
  'redis_keyspace_hits_rate',
  'redis_keyspace_misses_rate',
  'redis_total_commands_processed_rate',
  'redis_instantaneous_ops_per_sec',
  'redis_blocked_clients',
  'redis_expired_keys_rate',
  'redis_rejected_connections_rate',
  'redis_total_net_input_bytes_rate',
  'redis_total_net_output_bytes_rate',
  ...REDIS_REPLICATION_METRIC_NAMES,
  ...REDIS_CLUSTER_METRIC_NAMES
] as const;
