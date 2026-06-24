import type { SimpleDashboardConfig } from '../common/simple-dashboard-core';

// IBM MQ 队列管理器状态枚举（与 metrics.json 的 ibmmq_qmgr_status_gauge 一致）。
const IBMMQ_QMGR_STATUS_ENUM = {
  0: { label: '已停止', color: '#ff4d4f' },
  1: { label: '启动中', color: '#fa8c16' },
  2: { label: '运行中', color: '#1ac44a' },
  3: { label: '正在停止', color: '#fa8c16' },
  4: { label: '待命', color: '#1890ff' }
};

export const IBMMQ_DASHBOARD_CONFIG: SimpleDashboardConfig = {
  routeKey: 'ibmmq',
  pageTitle: 'IBM MQ 监控仪表盘',
  objectFallbackName: 'IBM MQ',
  instanceType: 'ibmmq',
  collectionStatusQuery:
    "count({instance_type='ibmmq', collect_type='exporter', __$labels__}) by (instance_id)",
  metaItems: ['IBM-MQ-Exporter', 'exporter'],
  metrics: [
    // ── KPI ──
    {
      name: 'ibmmq_qmgr_status_gauge',
      display_name: '队列管理器状态',
      description: '队列管理器当前运行状态。0 已停止、1 启动中、2 运行中、3 正在停止、4 待命。',
      unit: 'none',
      query: 'ibmmq_qmgr_status_gauge{__$labels__}',
      color: '#1ac44a'
    },
    {
      name: 'ibmmq_qmgr_uptime_gauge',
      display_name: '运行时长',
      description: '队列管理器自上次启动以来的持续运行时长。',
      unit: 's',
      query: 'ibmmq_qmgr_uptime_gauge{__$labels__}',
      color: '#597ef7'
    },
    {
      name: 'ibmmq_qmgr_connection_count_gauge',
      display_name: '连接数',
      description: '当前连接到队列管理器的活动连接数量。',
      unit: 'counts',
      query: 'ibmmq_qmgr_connection_count_gauge{__$labels__}',
      color: '#2f6bff'
    },
    {
      name: 'ibmmq_ram_used_pct',
      display_name: '内存使用率',
      description: '由空闲内存百分比推导的主机内存使用率（100 − 空闲%）。',
      unit: 'percent',
      query: '100 - ibmmq_qmgr_ram_free_percentage_gauge{__$labels__}',
      color: '#ff8a1f'
    },
    {
      name: 'ibmmq_qmgr_log_current_primary_space_in_use_percentage_gauge',
      display_name: '主日志空间使用率',
      description: '当前主日志空间使用百分比，逼近 100% 会阻塞持久消息写入。',
      unit: 'percent',
      query: 'ibmmq_qmgr_log_current_primary_space_in_use_percentage_gauge{__$labels__}',
      color: '#faad14'
    },
    {
      name: 'ibmmq_queue_depth_gauge',
      display_name: '队列深度',
      description: '各队列当前消息数量，持续升高表示消费不及导致积压。',
      unit: 'counts',
      query: 'ibmmq_queue_depth_gauge{__$labels__}',
      color: '#8a5cff'
    },
    // ── 资源 ──
    {
      name: 'ibmmq_qmgr_cpu_load_one_minute_average_percentage_gauge',
      display_name: 'CPU 1m 平均负载',
      description: '队列管理器主机最近一分钟的 CPU 平均负载百分比。',
      unit: 'percent',
      query: 'ibmmq_qmgr_cpu_load_one_minute_average_percentage_gauge{__$labels__}',
      color: '#ff8a1f'
    },
    {
      name: 'ibmmq_qmgr_cpu_load_five_minute_average_percentage_gauge',
      display_name: 'CPU 5m 平均负载',
      description: '队列管理器主机最近五分钟的 CPU 平均负载百分比。',
      unit: 'percent',
      query: 'ibmmq_qmgr_cpu_load_five_minute_average_percentage_gauge{__$labels__}',
      color: '#fa8c16'
    },
    {
      name: 'ibmmq_qmgr_ram_free_percentage_gauge',
      display_name: '空闲内存比例',
      description: '队列管理器主机的空闲内存百分比。',
      unit: 'percent',
      query: 'ibmmq_qmgr_ram_free_percentage_gauge{__$labels__}',
      color: '#27c274'
    },
    {
      name: 'ibmmq_ram_used_bytes',
      display_name: '已用内存',
      description: '由总内存与空闲比例推导的已用内存量。',
      unit: 'bytes',
      query:
        'ibmmq_qmgr_ram_total_bytes_gauge{__$labels__} * (1 - ibmmq_qmgr_ram_free_percentage_gauge{__$labels__} / 100)',
      color: '#8a5cff'
    },
    {
      name: 'ibmmq_ram_free_bytes',
      display_name: '空闲内存',
      description: '由总内存与空闲比例推导的空闲内存量。',
      unit: 'bytes',
      query:
        'ibmmq_qmgr_ram_total_bytes_gauge{__$labels__} * ibmmq_qmgr_ram_free_percentage_gauge{__$labels__} / 100',
      color: '#e8f0fe'
    },
    // ── 连接 ──
    {
      name: 'ibmmq_qmgr_active_listeners_gauge',
      display_name: '活动监听器',
      description: '队列管理器上处于活动状态的监听器数量。',
      unit: 'counts',
      query: 'ibmmq_qmgr_active_listeners_gauge{__$labels__}',
      color: '#13c2c2'
    },
    {
      name: 'ibmmq_qmgr_concurrent_connections_high_water_mark_gauge',
      display_name: '并发连接高水位',
      description: '队列管理器并发连接数的峰值（高水位标记）。',
      unit: 'counts',
      query: 'ibmmq_qmgr_concurrent_connections_high_water_mark_gauge{__$labels__}',
      color: '#9254de'
    },
    // ── 日志 ──
    {
      name: 'ibmmq_qmgr_log_in_use_bytes_gauge',
      display_name: '日志已用空间',
      description: '当前正在使用的恢复日志空间。',
      unit: 'bytes',
      query: 'ibmmq_qmgr_log_in_use_bytes_gauge{__$labels__}',
      color: '#faad14'
    },
    {
      name: 'ibmmq_qmgr_log_max_bytes_gauge',
      display_name: '日志容量上限',
      description: '恢复日志的最大容量。',
      unit: 'bytes',
      query: 'ibmmq_qmgr_log_max_bytes_gauge{__$labels__}',
      color: '#9aa9bf'
    },
    {
      name: 'ibmmq_qmgr_log_write_latency_seconds_gauge',
      display_name: '日志写入延迟',
      description: '日志写入的平均延迟，升高说明磁盘写盘压力大。',
      unit: 's',
      query: 'ibmmq_qmgr_log_write_latency_seconds_gauge{__$labels__}',
      color: '#ff7875'
    },
    // ── 队列 ──
    {
      name: 'ibmmq_queue_uncommitted_messages_gauge',
      display_name: '未提交消息',
      description: '队列中尚未提交的消息数量，过多通常表示存在长事务或回滚。',
      unit: 'counts',
      query: 'ibmmq_queue_uncommitted_messages_gauge{__$labels__}',
      color: '#faad14'
    },
    {
      name: 'ibmmq_queue_oldest_message_age_gauge',
      display_name: '最早消息时长',
      description: '队列中最早一条消息的滞留时长，过长说明消费停滞。',
      unit: 's',
      query: 'ibmmq_queue_oldest_message_age_gauge{__$labels__}',
      color: '#ff8a1f'
    },
    {
      name: 'ibmmq_queue_qtime_short_gauge',
      display_name: '短期排队时间',
      description: '消息在队列中停留时间的短周期平均值。',
      unit: 's',
      query: 'ibmmq_queue_qtime_short_gauge{__$labels__}',
      color: '#2f6bff'
    },
    {
      name: 'ibmmq_queue_qtime_long_gauge',
      display_name: '长期排队时间',
      description: '消息在队列中停留时间的长周期平均值。',
      unit: 's',
      query: 'ibmmq_queue_qtime_long_gauge{__$labels__}',
      color: '#13c2c2'
    },
    // ── 主题/订阅 ──
    {
      name: 'ibmmq_topic_publisher_count_gauge',
      display_name: '发布者数量',
      description: '主题上活动的发布者数量。',
      unit: 'counts',
      query: 'ibmmq_topic_publisher_count_gauge{__$labels__}',
      color: '#27c274'
    },
    {
      name: 'ibmmq_topic_subscriber_count_gauge',
      display_name: '订阅者数量',
      description: '主题上活动的订阅者数量。',
      unit: 'counts',
      query: 'ibmmq_topic_subscriber_count_gauge{__$labels__}',
      color: '#597ef7'
    }
  ],
  summaryCards: [
    {
      title: '运行时长',
      metric: 'ibmmq_qmgr_uptime_gauge',
      unit: 's',
      formatter: 'duration',
      isUptimeCard: true,
      icon: 'clock',
      color: '#597ef7',
      guide: [{ label: '运行时长', detail: '队列管理器自上次启动后的持续运行时间；期间重启会重新计时。' }],
      footer: [{ label: '启动', metric: 'ibmmq_qmgr_uptime_gauge', formatter: 'startedAt' }]
    },
    {
      title: '队列管理器状态',
      metric: 'ibmmq_qmgr_status_gauge',
      color: '#1ac44a',
      icon: 'health',
      enumMap: IBMMQ_QMGR_STATUS_ENUM,
      guide: [{ label: '队列管理器状态', detail: '是否运行中。非运行状态下消息无法收发，应先恢复队列管理器再看下游容量。' }],
      footer: [
        { label: '连接数', metric: 'ibmmq_qmgr_connection_count_gauge', unit: 'counts' },
        { label: '监听器', metric: 'ibmmq_qmgr_active_listeners_gauge', unit: 'counts' }
      ]
    },
    {
      title: '连接数',
      metric: 'ibmmq_qmgr_connection_count_gauge',
      unit: 'counts',
      color: '#2f6bff',
      icon: 'node',
      compare: true,
      compareFavorableDirection: 'down',
      guide: [{ label: '连接数', detail: '当前活动客户端连接数。逼近并发高水位时需关注连接句柄与资源上限。' }],
      footer: [{ label: '并发高水位', metric: 'ibmmq_qmgr_concurrent_connections_high_water_mark_gauge', unit: 'counts' }]
    },
    {
      title: '内存使用率',
      metric: 'ibmmq_ram_used_pct',
      unit: 'percent',
      color: '#ff8a1f',
      icon: 'memory',
      compare: true,
      compareFavorableDirection: 'down',
      guide: [{ label: '内存使用率', detail: '主机内存已用占比。逼近 100% 会拖慢队列管理器并影响消息吞吐。' }],
      footer: [
        { label: '已用', metric: 'ibmmq_ram_used_bytes', unit: 'bytes' },
        { label: '空闲', metric: 'ibmmq_qmgr_ram_free_percentage_gauge', unit: 'percent' }
      ]
    },
    {
      title: '主日志空间',
      metric: 'ibmmq_qmgr_log_current_primary_space_in_use_percentage_gauge',
      unit: 'percent',
      color: '#faad14',
      icon: 'backlog',
      compare: true,
      compareFavorableDirection: 'down',
      guide: [{ label: '主日志空间', detail: '主日志空间使用率。耗尽会阻塞持久消息写入，需检查日志配置与归档。' }],
      footer: [
        { label: '日志已用', metric: 'ibmmq_qmgr_log_in_use_bytes_gauge', unit: 'bytes' },
        { label: '写入延迟', metric: 'ibmmq_qmgr_log_write_latency_seconds_gauge', unit: 's' }
      ]
    },
    {
      title: '消息积压',
      metric: 'ibmmq_queue_depth_gauge',
      unit: 'counts',
      color: '#8a5cff',
      icon: 'backlog',
      compare: true,
      compareFavorableDirection: 'down',
      guide: [{ label: '消息积压', detail: '队列当前消息数。持续上升说明生产快于消费，需扩消费端或排查阻塞。' }],
      footer: [
        { label: '未提交', metric: 'ibmmq_queue_uncommitted_messages_gauge', unit: 'counts' },
        { label: '最早消息', metric: 'ibmmq_queue_oldest_message_age_gauge', unit: 's' }
      ]
    }
  ],
  charts: [
    {
      title: '资源压力趋势',
      subtitle: 'CPU 负载与内存',
      metric: 'ibmmq_qmgr_cpu_load_one_minute_average_percentage_gauge',
      guide: [{ label: '资源压力', detail: '对比 CPU 一/五分钟负载与内存使用率，识别队列管理器主机资源瓶颈。' }],
      series: [
        { metric: 'ibmmq_qmgr_cpu_load_one_minute_average_percentage_gauge', label: 'CPU 1m', color: '#ff8a1f', unit: 'percent' },
        { metric: 'ibmmq_qmgr_cpu_load_five_minute_average_percentage_gauge', label: 'CPU 5m', color: '#fa8c16', unit: 'percent' },
        { metric: 'ibmmq_ram_used_pct', label: '内存使用率', color: '#8a5cff', unit: 'percent' }
      ]
    },
    {
      title: '连接趋势',
      subtitle: '连接、监听器与高水位',
      metric: 'ibmmq_qmgr_connection_count_gauge',
      guide: [{ label: '连接趋势', detail: '对比活动连接、监听器与并发高水位，识别连接资源耗尽风险。' }],
      series: [
        { metric: 'ibmmq_qmgr_connection_count_gauge', label: '当前连接', color: '#2f6bff', unit: 'counts' },
        { metric: 'ibmmq_qmgr_active_listeners_gauge', label: '活动监听器', color: '#13c2c2', unit: 'counts' },
        { metric: 'ibmmq_qmgr_concurrent_connections_high_water_mark_gauge', label: '并发高水位', color: '#9254de', unit: 'counts' }
      ]
    },
    {
      title: '日志空间趋势',
      subtitle: '已用 vs 容量上限',
      metric: 'ibmmq_qmgr_log_in_use_bytes_gauge',
      guide: [{ label: '日志空间', detail: '虚线为日志容量上限，实线为已用量。两线收敛即日志耗尽风险。' }],
      series: [
        { metric: 'ibmmq_qmgr_log_in_use_bytes_gauge', label: '日志已用', color: '#faad14', unit: 'bytes' },
        { metric: 'ibmmq_qmgr_log_max_bytes_gauge', label: '容量上限', color: '#9aa9bf', unit: 'bytes', style: 'limit' }
      ]
    },
    {
      title: '队列排队趋势',
      subtitle: '深度、未提交与排队时间',
      metric: 'ibmmq_queue_depth_gauge',
      guide: [{ label: '队列排队', detail: '对比队列深度、未提交消息与短/长期排队时间，定位积压是堆积还是确认滞后。' }],
      series: [
        { metric: 'ibmmq_queue_depth_gauge', label: '队列深度', color: '#8a5cff', unit: 'counts' },
        { metric: 'ibmmq_queue_uncommitted_messages_gauge', label: '未提交', color: '#faad14', unit: 'counts' },
        { metric: 'ibmmq_queue_qtime_short_gauge', label: '短期排队', color: '#2f6bff', unit: 's' },
        { metric: 'ibmmq_queue_qtime_long_gauge', label: '长期排队', color: '#13c2c2', unit: 's' }
      ]
    }
  ],
  ringPanels: [
    {
      title: '主机内存分布',
      subtitle: '已用 vs 空闲',
      centerMetric: 'ibmmq_ram_used_pct',
      centerCaption: '内存使用率',
      centerUnit: 'percent',
      guide: [{ label: '内存分布', detail: '按已用与空闲拆分主机内存，中心为使用率。' }],
      segments: [
        { label: '已用内存', metric: 'ibmmq_ram_used_bytes', color: '#8a5cff', unit: 'bytes' },
        { label: '空闲内存', metric: 'ibmmq_ram_free_bytes', color: '#e8f0fe', unit: 'bytes' }
      ]
    }
  ],
  statusPanels: [],
  details: [
    {
      title: '主题与订阅详情',
      subtitle: '发布者、订阅者与日志延迟',
      rows: [
        { label: '发布者数量', metric: 'ibmmq_topic_publisher_count_gauge', unit: 'counts' },
        { label: '订阅者数量', metric: 'ibmmq_topic_subscriber_count_gauge', unit: 'counts' },
        { label: '日志写入延迟', metric: 'ibmmq_qmgr_log_write_latency_seconds_gauge', unit: 's' }
      ]
    }
  ]
};
