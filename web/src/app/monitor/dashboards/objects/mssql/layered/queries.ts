import type { Dimension } from '@/app/monitor/types';
import type { SimpleMetricConfig } from '../../common/simple-dashboard-core';

/** 与传统盘同一套色，专业盘不另起一套主题色。 */
export const MSSQL_PRO_PALETTE = {
  emerald: '#10B981',
  blue: '#2563EB',
  cyan: '#06B6D4',
  indigo: '#6366F1',
  amber: '#F59E0B',
  orange: '#F97316',
  rose: '#EF4444',
  neutral: '#94A3B8'
} as const;

const metric = (
  name: string,
  displayName: string,
  description: string,
  unit: SimpleMetricConfig['unit'],
  query: string,
  color: string,
  dimensions?: Dimension[]
): SimpleMetricConfig => ({
  name,
  display_name: displayName,
  description,
  unit,
  query,
  color,
  ...(dimensions ? { dimensions } : {})
});

/**
 * 专业盘查询。
 * 与传统盘相同的模板沿用原指标名；口径不同的用新名字，避免切盘时复用到错误序列。
 * 测量名不加 mssql_ 前缀，也不另造 *_value。性能计数器走 sqlserver_performance_value{counter=...}。
 */
export const MSSQL_PRO_METRICS: SimpleMetricConfig[] = [
  metric(
    'sqlserver_server_properties_uptime',
    '运行时长',
    '实例自上次启动以来的持续运行时间。',
    's',
    'sqlserver_server_properties_uptime{__$labels__}',
    MSSQL_PRO_PALETTE.indigo
  ),
  metric(
    'sqlserver_user_connections_rate',
    '用户连接数',
    '当前连到本实例的用户会话个数。',
    'counts',
    'sqlserver_performance_value{counter="User Connections", __$labels__}',
    MSSQL_PRO_PALETTE.indigo
  ),
  metric(
    'sqlserver_performance_value_rate',
    '批处理请求速率',
    '每秒完成的批处理请求数。',
    'cps',
    'rate(sqlserver_performance_value{counter=~"Batch Requests/sec", __$labels__}[__$window__])',
    MSSQL_PRO_PALETTE.emerald
  ),
  metric(
    'sqlserver_buffer_cache_hit_ratio',
    '缓冲池命中率',
    '缓冲池满足的数据页读取占比。',
    'percent',
    'sqlserver_performance_value{counter="Buffer cache hit ratio", __$labels__}',
    MSSQL_PRO_PALETTE.emerald
  ),
  metric(
    'mssql_pro_process_cpu',
    '进程 CPU',
    'SQL Server 进程自身占用的计算资源比例，按近 5 分钟平均。',
    'percent',
    'avg_over_time(sqlserver_cpu_sqlserver_process_cpu{__$labels__}[5m])',
    MSSQL_PRO_PALETTE.blue
  ),
  metric(
    'mssql_pro_idle_cpu',
    '系统空闲 CPU',
    '操作系统空闲 CPU，仅作进程 CPU 的对照。',
    'percent',
    'avg_over_time(sqlserver_cpu_system_idle_cpu{__$labels__}[5m])',
    MSSQL_PRO_PALETTE.neutral
  ),
  metric(
    'mssql_pro_read_latency',
    '数据库读取延迟',
    '数据库文件完成一次读取平均所需的时间。',
    'ms',
    'avg by (instance_id) (avg_over_time(sqlserver_database_io_read_latency_ms{__$labels__}[__$window__]))',
    MSSQL_PRO_PALETTE.blue
  ),
  metric(
    'mssql_pro_write_latency',
    '数据库写入延迟',
    '数据库文件完成一次写入平均所需的时间。',
    'ms',
    'avg by (instance_id) (avg_over_time(sqlserver_database_io_write_latency_ms{__$labels__}[__$window__]))',
    MSSQL_PRO_PALETTE.orange
  ),
  metric(
    'mssql_pro_reads_rate',
    '数据库读取次数',
    '数据库文件每秒的读取次数。',
    'cps',
    'sum by (instance_id) (rate(sqlserver_database_io_reads{__$labels__}[__$window__]))',
    MSSQL_PRO_PALETTE.blue
  ),
  metric(
    'mssql_pro_writes_rate',
    '数据库写入次数',
    '数据库文件每秒的写入次数。',
    'cps',
    'sum by (instance_id) (rate(sqlserver_database_io_writes{__$labels__}[__$window__]))',
    MSSQL_PRO_PALETTE.emerald
  ),
  metric(
    'mssql_pro_page_life',
    '页生命周期期望',
    '数据页在缓冲池中预计可停留的时间。',
    's',
    'avg by (instance_id) (sqlserver_performance_value{counter="Page life expectancy", object=~".*Buffer Manager", __$labels__})',
    MSSQL_PRO_PALETTE.cyan
  ),
  metric(
    'sqlserver_processes_blocked',
    '阻塞进程数',
    '当前被其他会话堵住、正在等待的进程个数。',
    'counts',
    'sqlserver_performance_value{counter="Processes blocked", __$labels__}',
    MSSQL_PRO_PALETTE.rose
  ),
  metric(
    'mssql_pro_deadlocks_count',
    '死锁次数',
    '当前时间范围内发生的死锁次数。',
    'counts',
    'sum by (instance_id) (increase(sqlserver_performance_value{counter="Number of Deadlocks/sec", __$labels__}[__$window__]))',
    MSSQL_PRO_PALETTE.rose
  ),
  metric(
    'sqlserver_memory_total_server_memory_kb',
    '当前 Server Memory',
    '当前已提交给 SQL Server 的内存。',
    'kibibytes',
    'sqlserver_performance_value{counter="Total Server Memory (KB)", __$labels__}',
    MSSQL_PRO_PALETTE.indigo
  ),
  metric(
    'sqlserver_memory_target_server_memory_kb',
    '目标 Server Memory',
    '实例希望使用的目标内存。',
    'kibibytes',
    'sqlserver_performance_value{counter="Target Server Memory (KB)", __$labels__}',
    MSSQL_PRO_PALETTE.neutral
  ),
  metric(
    'sqlserver_checkpoint_pages_rate',
    '检查点写页',
    '检查点写回脏页的速率。',
    'cps',
    'rate(sqlserver_performance_value{counter="Checkpoint pages/sec", __$labels__}[__$window__])',
    MSSQL_PRO_PALETTE.blue
  ),
  metric(
    'sqlserver_lazy_writes_rate',
    '惰性写入',
    '内存紧张时惰性写入腾出缓冲的速率。',
    'cps',
    'rate(sqlserver_performance_value{counter="Lazy writes/sec", __$labels__}[__$window__])',
    MSSQL_PRO_PALETTE.indigo
  ),
  metric(
    'sqlserver_memory_grants_outstanding',
    '已授予内存的请求数',
    '已获得工作区内存的请求数。',
    'counts',
    'sqlserver_performance_value{counter="Memory Grants Outstanding", __$labels__}',
    MSSQL_PRO_PALETTE.blue
  ),
  metric(
    'sqlserver_memory_grants_pending',
    '等待内存授予的请求数',
    '仍在排队等待授予的请求数。',
    'counts',
    'sqlserver_performance_value{counter="Memory Grants Pending", __$labels__}',
    MSSQL_PRO_PALETTE.orange
  ),
  metric(
    'sqlserver_sql_compilations_rate',
    'SQL 编译',
    '每秒新编译的语句计划数。',
    'cps',
    'rate(sqlserver_performance_value{counter="SQL Compilations/sec", __$labels__}[__$window__])',
    MSSQL_PRO_PALETTE.cyan
  ),
  metric(
    'sqlserver_sql_recompilations_rate',
    'SQL 重编译',
    '每秒重新编译的语句计划数。',
    'cps',
    'rate(sqlserver_performance_value{counter="SQL Re-Compilations/sec", __$labels__}[__$window__])',
    MSSQL_PRO_PALETTE.amber
  ),
  metric(
    'mssql_pro_clerks',
    '内存 Clerk 构成',
    '各类内存办事员占用的内存大小。',
    'kibibytes',
    'topk(8, sum by (clerk_type) (sqlserver_memory_clerks_size_kb{__$labels__}))',
    MSSQL_PRO_PALETTE.indigo,
    [{ name: 'clerk_type', description: '用途' }]
  ),
  metric(
    'sqlserver_log_flushes_rate',
    '事务日志刷写',
    '事务日志每秒刷到磁盘的次数。',
    'cps',
    'rate(sqlserver_performance_value{counter="Log Flushes/sec", __$labels__}[__$window__])',
    MSSQL_PRO_PALETTE.cyan
  ),
  metric(
    'sqlserver_tempdb_free_space_kb',
    'TempDB 可用空间',
    'TempDB 当前可用空间。',
    'kibibytes',
    'sqlserver_performance_value{counter="Free Space in tempdb (KB)", __$labels__}',
    MSSQL_PRO_PALETTE.emerald
  ),
  metric(
    'sqlserver_tempdb_version_store_size_kb',
    'TempDB 版本存储',
    '版本存储占用的大小。',
    'kibibytes',
    'sqlserver_performance_value{counter="Version Store Size (KB)", __$labels__}',
    MSSQL_PRO_PALETTE.amber
  ),
  metric(
    'sqlserver_volume_space_used_space_bytes',
    '卷已用空间',
    '数据与日志所在卷已使用的空间。',
    'bytes',
    'sum by (instance_id) (sqlserver_volume_space_used_space_bytes{__$labels__})',
    MSSQL_PRO_PALETTE.blue
  ),
  metric(
    'sqlserver_volume_space_total_space_bytes',
    '卷总空间',
    '数据与日志所在卷的总容量。',
    'bytes',
    'sum by (instance_id) (sqlserver_volume_space_total_space_bytes{__$labels__})',
    MSSQL_PRO_PALETTE.neutral
  ),
  metric(
    'mssql_pro_wait_time',
    '总等待',
    '各类等待消耗的时间。',
    'msps',
    'sum by (instance_id) (rate(sqlserver_waitstats_wait_time_ms{__$labels__}[__$window__]))',
    MSSQL_PRO_PALETTE.indigo
  ),
  metric(
    'mssql_pro_signal_wait',
    '信号等待',
    '等待 CPU 调度的时间。',
    'msps',
    'sum by (instance_id) (rate(sqlserver_waitstats_signal_wait_time_ms{__$labels__}[__$window__]))',
    MSSQL_PRO_PALETTE.orange
  ),
  metric(
    'mssql_pro_resource_wait',
    '资源等待',
    '等待锁、I/O 等外部资源的时间。',
    'msps',
    'sum by (instance_id) (rate(sqlserver_waitstats_resource_wait_ms{__$labels__}[__$window__]))',
    MSSQL_PRO_PALETTE.cyan
  ),
  metric(
    'mssql_pro_lock_waits',
    '锁等待',
    '锁等待发生的频繁程度。',
    'cps',
    'sum by (instance_id) (rate(sqlserver_performance_value{counter="Lock Waits/sec", __$labels__}[__$window__]))',
    MSSQL_PRO_PALETTE.orange
  ),
  metric(
    'mssql_pro_runnable_tasks',
    '可运行任务',
    '当前可运行但尚未获得 CPU 的任务数。',
    'counts',
    'sum by (instance_id) (sqlserver_schedulers_runnable_tasks_count{__$labels__})',
    MSSQL_PRO_PALETTE.amber
  ),
  metric(
    'mssql_pro_active_workers',
    '活动工作线程',
    '调度器上的活动工作线程数。',
    'counts',
    'sum by (instance_id) (sqlserver_schedulers_active_workers_count{__$labels__})',
    MSSQL_PRO_PALETTE.blue
  ),
  metric(
    'mssql_pro_request_cpu',
    '请求计算耗时',
    '正在执行的请求花在计算上的耗时。',
    'msps',
    'sum by (instance_id) (rate(sqlserver_requests_cpu_time_ms{__$labels__}[__$window__]))',
    MSSQL_PRO_PALETTE.blue
  ),
  metric(
    'mssql_pro_request_elapsed',
    '请求总耗时',
    '正在执行的请求的总耗时。',
    'msps',
    'sum by (instance_id) (rate(sqlserver_requests_total_elapsed_time_ms{__$labels__}[__$window__]))',
    MSSQL_PRO_PALETTE.indigo
  ),
  metric(
    'mssql_pro_request_wait',
    '请求等待耗时',
    '正在执行的请求花在等待上的耗时。',
    'msps',
    'sum by (instance_id) (rate(sqlserver_requests_wait_time_ms{__$labels__}[__$window__]))',
    MSSQL_PRO_PALETTE.orange
  )
];

export const MSSQL_PRO_METRIC_NAMES = MSSQL_PRO_METRICS.map((item) => item.name);

/** 等待类别排行。按类别汇总等待时间，不把累计等待次数当成当前等待个数。 */
export const MSSQL_PRO_WAIT_CATEGORY_QUERY = 'topk(8, sum by (wait_category) (rate(sqlserver_waitstats_wait_time_ms{__$labels__}[__$window__])))';

export const MSSQL_PRO_NAMES = {
  uptime: 'sqlserver_server_properties_uptime',
  connections: 'sqlserver_user_connections_rate',
  batch: 'sqlserver_performance_value_rate',
  hit: 'sqlserver_buffer_cache_hit_ratio',
  processCpu: 'mssql_pro_process_cpu',
  idleCpu: 'mssql_pro_idle_cpu',
  readLatency: 'mssql_pro_read_latency',
  writeLatency: 'mssql_pro_write_latency',
  reads: 'mssql_pro_reads_rate',
  writes: 'mssql_pro_writes_rate',
  pageLife: 'mssql_pro_page_life',
  blocked: 'sqlserver_processes_blocked',
  deadlocks: 'mssql_pro_deadlocks_count',
  totalMemory: 'sqlserver_memory_total_server_memory_kb',
  targetMemory: 'sqlserver_memory_target_server_memory_kb',
  checkpoint: 'sqlserver_checkpoint_pages_rate',
  lazyWrites: 'sqlserver_lazy_writes_rate',
  grantsOutstanding: 'sqlserver_memory_grants_outstanding',
  grantsPending: 'sqlserver_memory_grants_pending',
  compilations: 'sqlserver_sql_compilations_rate',
  recompilations: 'sqlserver_sql_recompilations_rate',
  clerks: 'mssql_pro_clerks',
  logFlushes: 'sqlserver_log_flushes_rate',
  tempdbFree: 'sqlserver_tempdb_free_space_kb',
  versionStore: 'sqlserver_tempdb_version_store_size_kb',
  volumeUsed: 'sqlserver_volume_space_used_space_bytes',
  volumeTotal: 'sqlserver_volume_space_total_space_bytes',
  waitTime: 'mssql_pro_wait_time',
  signalWait: 'mssql_pro_signal_wait',
  resourceWait: 'mssql_pro_resource_wait',
  lockWaits: 'mssql_pro_lock_waits',
  runnable: 'mssql_pro_runnable_tasks',
  workers: 'mssql_pro_active_workers',
  requestCpu: 'mssql_pro_request_cpu',
  requestElapsed: 'mssql_pro_request_elapsed',
  requestWait: 'mssql_pro_request_wait'
} as const;
