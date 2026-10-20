/**
 * 专业盘分区是否还在等自己的查询。
 * 与主机 `metricBlockPhase` 同一套：只看本区指标，不等别的接口。
 */
export const blocksUntilReady = (
  names: readonly string[],
  pending: ReadonlySet<string>
) => names.some((name) => pending.has(name));

/** 实例态：角色 / 只读 / Binlog。不等折线。 */
export const MYSQL_HEADER_METRICS = [
  'mysql_variables_read_only',
  'mysql_variables_super_read_only',
  'mysql_variables_log_bin',
  'mysql_slave_seconds_behind_master',
  'mysql_slave_io_running',
  'mysql_slave_sql_running'
] as const;

/** 健康概览一行。告警条数是另一条请求，不放进这组。 */
export const MYSQL_HEALTH_METRICS = [
  'mysql_uptime',
  'mysql_threads_connected',
  'mysql_variables_max_connections',
  'mysql_queries_rate',
  'mysql_slow_queries_rate',
  'mysql_buffer_pool_hit_ratio'
] as const;

export const MYSQL_FOCUS_METRICS = [
  'mysql_slow_queries_rate',
  'mysql_connection_utilization',
  'mysql_buffer_pool_hit_ratio',
  'mysql_threads_running'
] as const;

export const MYSQL_ROLE_METRICS = [
  'mysql_slave_seconds_behind_master',
  'mysql_slave_io_running',
  'mysql_slave_sql_running'
] as const;
