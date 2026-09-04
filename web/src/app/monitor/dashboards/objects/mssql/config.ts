import type { SimpleDashboardConfig } from '../common/simple-dashboard-core';

/** MSSQL 监控高对比鲜活科技色板 */
const MSSQL_PALETTE = {
  emerald: '#10B981',   // 批量请求、写入速率、缓存命中率、可用空间
  blue: '#2563EB',      // 进程CPU、读延迟、读取速率、检查点写页、已用卷
  cyan: '#06B6D4',      // 卷可用空间、逻辑读、编译、页面生命周期
  indigo: '#6366F1',    // 运行时长、请求总耗时、惰性写入、用户连接
  amber: '#F59E0B',     // 资源等待、死锁、版本存储、重编译
  orange: '#F97316',    // 写延迟、内存授予等待、信号等待、锁等待
  rose: '#EF4444',      // 阻塞进程、等待任务
  neutral: '#94A3B8'    // 系统空闲 CPU、总空间、目标内存
} as const;

export const MSSQL_DASHBOARD_CONFIG: SimpleDashboardConfig = {
  routeKey: 'mssql',
  pageTitle: 'MSSQL 监控仪表盘',
  objectFallbackName: 'MSSQL',
  instanceType: 'mssql',
  collectionStatusQuery: "count({instance_type='mssql', collect_type='database', __$labels__}) by (instance_id)",
  metaItems: ['Telegraf', 'database'],
  metrics: [
    {
      name: 'sqlserver_server_properties_uptime',
      display_name: '运行时长',
      description: 'SQL Server 实例自上次启动以来的持续运行时间。',
      unit: 's',
      query: 'sqlserver_server_properties_uptime{__$labels__}',
      color: MSSQL_PALETTE.indigo
    },
    {
      name: 'sqlserver_cpu_sqlserver_process_cpu_avg',
      display_name: '进程 CPU 使用率',
      description: 'SQL Server 数据库进程的 CPU 使用率。',
      unit: 'percent',
      query: 'avg_over_time(sqlserver_cpu_sqlserver_process_cpu{__$labels__}[__$window__])',
      color: MSSQL_PALETTE.blue
    },
    {
      name: 'sqlserver_cpu_system_idle_cpu_avg',
      display_name: '系统空闲 CPU',
      description: '操作系统整体空闲 CPU 百分比。',
      unit: 'percent',
      query: 'avg_over_time(sqlserver_cpu_system_idle_cpu{__$labels__}[__$window__])',
      color: MSSQL_PALETTE.neutral
    },
    {
      name: 'sqlserver_database_io_read_latency_ms',
      display_name: '数据库读延迟',
      description: '数据库文件读操作的平均延迟时间。',
      unit: 'ms',
      query: 'avg without (database) (avg_over_time(sqlserver_database_io_read_latency_ms{__$labels__}[__$window__]))',
      color: MSSQL_PALETTE.blue
    },
    {
      name: 'sqlserver_database_io_write_latency_ms',
      display_name: '数据库写延迟',
      description: '数据库文件写操作的平均延迟时间。',
      unit: 'ms',
      query: 'avg without (database) (avg_over_time(sqlserver_database_io_write_latency_ms{__$labels__}[__$window__]))',
      color: MSSQL_PALETTE.orange
    },
    {
      name: 'sqlserver_database_io_reads_rate',
      display_name: '数据库读取速率',
      description: '数据库文件读操作速率。',
      unit: 'cps',
      query: 'sum without (database) (rate(sqlserver_database_io_reads{__$labels__}[__$window__]))',
      color: MSSQL_PALETTE.blue
    },
    {
      name: 'sqlserver_database_io_writes_rate',
      display_name: '数据库写入速率',
      description: '数据库文件写操作速率。',
      unit: 'cps',
      query: 'sum without (database) (rate(sqlserver_database_io_writes{__$labels__}[__$window__]))',
      color: MSSQL_PALETTE.emerald
    },
    {
      name: 'sqlserver_memory_clerks_size_kb',
      display_name: '内存 Clerk 大小',
      description: 'SQL Server 内部内存 Clerk 分配大小。',
      unit: 'kibibytes',
      query: 'sqlserver_memory_clerks_size_kb{__$labels__}',
      color: MSSQL_PALETTE.indigo
    },
    {
      name: 'sqlserver_performance_value_rate',
      display_name: '批量请求速率',
      description: 'SQL Server 处理批量请求的速率。',
      unit: 'cps',
      query: 'rate(sqlserver_performance_value{counter=~"Batch Requests/sec", __$labels__}[__$window__])',
      color: MSSQL_PALETTE.emerald
    },
    {
      name: 'sqlserver_checkpoint_pages_rate',
      display_name: '检查点写页速率',
      description: '检查点进程将脏页刷写到磁盘的速率。',
      unit: 'cps',
      query: 'rate(sqlserver_performance_value{counter="Checkpoint pages/sec", __$labels__}[__$window__])',
      color: MSSQL_PALETTE.blue
    },
    {
      name: 'sqlserver_lazy_writes_rate',
      display_name: '惰性写入速率',
      description: '惰性写入器为腾出缓冲池空间而刷写页面的速率。',
      unit: 'cps',
      query: 'rate(sqlserver_performance_value{counter="Lazy writes/sec", __$labels__}[__$window__])',
      color: MSSQL_PALETTE.indigo
    },
    {
      name: 'sqlserver_memory_grants_pending',
      display_name: '等待内存授予的请求数',
      description: '当前等待执行内存授予的查询数量。',
      unit: 'counts',
      query: 'sqlserver_performance_value{counter="Memory Grants Pending", __$labels__}',
      color: MSSQL_PALETTE.orange
    },
    {
      name: 'sqlserver_memory_grants_outstanding',
      display_name: '已授予内存的请求数',
      description: '当前已获得查询工作区内存但尚未完成的请求数。',
      unit: 'counts',
      query: 'sqlserver_performance_value{counter="Memory Grants Outstanding", __$labels__}',
      color: MSSQL_PALETTE.blue
    },
    {
      name: 'sqlserver_memory_target_server_memory_kb',
      display_name: '目标 Server Memory',
      description: 'SQL Server 目标内存大小。',
      unit: 'kibibytes',
      query: 'sqlserver_performance_value{counter="Target Server Memory (KB)", __$labels__}',
      color: MSSQL_PALETTE.neutral
    },
    {
      name: 'sqlserver_memory_total_server_memory_kb',
      display_name: '当前 Server Memory',
      description: 'SQL Server 当前已提交的内存大小。',
      unit: 'kibibytes',
      query: 'sqlserver_performance_value{counter="Total Server Memory (KB)", __$labels__}',
      color: MSSQL_PALETTE.indigo
    },
    {
      name: 'sqlserver_tempdb_free_space_kb',
      display_name: 'TempDB 可用空间',
      description: 'TempDB 当前可用空间。',
      unit: 'kibibytes',
      query: 'sqlserver_performance_value{counter="Free Space in tempdb (KB)", __$labels__}',
      color: MSSQL_PALETTE.emerald
    },
    {
      name: 'sqlserver_tempdb_version_store_size_kb',
      display_name: 'TempDB 版本存储大小',
      description: 'TempDB 当前版本存储大小。',
      unit: 'kibibytes',
      query: 'sqlserver_performance_value{counter="Version Store Size (KB)", __$labels__}',
      color: MSSQL_PALETTE.amber
    },
    {
      name: 'sqlserver_log_flushes_rate',
      display_name: '事务日志刷写速率',
      description: '事务日志刷写速率。',
      unit: 'cps',
      query: 'rate(sqlserver_performance_value{counter="Log Flushes/sec", __$labels__}[__$window__])',
      color: MSSQL_PALETTE.cyan
    },
    {
      name: 'sqlserver_processes_blocked',
      display_name: '阻塞进程数',
      description: '当前被阻塞的 SQL Server 进程数量。',
      unit: 'counts',
      query: 'sqlserver_performance_value{counter="Processes blocked", __$labels__}',
      color: MSSQL_PALETTE.rose
    },
    {
      name: 'sqlserver_deadlocks_rate',
      display_name: '死锁速率',
      description: 'SQL Server 死锁发生速率。',
      unit: 'cps',
      query: 'rate(sqlserver_performance_value{counter="Number of Deadlocks/sec", __$labels__}[__$window__])',
      color: MSSQL_PALETTE.rose
    },
    {
      name: 'sqlserver_sql_compilations_rate',
      display_name: 'SQL 编译速率',
      description: 'SQL 语句编译速率。',
      unit: 'cps',
      query: 'rate(sqlserver_performance_value{counter="SQL Compilations/sec", __$labels__}[__$window__])',
      color: MSSQL_PALETTE.cyan
    },
    {
      name: 'sqlserver_sql_recompilations_rate',
      display_name: 'SQL 重编译速率',
      description: 'SQL 语句重编译速率。',
      unit: 'cps',
      query: 'rate(sqlserver_performance_value{counter="SQL Re-Compilations/sec", __$labels__}[__$window__])',
      color: MSSQL_PALETTE.amber
    },
    {
      name: 'sqlserver_page_life_expectancy',
      display_name: '页面生命周期',
      description: '数据页在缓冲池中平均停留时间。',
      unit: 's',
      query: 'sqlserver_performance_value{counter="Page life expectancy", __$labels__}',
      color: MSSQL_PALETTE.cyan
    },
    {
      name: 'sqlserver_buffer_cache_hit_ratio',
      display_name: '缓冲区命中率',
      description: '从缓冲池满足数据页读取的百分比。',
      unit: 'percent',
      query: 'sqlserver_performance_value{counter="Buffer cache hit ratio", __$labels__}',
      color: MSSQL_PALETTE.emerald
    },
    {
      name: 'sqlserver_user_connections_rate',
      display_name: '用户连接数',
      description: '当前连接到 SQL Server 实例的用户数量。',
      unit: 'counts',
      query: 'sqlserver_performance_value{counter="User Connections", __$labels__}',
      color: MSSQL_PALETTE.indigo
    },
    {
      name: 'sqlserver_lock_wait_time_rate',
      display_name: '锁等待速率',
      description: '锁等待发生速率。',
      unit: 'cps',
      query: 'rate(sqlserver_performance_value{counter="Lock Waits/sec", __$labels__}[__$window__])',
      color: MSSQL_PALETTE.orange
    },
    {
      name: 'sqlserver_schedulers_active_workers_count',
      display_name: '活跃工作线程数',
      description: '调度器上当前执行任务的活跃工作线程数。',
      unit: 'counts',
      query: 'sqlserver_schedulers_active_workers_count{__$labels__}',
      color: MSSQL_PALETTE.blue
    },
    {
      name: 'sqlserver_schedulers_runnable_tasks_count',
      display_name: '可运行任务数',
      description: '就绪等待 CPU 执行的任务数。',
      unit: 'counts',
      query: 'sqlserver_schedulers_runnable_tasks_count{__$labels__}',
      color: MSSQL_PALETTE.amber
    },
    {
      name: 'sqlserver_waitstats_waiting_tasks_count',
      display_name: '等待任务数',
      description: '当前等待的任务数量。',
      unit: 'counts',
      query: 'sqlserver_waitstats_waiting_tasks_count{__$labels__}',
      color: MSSQL_PALETTE.rose
    },
    {
      name: 'sqlserver_requests_cpu_time_ms_rate',
      display_name: '请求 CPU 时间速率',
      description: '请求消耗 CPU 时间的速率（ms/s）。',
      unit: 'msps',
      query: 'rate(sqlserver_requests_cpu_time_ms{__$labels__}[__$window__])',
      color: MSSQL_PALETTE.blue
    },
    {
      name: 'sqlserver_requests_logical_reads_rate',
      display_name: '请求逻辑读速率',
      description: '请求逻辑读操作速率。',
      unit: 'cps',
      query: 'rate(sqlserver_requests_logical_reads{__$labels__}[__$window__])',
      color: MSSQL_PALETTE.cyan
    },
    {
      name: 'sqlserver_requests_total_elapsed_time_ms_rate',
      display_name: '请求总耗时速率',
      description: '请求总执行时间速率（ms/s）。',
      unit: 'msps',
      query: 'rate(sqlserver_requests_total_elapsed_time_ms{__$labels__}[__$window__])',
      color: MSSQL_PALETTE.indigo
    },
    {
      name: 'sqlserver_requests_wait_time_ms_rate',
      display_name: '请求等待时间速率',
      description: '请求等待资源时间速率（ms/s）。',
      unit: 'msps',
      query: 'rate(sqlserver_requests_wait_time_ms{__$labels__}[__$window__])',
      color: MSSQL_PALETTE.orange
    },
    {
      name: 'sqlserver_waitstats_resource_wait_ms',
      display_name: '资源等待速率',
      description: '等待外部资源的时间速率（ms/s）。',
      unit: 'msps',
      query: 'rate(sqlserver_waitstats_resource_wait_ms{__$labels__}[__$window__])',
      color: MSSQL_PALETTE.cyan
    },
    {
      name: 'sqlserver_waitstats_wait_time_ms_rate',
      display_name: '等待时间速率',
      description: 'SQL Server 各类等待类型累计等待时间速率（ms/s）。',
      unit: 'msps',
      query: 'rate(sqlserver_waitstats_wait_time_ms{__$labels__}[__$window__])',
      color: MSSQL_PALETTE.indigo
    },
    {
      name: 'sqlserver_waitstats_signal_wait_time_ms_rate',
      display_name: '信号等待速率',
      description: '等待 CPU 调度器的时间速率（ms/s）。',
      unit: 'msps',
      query: 'rate(sqlserver_waitstats_signal_wait_time_ms_rate{__$labels__}[__$window__])',
      color: MSSQL_PALETTE.orange
    },
    {
      name: 'sqlserver_volume_space_available_space_bytes',
      display_name: '卷可用空间',
      description: '存储卷的可用空间。',
      unit: 'bytes',
      query: 'sum by (instance_id) (sqlserver_volume_space_available_space_bytes{__$labels__})',
      color: MSSQL_PALETTE.cyan
    },
    {
      name: 'sqlserver_volume_space_total_space_bytes',
      display_name: '卷总空间',
      description: '存储卷的总容量（多卷按实例求和）。',
      unit: 'bytes',
      query: 'sum by (instance_id) (sqlserver_volume_space_total_space_bytes{__$labels__})',
      color: MSSQL_PALETTE.neutral
    },
    {
      name: 'sqlserver_volume_space_used_space_bytes',
      display_name: '卷已用空间',
      description: '存储卷的已用空间（多卷按实例求和）。',
      unit: 'bytes',
      query: 'sum by (instance_id) (sqlserver_volume_space_used_space_bytes{__$labels__})',
      color: MSSQL_PALETTE.blue
    },
    {
      name: 'sqlserver_volume_space_used_ratio',
      display_name: '卷空间使用率',
      description: '实例各卷合计已用空间占总容量的比例。',
      unit: 'percent',
      query: '100 * sum by (instance_id) (sqlserver_volume_space_used_space_bytes{__$labels__}) / clamp_min(sum by (instance_id) (sqlserver_volume_space_total_space_bytes{__$labels__}), 1)',
      color: MSSQL_PALETTE.blue
    }
  ],
  summaryCards: [
    {
      title: '运行时长',
      metric: 'sqlserver_server_properties_uptime',
      formatter: 'duration',
      color: MSSQL_PALETTE.indigo,
      icon: 'clock',
      isUptimeCard: true,
      hideTrend: true,
      guide: [{ label: '运行时长', detail: '实例自上次启动以来的持续运行时间。' }],
      footer: [{ label: '启动', metric: 'sqlserver_server_properties_uptime', formatter: 'startedAt' }]
    },
    {
      title: '批量请求速率',
      metric: 'sqlserver_performance_value_rate',
      color: MSSQL_PALETTE.emerald,
      icon: 'thunder',
      guide: [{ label: '批量请求', detail: '每秒处理的 SQL 批量请求数(次/秒),无固定阈值,按业务基线看突增突降。' }],
      footer: [{ label: '当前连接', metric: 'sqlserver_user_connections_rate', unit: 'counts' }]
    },
    {
      title: '缓存命中率',
      metric: 'sqlserver_buffer_cache_hit_ratio',
      color: MSSQL_PALETTE.emerald,
      icon: 'database',
      compare: true,
      compareFavorableDirection: 'up',
      guide: [{ label: '缓存命中率', detail: '缓冲池满足数据页读取的比例，低值说明内存或缓存压力偏高。' }]
    },
    {
      title: '读延迟',
      metric: 'sqlserver_database_io_read_latency_ms',
      color: MSSQL_PALETTE.blue,
      icon: 'api',
      compare: true,
      guide: [{ label: '读延迟', detail: '数据库文件读操作平均延迟，持续升高需排查存储性能；写延迟见下方「读写延迟」趋势。' }]
    },
    {
      title: '卷可用空间',
      metric: 'sqlserver_volume_space_available_space_bytes',
      color: MSSQL_PALETTE.cyan,
      icon: 'database',
      guide: [{ label: '卷可用空间', detail: '数据库所在卷剩余空间，空间不足会影响写入和维护任务。' }],
      footer: [
        { label: '总空间', metric: 'sqlserver_volume_space_total_space_bytes', unit: 'bytes' }
      ]
    }
  ],
  charts: [
    {
      title: '读写延迟',
      subtitle: '读写延迟变化',
      metric: 'sqlserver_database_io_read_latency_ms',
      guide: [
        { label: '读延迟', detail: '数据库文件读操作平均延迟。' },
        { label: '写延迟', detail: '数据库文件写操作平均延迟。' }
      ],
      series: [
        { metric: 'sqlserver_database_io_read_latency_ms', label: '读延迟', color: MSSQL_PALETTE.blue, unit: 'ms' },
        { metric: 'sqlserver_database_io_write_latency_ms', label: '写延迟', color: MSSQL_PALETTE.orange, unit: 'ms' }
      ]
    },
    {
      title: '读写吞吐',
      subtitle: '文件读写速率',
      metric: 'sqlserver_database_io_reads_rate',
      guide: [
        { label: '读取速率', detail: '数据库文件读操作速率。' },
        { label: '写入速率', detail: '数据库文件写操作速率。' }
      ],
      series: [
        { metric: 'sqlserver_database_io_reads_rate', label: '读取速率', color: MSSQL_PALETTE.blue, unit: 'cps' },
        { metric: 'sqlserver_database_io_writes_rate', label: '写入速率', color: MSSQL_PALETTE.emerald, unit: 'cps' }
      ]
    },
    {
      title: 'CPU 使用情况',
      subtitle: '进程与系统空闲',
      metric: 'sqlserver_cpu_sqlserver_process_cpu_avg',
      guide: [
        { label: '进程 CPU', detail: 'SQL Server 进程 CPU 使用率。' },
        { label: '系统空闲', detail: '操作系统空闲 CPU 百分比。' }
      ],
      series: [
        { metric: 'sqlserver_cpu_sqlserver_process_cpu_avg', label: '进程 CPU', color: MSSQL_PALETTE.blue, unit: 'percent' },
        { metric: 'sqlserver_cpu_system_idle_cpu_avg', label: '系统空闲', color: MSSQL_PALETTE.neutral, unit: 'percent' }
      ]
    },
    {
      title: '存储空间',
      subtitle: '已用与总容量',
      metric: 'sqlserver_volume_space_used_space_bytes',
      guide: [
        { label: '已用空间', detail: '存储卷已用空间。' },
        { label: '总空间', detail: '存储卷总容量。' }
      ],
      series: [
        { metric: 'sqlserver_volume_space_used_space_bytes', label: '已用空间', color: MSSQL_PALETTE.blue, unit: 'bytes' },
        { metric: 'sqlserver_volume_space_total_space_bytes', label: '总空间', color: MSSQL_PALETTE.neutral, unit: 'bytes' }
      ]
    },
    {
      title: '等待时间趋势',
      subtitle: '总等待与信号等待',
      metric: 'sqlserver_waitstats_wait_time_ms_rate',
      guide: [
        { label: '总等待', detail: '各类等待累计耗时速率（ms/s）。' },
        { label: '信号等待', detail: '等待 CPU 调度器的时间速率（ms/s）。' },
        { label: '资源等待', detail: '等待外部资源的时间速率（ms/s）。' }
      ],
      series: [
        { metric: 'sqlserver_waitstats_wait_time_ms_rate', label: '总等待', color: MSSQL_PALETTE.indigo, unit: 'msps' },
        { metric: 'sqlserver_waitstats_signal_wait_time_ms_rate', label: '信号等待', color: MSSQL_PALETTE.orange, unit: 'msps' },
        { metric: 'sqlserver_waitstats_resource_wait_ms', label: '资源等待', color: MSSQL_PALETTE.cyan, unit: 'msps' }
      ]
    },
    {
      title: '缓冲池写回压力',
      subtitle: '检查点与惰性写入',
      metric: 'sqlserver_checkpoint_pages_rate',
      guide: [
        { label: '检查点写页', detail: '检查点进程将脏页写入磁盘的速率；应结合写延迟观察。' },
        { label: '惰性写入', detail: '惰性写入器为缓冲池腾出空间的速率；持续升高且页生命周期下降时表示内存压力。' }
      ],
      series: [
        { metric: 'sqlserver_checkpoint_pages_rate', label: '检查点写页', color: MSSQL_PALETTE.blue, unit: 'cps' },
        { metric: 'sqlserver_lazy_writes_rate', label: '惰性写入', color: MSSQL_PALETTE.indigo, unit: 'cps' }
      ]
    },
    {
      title: '并发与内存压力',
      subtitle: '阻塞进程与内存授予等待',
      metric: 'sqlserver_processes_blocked',
      guide: [
        { label: '阻塞进程', detail: '当前被锁或资源争用阻塞的进程数。' },
        { label: '内存授予等待', detail: '等待查询工作区内存的请求数，持续非零应排查大排序、哈希和并发。' }
      ],
      series: [
        { metric: 'sqlserver_processes_blocked', label: '阻塞进程', color: MSSQL_PALETTE.rose, unit: 'counts' },
        { metric: 'sqlserver_memory_grants_pending', label: '内存授予等待', color: MSSQL_PALETTE.orange, unit: 'counts' }
      ]
    },
    {
      title: 'Server Memory',
      subtitle: '当前内存与目标内存',
      metric: 'sqlserver_memory_total_server_memory_kb',
      guide: [
        { label: '当前内存', detail: 'SQL Server 当前已提交的内存大小。' },
        { label: '目标内存', detail: 'SQL Server 配置的目标内存大小；长期差距需结合内存授予等待排查。' }
      ],
      series: [
        { metric: 'sqlserver_memory_total_server_memory_kb', label: '当前内存', color: MSSQL_PALETTE.indigo, unit: 'kibibytes' },
        { metric: 'sqlserver_memory_target_server_memory_kb', label: '目标内存', color: MSSQL_PALETTE.neutral, unit: 'kibibytes' }
      ]
    },
    {
      title: 'TempDB 健康度',
      subtitle: '可用空间与版本存储',
      metric: 'sqlserver_tempdb_free_space_kb',
      guide: [
        { label: '可用空间', detail: 'TempDB 当前剩余空间，过低会影响排序、哈希与临时对象。' },
        { label: '版本存储', detail: '长事务或快照读会推动版本存储增长。' }
      ],
      series: [
        { metric: 'sqlserver_tempdb_free_space_kb', label: '可用空间', color: MSSQL_PALETTE.emerald, unit: 'kibibytes' },
        { metric: 'sqlserver_tempdb_version_store_size_kb', label: '版本存储', color: MSSQL_PALETTE.amber, unit: 'kibibytes' }
      ]
    },
    {
      title: '事务日志刷写',
      subtitle: '事务日志 I/O 负载',
      metric: 'sqlserver_log_flushes_rate',
      guide: [{ label: '日志刷写', detail: '事务日志刷写速率；应结合数据库写延迟判断日志 I/O 压力。' }],
      series: [
        { metric: 'sqlserver_log_flushes_rate', label: '日志刷写', color: MSSQL_PALETTE.cyan, unit: 'cps' }
      ]
    },
    {
      title: '计划缓存与死锁',
      subtitle: '编译、重编译与死锁',
      metric: 'sqlserver_sql_compilations_rate',
      guide: [
        { label: 'SQL 编译', detail: 'SQL 语句编译速率，需结合批量请求速率判断计划缓存效率。' },
        { label: 'SQL 重编译', detail: 'SQL 语句重编译速率，相对编译速率持续偏高会增加 CPU 成本。' },
        { label: '死锁', detail: '死锁发生速率，持续非零应检查事务访问顺序和隔离级别。' }
      ],
      series: [
        { metric: 'sqlserver_sql_compilations_rate', label: 'SQL 编译', color: MSSQL_PALETTE.cyan, unit: 'cps' },
        { metric: 'sqlserver_sql_recompilations_rate', label: 'SQL 重编译', color: MSSQL_PALETTE.amber, unit: 'cps' },
        { metric: 'sqlserver_deadlocks_rate', label: '死锁', color: MSSQL_PALETTE.rose, unit: 'cps' }
      ]
    },
    {
      title: '请求耗时趋势',
      subtitle: 'CPU、等待与总耗时',
      metric: 'sqlserver_requests_total_elapsed_time_ms_rate',
      guide: [
        { label: '总耗时', detail: '请求总执行时间速率（ms/s）。' },
        { label: 'CPU 时间', detail: '请求消耗 CPU 时间速率（ms/s）。' },
        { label: '等待时间', detail: '请求等待资源时间速率（ms/s）。' }
      ],
      series: [
        { metric: 'sqlserver_requests_total_elapsed_time_ms_rate', label: '总耗时', color: MSSQL_PALETTE.indigo, unit: 'msps' },
        { metric: 'sqlserver_requests_cpu_time_ms_rate', label: 'CPU 时间', color: MSSQL_PALETTE.blue, unit: 'msps' },
        { metric: 'sqlserver_requests_wait_time_ms_rate', label: '等待时间', color: MSSQL_PALETTE.orange, unit: 'msps' }
      ]
    }
  ],
  ringPanels: [
    {
      title: '存储空间分布',
      subtitle: '已用与可用',
      centerMetric: 'sqlserver_volume_space_used_ratio',
      centerCaption: '使用率',
      centerUnit: 'percent',
      guide: [{ label: '存储空间', detail: '数据库所在卷已用空间与可用空间占比。' }],
      segments: [
        { label: '已用空间', metric: 'sqlserver_volume_space_used_ratio', color: MSSQL_PALETTE.blue, unit: 'percent' },
        { label: '可用空间', metric: 'sqlserver_volume_space_used_ratio', color: MSSQL_PALETTE.neutral, unit: 'percent', transform: 'percentRemaining' }
      ]
    }
  ],
  barPanels: [
    {
      title: '调度器压力',
      subtitle: '工作线程与等待',
      showTrend: true,
      guide: [{ label: '调度器压力', detail: '活跃工作线程、可运行任务和等待任务的当前分布。' }],
      items: [
        { label: '活跃工作线程', metric: 'sqlserver_schedulers_active_workers_count', color: MSSQL_PALETTE.blue, unit: 'counts' },
        { label: '可运行任务', metric: 'sqlserver_schedulers_runnable_tasks_count', color: MSSQL_PALETTE.amber, unit: 'counts' },
        { label: '等待任务', metric: 'sqlserver_waitstats_waiting_tasks_count', color: MSSQL_PALETTE.rose, unit: 'counts' }
      ]
    },
  ],
  details: []
};
