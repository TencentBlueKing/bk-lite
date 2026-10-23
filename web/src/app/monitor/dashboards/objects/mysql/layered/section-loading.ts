/**
 * 专业盘分区是否还在等自己的查询。
 * 与主机 `metricBlockPhase` 同一套：只看本区指标，不等别的接口。
 */
export const blocksUntilReady = (
  names: readonly string[],
  pending: ReadonlySet<string>
) => names.some((name) => pending.has(name));

/** 实例摘要：角色 / 只读 / Binlog / 版本。不等折线。 */
export const MYSQL_HEADER_METRICS = [
  'mysql_variables_read_only',
  'mysql_variables_super_read_only',
  'mysql_variables_log_bin',
  'mysql_variables_max_connections',
  'mysql_slave_seconds_behind_master',
  'mysql_slave_io_running',
  'mysql_slave_sql_running',
  'mysql_slave_relay_log_pos',
  'mysql_slave_relay_log_space',
  'mysql_replication_source_log_pos'
] as const;

export const MYSQL_ROLE_METRICS = [
  'mysql_slave_seconds_behind_master',
  'mysql_slave_io_running',
  'mysql_slave_sql_running'
] as const;

/** 健康概览一行。告警条数是另一条请求，不放进这组。活跃会话与当前连接同组拉取。 */
export const MYSQL_HEALTH_METRICS = [
  'mysql_uptime',
  'mysql_threads_connected',
  'mysql_threads_running',
  'mysql_variables_max_connections',
  'mysql_queries_rate',
  'mysql_slow_queries_rate',
  ...MYSQL_ROLE_METRICS,
  'mysql_slave_relay_log_pos',
  'mysql_slave_relay_log_space',
  'mysql_replication_source_log_pos'
] as const;

/** 重点关注四卡。主从同一套；缺采也占位，不按角色换卡。 */
export const MYSQL_FOCUS_METRICS = [
  'mysql_threads_running',
  'mysql_buffer_pool_hit_ratio',
  'mysql_innodb_row_lock_waits_rate',
  'mysql_tmp_disk_table_ratio'
] as const;
