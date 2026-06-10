import type { SimpleDashboardConfig } from '../common/simple-dashboard-core';

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
      color: '#597ef7'
    },
    {
      name: 'sqlserver_cpu_sqlserver_process_cpu_avg',
      display_name: '进程 CPU 使用率',
      description: 'SQL Server 数据库进程的 CPU 使用率。',
      unit: 'percent',
      query: 'avg_over_time(sqlserver_cpu_sqlserver_process_cpu{__$labels__}[5m])',
      color: '#2f6bff'
    },
    {
      name: 'sqlserver_cpu_system_idle_cpu_avg',
      display_name: '系统空闲 CPU',
      description: '操作系统整体空闲 CPU 百分比。',
      unit: 'percent',
      query: 'avg_over_time(sqlserver_cpu_system_idle_cpu{__$labels__}[5m])',
      color: '#9aa9bf'
    },
    {
      name: 'sqlserver_database_io_read_latency_ms',
      display_name: '数据库读延迟',
      description: '数据库文件读操作的平均延迟时间。',
      unit: 'ms',
      query: 'avg_over_time(sqlserver_database_io_read_latency_ms{__$labels__}[5m])',
      color: '#2f6bff'
    },
    {
      name: 'sqlserver_database_io_write_latency_ms',
      display_name: '数据库写延迟',
      description: '数据库文件写操作的平均延迟时间。',
      unit: 'ms',
      query: 'avg_over_time(sqlserver_database_io_write_latency_ms{__$labels__}[5m])',
      color: '#ff8a1f'
    },
    {
      name: 'sqlserver_database_io_reads_rate',
      display_name: '数据库读取速率',
      description: '数据库文件读操作速率。',
      unit: 'cps',
      query: 'rate(sqlserver_database_io_reads{__$labels__}[5m])',
      color: '#2f6bff'
    },
    {
      name: 'sqlserver_database_io_writes_rate',
      display_name: '数据库写入速率',
      description: '数据库文件写操作速率。',
      unit: 'cps',
      query: 'rate(sqlserver_database_io_writes{__$labels__}[5m])',
      color: '#27c274'
    },
    {
      name: 'sqlserver_memory_clerks_size_kb',
      display_name: '内存 Clerk 大小',
      description: 'SQL Server 内部内存 Clerk 分配大小。',
      unit: 'kibibytes',
      query: 'sqlserver_memory_clerks_size_kb{__$labels__}',
      color: '#8a5cff'
    },
    {
      name: 'sqlserver_performance_value_rate',
      display_name: '批量请求速率',
      description: 'SQL Server 处理批量请求的速率。',
      unit: 'cps',
      query: 'rate(sqlserver_performance_value{counter=~"Batch Requests/sec", __$labels__}[5m])',
      color: '#27c274'
    },
    {
      name: 'sqlserver_page_life_expectancy',
      display_name: '页面生命周期',
      description: '数据页在缓冲池中平均停留时间。',
      unit: 's',
      query: 'sqlserver_performance_value{counter="Page life expectancy", __$labels__}',
      color: '#13c2c2'
    },
    {
      name: 'sqlserver_buffer_cache_hit_ratio',
      display_name: '缓冲区命中率',
      description: '从缓冲池满足数据页读取的百分比。',
      unit: 'percent',
      query: 'sqlserver_performance_value{counter="Buffer cache hit ratio", __$labels__}',
      color: '#27c274'
    },
    {
      name: 'sqlserver_user_connections_rate',
      display_name: '用户连接变化',
      description: '用户连接数变化速率。',
      unit: 'cps',
      query: 'rate(sqlserver_performance_value{counter=~"User Connections", __$labels__}[5m])',
      color: '#597ef7'
    },
    {
      name: 'sqlserver_lock_wait_time_rate',
      display_name: '锁等待速率',
      description: '锁等待发生速率。',
      unit: 'cps',
      query: 'rate(sqlserver_performance_value{counter=~"Lock Waits/sec", __$labels__}[5m])',
      color: '#ff8a1f'
    },
    {
      name: 'sqlserver_schedulers_active_workers_count',
      display_name: '活跃工作线程数',
      description: '调度器上当前执行任务的活跃工作线程数。',
      unit: 'counts',
      query: 'sqlserver_schedulers_active_workers_count{__$labels__}',
      color: '#2f6bff'
    },
    {
      name: 'sqlserver_schedulers_runnable_tasks_count',
      display_name: '可运行任务数',
      description: '就绪等待 CPU 执行的任务数。',
      unit: 'counts',
      query: 'sqlserver_schedulers_runnable_tasks_count{__$labels__}',
      color: '#faad14'
    },
    {
      name: 'sqlserver_waitstats_waiting_tasks_count',
      display_name: '等待任务数',
      description: '当前等待的任务数量。',
      unit: 'counts',
      query: 'sqlserver_waitstats_waiting_tasks_count{__$labels__}',
      color: '#ff4d4f'
    },
    {
      name: 'sqlserver_requests_cpu_time_ms_rate',
      display_name: '请求 CPU 时间速率',
      description: '请求消耗 CPU 时间的速率。',
      unit: 'ms',
      query: 'rate(sqlserver_requests_cpu_time_ms{__$labels__}[5m])',
      color: '#2f6bff'
    },
    {
      name: 'sqlserver_requests_logical_reads_rate',
      display_name: '请求逻辑读速率',
      description: '请求逻辑读操作速率。',
      unit: 'cps',
      query: 'rate(sqlserver_requests_logical_reads{__$labels__}[5m])',
      color: '#13c2c2'
    },
    {
      name: 'sqlserver_requests_total_elapsed_time_ms_rate',
      display_name: '请求总耗时速率',
      description: '请求总执行时间速率。',
      unit: 'ms',
      query: 'rate(sqlserver_requests_total_elapsed_time_ms{__$labels__}[5m])',
      color: '#8a5cff'
    },
    {
      name: 'sqlserver_requests_wait_time_ms_rate',
      display_name: '请求等待时间速率',
      description: '请求等待资源时间速率。',
      unit: 'ms',
      query: 'rate(sqlserver_requests_wait_time_ms{__$labels__}[5m])',
      color: '#ff8a1f'
    },
    {
      name: 'sqlserver_waitstats_resource_wait_ms',
      display_name: '资源等待速率',
      description: '等待外部资源的时间速率。',
      unit: 'ms',
      query: 'rate(sqlserver_waitstats_resource_wait_ms{__$labels__}[5m])',
      color: '#faad14'
    },
    {
      name: 'sqlserver_waitstats_wait_time_ms_rate',
      display_name: '等待时间速率',
      description: 'SQL Server 各类等待类型累计等待时间速率。',
      unit: 'ms',
      query: 'rate(sqlserver_waitstats_wait_time_ms{__$labels__}[5m])',
      color: '#8a5cff'
    },
    {
      name: 'sqlserver_waitstats_signal_wait_time_ms_rate',
      display_name: '信号等待速率',
      description: '等待 CPU 调度器的时间速率。',
      unit: 'ms',
      query: 'rate(sqlserver_waitstats_signal_wait_time_ms{__$labels__}[5m])',
      color: '#ff8a1f'
    },
    {
      name: 'sqlserver_volume_space_available_space_bytes',
      display_name: '卷可用空间',
      description: '存储卷的可用空间。',
      unit: 'bytes',
      query: 'sqlserver_volume_space_available_space_bytes{__$labels__}',
      color: '#13c2c2'
    },
    {
      name: 'sqlserver_volume_space_total_space_bytes',
      display_name: '卷总空间',
      description: '存储卷的总容量。',
      unit: 'bytes',
      query: 'sqlserver_volume_space_total_space_bytes{__$labels__}',
      color: '#9aa9bf'
    },
    {
      name: 'sqlserver_volume_space_used_space_bytes',
      display_name: '卷已用空间',
      description: '存储卷的已用空间。',
      unit: 'bytes',
      query: 'sqlserver_volume_space_used_space_bytes{__$labels__}',
      color: '#2f6bff'
    },
    {
      name: 'sqlserver_volume_space_used_ratio',
      display_name: '卷空间使用率',
      description: '存储卷已用空间占总容量的比例。',
      unit: 'percent',
      query: '100 * sqlserver_volume_space_used_space_bytes{__$labels__} / clamp_min(sqlserver_volume_space_total_space_bytes{__$labels__}, 1)',
      color: '#2f6bff'
    },
    {
      name: 'sqlserver_signal_wait_ratio',
      display_name: '信号等待占比',
      description: '信号等待时间占总等待时间的比例。',
      unit: 'percent',
      query: '100 * rate(sqlserver_waitstats_signal_wait_time_ms{__$labels__}[5m]) / clamp_min(rate(sqlserver_waitstats_wait_time_ms{__$labels__}[5m]), 1e-6)',
      color: '#ff8a1f'
    }
  ],
  summaryCards: [
    {
      title: '运行时长',
      metric: 'sqlserver_server_properties_uptime',
      formatter: 'duration',
      color: '#597ef7',
      icon: 'clock',
      isUptimeCard: true,
      hideTrend: true,
      guide: [{ label: '运行时长', detail: '实例自上次启动以来的持续运行时间。' }],
      footer: [{ label: '启动时间', metric: 'sqlserver_server_properties_uptime', formatter: 'startedAt' }]
    },
    {
      title: '批量请求速率',
      metric: 'sqlserver_performance_value_rate',
      color: '#27c274',
      icon: 'thunder',
      guide: [{ label: '批量请求', detail: '每秒处理的 SQL 批量请求数(次/秒),无固定阈值,按业务基线看突增突降。' }],
      footer: [{ label: '锁等待', metric: 'sqlserver_lock_wait_time_rate', unit: 'cps' }]
    },
    {
      title: '缓存命中率',
      metric: 'sqlserver_buffer_cache_hit_ratio',
      color: '#27c274',
      icon: 'database',
      compare: true,
      compareFavorableDirection: 'up',
      guide: [{ label: '缓存命中率', detail: '缓冲池满足数据页读取的比例，低值说明内存或缓存压力偏高。' }],
      footer: [{ label: '页面生命周期', metric: 'sqlserver_page_life_expectancy', unit: 's' }]
    },
    {
      title: '读延迟',
      metric: 'sqlserver_database_io_read_latency_ms',
      color: '#ff8a1f',
      icon: 'api',
      compare: true,
      guide: [{ label: '读延迟', detail: '数据库文件读操作平均延迟，持续升高需排查存储性能。' }],
      footer: [
        { label: '写延迟', metric: 'sqlserver_database_io_write_latency_ms', unit: 'ms' },
        { label: '逻辑读', metric: 'sqlserver_requests_logical_reads_rate', unit: 'cps' }
      ]
    },
    {
      title: '卷可用空间',
      metric: 'sqlserver_volume_space_available_space_bytes',
      color: '#13c2c2',
      icon: 'database',
      guide: [{ label: '卷可用空间', detail: '数据库所在卷剩余空间，空间不足会影响写入和维护任务。' }],
      footer: [
        { label: '总空间', metric: 'sqlserver_volume_space_total_space_bytes', unit: 'bytes' },
        { label: '使用率', metric: 'sqlserver_volume_space_used_ratio', unit: 'percent' }
      ]
    },
    {
      title: '信号等待占比',
      metric: 'sqlserver_signal_wait_ratio',
      color: '#ff8a1f',
      icon: 'api',
      compare: true,
      guide: [{ label: '信号等待', detail: '信号等待占总等待的百分比,反映 CPU 调度排队;持续偏高排查 CPU 争用或并行度。' }],
      footer: [{ label: '总等待', metric: 'sqlserver_waitstats_wait_time_ms_rate', unit: 'ms' }]
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
        { metric: 'sqlserver_database_io_read_latency_ms', label: '读延迟', color: '#2f6bff', unit: 'ms' },
        { metric: 'sqlserver_database_io_write_latency_ms', label: '写延迟', color: '#ff8a1f', unit: 'ms' }
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
        { metric: 'sqlserver_database_io_reads_rate', label: '读取速率', color: '#2f6bff', unit: 'cps' },
        { metric: 'sqlserver_database_io_writes_rate', label: '写入速率', color: '#27c274', unit: 'cps' }
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
        { metric: 'sqlserver_cpu_sqlserver_process_cpu_avg', label: '进程 CPU', color: '#2f6bff', unit: 'percent' },
        { metric: 'sqlserver_cpu_system_idle_cpu_avg', label: '系统空闲', color: '#9aa9bf', unit: 'percent' }
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
        { metric: 'sqlserver_volume_space_used_space_bytes', label: '已用空间', color: '#2f6bff', unit: 'bytes' },
        { metric: 'sqlserver_volume_space_total_space_bytes', label: '总空间', color: '#9aa9bf', unit: 'bytes' }
      ]
    },
    {
      title: '等待时间趋势',
      subtitle: '总等待与信号等待',
      metric: 'sqlserver_waitstats_wait_time_ms_rate',
      guide: [
        { label: '总等待', detail: '各类等待累计耗时速率。' },
        { label: '信号等待', detail: '等待 CPU 调度器的时间速率。' },
        { label: '资源等待', detail: '等待外部资源的时间速率。' }
      ],
      series: [
        { metric: 'sqlserver_waitstats_wait_time_ms_rate', label: '总等待', color: '#8a5cff', unit: 'ms' },
        { metric: 'sqlserver_waitstats_signal_wait_time_ms_rate', label: '信号等待', color: '#ff8a1f', unit: 'ms' },
        { metric: 'sqlserver_waitstats_resource_wait_ms', label: '资源等待', color: '#faad14', unit: 'ms' }
      ]
    },
    {
      title: '请求耗时趋势',
      subtitle: 'CPU、等待与总耗时',
      metric: 'sqlserver_requests_total_elapsed_time_ms_rate',
      guide: [
        { label: '总耗时', detail: '请求总执行时间速率。' },
        { label: 'CPU 时间', detail: '请求消耗 CPU 时间速率。' },
        { label: '等待时间', detail: '请求等待资源时间速率。' }
      ],
      series: [
        { metric: 'sqlserver_requests_total_elapsed_time_ms_rate', label: '总耗时', color: '#8a5cff', unit: 'ms' },
        { metric: 'sqlserver_requests_cpu_time_ms_rate', label: 'CPU 时间', color: '#2f6bff', unit: 'ms' },
        { metric: 'sqlserver_requests_wait_time_ms_rate', label: '等待时间', color: '#ff8a1f', unit: 'ms' }
      ]
    }
  ],
  ringPanels: [
    {
      title: '缓存命中分布',
      subtitle: '命中与未命中',
      centerMetric: 'sqlserver_buffer_cache_hit_ratio',
      centerCaption: '命中率',
      centerUnit: 'percent',
      guide: [{ label: '缓存命中', detail: '缓冲区缓存命中率与剩余未命中占比。' }],
      segments: [
        { label: '命中', metric: 'sqlserver_buffer_cache_hit_ratio', color: '#27c274', unit: 'percent' },
        { label: '未命中', metric: 'sqlserver_buffer_cache_hit_ratio', color: '#ffccc7', unit: 'percent', transform: 'percentRemaining' }
      ]
    },
    {
      title: '存储空间分布',
      subtitle: '已用与可用',
      centerMetric: 'sqlserver_volume_space_used_ratio',
      centerCaption: '使用率',
      centerUnit: 'percent',
      guide: [{ label: '存储空间', detail: '数据库所在卷已用空间与可用空间占比。' }],
      segments: [
        { label: '已用空间', metric: 'sqlserver_volume_space_used_ratio', color: '#2f6bff', unit: 'percent' },
        { label: '可用空间', metric: 'sqlserver_volume_space_used_ratio', color: '#e8f0fe', unit: 'percent', transform: 'percentRemaining' }
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
        { label: '活跃工作线程', metric: 'sqlserver_schedulers_active_workers_count', color: '#2f6bff', unit: 'counts' },
        { label: '可运行任务', metric: 'sqlserver_schedulers_runnable_tasks_count', color: '#faad14', unit: 'counts' },
        { label: '等待任务', metric: 'sqlserver_waitstats_waiting_tasks_count', color: '#ff4d4f', unit: 'counts' }
      ]
    },
    {
      title: '请求资源消耗',
      subtitle: 'CPU、等待与总耗时',
      showTrend: true,
      guide: [{ label: '请求资源', detail: '请求 CPU 时间、等待时间和总耗时速率，用于定位高成本查询。' }],
      items: [
        { label: '总耗时', metric: 'sqlserver_requests_total_elapsed_time_ms_rate', color: '#8a5cff', unit: 'ms' },
        { label: 'CPU 时间', metric: 'sqlserver_requests_cpu_time_ms_rate', color: '#2f6bff', unit: 'ms' },
        { label: '等待时间', metric: 'sqlserver_requests_wait_time_ms_rate', color: '#ff8a1f', unit: 'ms' }
      ]
    }
  ],
  details: []
};
