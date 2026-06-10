import type { SimpleDashboardConfig } from '../common/simple-dashboard-core';

const RABBITMQ_RUNNING_ENUM = {
  0: { label: '静止', color: '#ff4d4f' },
  1: { label: '运行中', color: '#27c274' }
};

export const RABBITMQ_DASHBOARD_CONFIG: SimpleDashboardConfig = {
  routeKey: 'rabbitmq',
  pageTitle: 'RabbitMQ 监控仪表盘',
  objectFallbackName: 'RabbitMQ',
  instanceType: 'rabbitmq',
  collectionStatusQuery: "count({instance_type='rabbitmq', collect_type='middleware', __$labels__}) by (instance_id)",
  metaItems: ['Telegraf', 'middleware'],
  metrics: [
    // ── KPI (phase 1) ──
    {
      name: 'rabbitmq_node_running',
      display_name: '节点运行状态',
      description: 'RabbitMQ 节点是否处于运行中状态。',
      unit: 'none',
      query: 'rabbitmq_node_running{__$labels__}',
      color: '#27c274'
    },
    {
      name: 'rabbitmq_node_mem_used_pct',
      display_name: '内存使用率',
      description: '由内存已用量与上限推导的内存使用率（已用 / 上限）。',
      unit: 'percent',
      query: '100 * (rabbitmq_node_mem_used{__$labels__} / clamp_min(rabbitmq_node_mem_limit{__$labels__}, 1))',
      color: '#ff8a1f'
    },
    {
      name: 'rabbitmq_messages_unacked_pct',
      display_name: '未确认占比',
      description: '由未确认消息数与总消息数推导的未确认占比（未确认 / 总消息）。',
      unit: 'percent',
      query: '100 * (rabbitmq_overview_messages_unacked{__$labels__} / clamp_min(rabbitmq_overview_messages{__$labels__}, 1))',
      color: '#faad14'
    },
    {
      name: 'rabbitmq_overview_messages_ready',
      display_name: 'Ready 消息',
      description: '等待消费的 ready 消息数量，持续升高表示消费压力。',
      unit: 'counts',
      query: 'rabbitmq_overview_messages_ready{__$labels__}',
      color: '#ff8a1f'
    },
    {
      name: 'rabbitmq_overview_messages_published_rate',
      display_name: '消息发布速率',
      description: 'RabbitMQ 消息发布速率，反映生产侧写入压力。',
      unit: 'counts',
      query: 'rate(rabbitmq_overview_messages_published{__$labels__}[5m])',
      color: '#27c274'
    },
    // ── Diagnostics (phase 2) ──
    {
      name: 'rabbitmq_node_uptime',
      display_name: '节点运行时长',
      description: 'RabbitMQ 节点自启动以来的运行时长。',
      unit: 's',
      query: 'rabbitmq_node_uptime{__$labels__}',
      color: '#27c274'
    },
    {
      name: 'rabbitmq_node_mem_used',
      display_name: '节点内存已用',
      description: 'RabbitMQ 节点当前内存使用量。',
      unit: 'bytes',
      query: 'rabbitmq_node_mem_used{__$labels__}',
      color: '#8a5cff'
    },
    {
      name: 'rabbitmq_node_mem_limit',
      display_name: '节点内存上限',
      description: 'RabbitMQ 节点内存限制。',
      unit: 'bytes',
      query: 'rabbitmq_node_mem_limit{__$labels__}',
      color: '#9aa9bf'
    },
    {
      name: 'rabbitmq_node_mem_free',
      display_name: '节点内存剩余',
      description: '由内存上限与已用量推导出的剩余内存。',
      unit: 'bytes',
      query: 'clamp_min(rabbitmq_node_mem_limit{__$labels__} - rabbitmq_node_mem_used{__$labels__}, 0)',
      color: '#e8f0fe'
    },
    {
      name: 'rabbitmq_node_disk_free',
      display_name: '磁盘剩余空间',
      description: 'RabbitMQ 节点磁盘剩余空间。',
      unit: 'bytes',
      query: 'rabbitmq_node_disk_free{__$labels__}',
      color: '#27c274'
    },
    {
      name: 'rabbitmq_overview_messages',
      display_name: '总消息数',
      description: 'RabbitMQ 当前总消息数量。',
      unit: 'counts',
      query: 'rabbitmq_overview_messages{__$labels__}',
      color: '#2f6bff'
    },
    {
      name: 'rabbitmq_overview_messages_unacked',
      display_name: '未确认消息',
      description: '已投递但尚未确认的消息数量。',
      unit: 'counts',
      query: 'rabbitmq_overview_messages_unacked{__$labels__}',
      color: '#faad14'
    },
    {
      name: 'rabbitmq_overview_connections',
      display_name: '连接数',
      description: 'RabbitMQ 当前活跃客户端连接数。',
      unit: 'counts',
      query: 'rabbitmq_overview_connections{__$labels__}',
      color: '#2f6bff'
    },
    {
      name: 'rabbitmq_overview_channels',
      display_name: '通道数',
      description: 'RabbitMQ 当前打开通道数。',
      unit: 'counts',
      query: 'rabbitmq_overview_channels{__$labels__}',
      color: '#13c2c2'
    },
    {
      name: 'rabbitmq_overview_consumers',
      display_name: '消费者数',
      description: 'RabbitMQ 当前活跃消费者数量。',
      unit: 'counts',
      query: 'rabbitmq_overview_consumers{__$labels__}',
      color: '#27c274'
    },
    {
      name: 'rabbitmq_overview_queues',
      display_name: '队列数',
      description: 'RabbitMQ 当前定义队列数量。',
      unit: 'counts',
      query: 'rabbitmq_overview_queues{__$labels__}',
      color: '#8a5cff'
    },
    {
      name: 'rabbitmq_node_run_queue',
      display_name: '运行队列',
      description: 'Erlang 运行队列长度，反映节点 CPU 处理压力。',
      unit: 'counts',
      query: 'rabbitmq_node_run_queue{__$labels__}',
      color: '#ff8a1f'
    },
    {
      name: 'rabbitmq_node_mnesia_disk_tx_count_rate',
      display_name: 'Mnesia 磁盘事务速率',
      description: 'RabbitMQ Mnesia 数据库磁盘事务速率。',
      unit: 'counts',
      query: 'rate(rabbitmq_node_mnesia_disk_tx_count{__$labels__}[5m])',
      color: '#13c2c2'
    },
    {
      name: 'rabbitmq_node_fd_used',
      display_name: '文件描述符使用数',
      description: 'RabbitMQ 节点当前使用文件描述符数量。',
      unit: 'counts',
      query: 'rabbitmq_node_fd_used{__$labels__}',
      color: '#2f6bff'
    },
    {
      name: 'rabbitmq_node_sockets_used',
      display_name: 'Socket 使用数',
      description: 'RabbitMQ 节点当前使用 Socket 数量。',
      unit: 'counts',
      query: 'rabbitmq_node_sockets_used{__$labels__}',
      color: '#13c2c2'
    },
    {
      name: 'rabbitmq_node_proc_used',
      display_name: '进程使用数',
      description: 'RabbitMQ 节点当前 Erlang 进程使用数量。',
      unit: 'counts',
      query: 'rabbitmq_node_proc_used{__$labels__}',
      color: '#8a5cff'
    }
  ],
  summaryCards: [
    {
      title: '运行时长',
      metric: 'rabbitmq_node_uptime',
      unit: 's',
      formatter: 'duration',
      isUptimeCard: true,
      icon: 'clock',
      color: '#597ef7',
      guide: [{ label: '运行时长', detail: '实例自上次启动后的持续运行时间;期间发生重启会重新计时。' }],
      footer: [{ label: '启动', metric: 'rabbitmq_node_uptime', formatter: 'startedAt' }]
    },
    {
      title: '节点健康',
      metric: 'rabbitmq_node_running',
      color: '#27c274',
      icon: 'health',
      enumMap: RABBITMQ_RUNNING_ENUM,
      guide: [{ label: '节点健康', detail: 'RabbitMQ 节点是否运行中。先确认节点存活，再看下游容量与积压指标。' }],
      footer: [
        { label: '内存使用率', metric: 'rabbitmq_node_mem_used_pct', unit: 'percent' },
        { label: '磁盘剩余', metric: 'rabbitmq_node_disk_free', unit: 'bytes' }
      ]
    },
    {
      title: '内存使用率',
      metric: 'rabbitmq_node_mem_used_pct',
      unit: 'percent',
      color: '#ff8a1f',
      icon: 'memory',
      compare: true,
      compareFavorableDirection: 'down',
      guide: [{ label: '内存使用率', detail: '内存已用占上限比例。逼近 100% 会触发 mem_alarm 并阻塞生产者，应在此前扩容或降载。' }],
      footer: [
        { label: '已用', metric: 'rabbitmq_node_mem_used', unit: 'bytes' },
        { label: '上限', metric: 'rabbitmq_node_mem_limit', unit: 'bytes' }
      ]
    },
    {
      title: '未确认占比',
      metric: 'rabbitmq_messages_unacked_pct',
      unit: 'percent',
      color: '#faad14',
      icon: 'unacked',
      compare: true,
      compareFavorableDirection: 'down',
      guide: [{ label: '未确认占比', detail: '未确认消息占总消息比例升高，说明消费者确认变慢或消费能力不足。' }],
      footer: [
        { label: '未确认', metric: 'rabbitmq_overview_messages_unacked', unit: 'counts' },
        { label: '总消息', metric: 'rabbitmq_overview_messages', unit: 'counts' }
      ]
    },
    {
      title: '消息积压',
      metric: 'rabbitmq_overview_messages_ready',
      unit: 'counts',
      color: '#2f6bff',
      icon: 'backlog',
      compare: true,
      compareFavorableDirection: 'down',
      guide: [{ label: '消息积压', detail: '等待消费的 ready 消息。持续上升说明生产快于消费，需扩消费者或排查消费阻塞。' }],
      footer: [
        { label: '发布速率', metric: 'rabbitmq_overview_messages_published_rate', unit: 'counts' },
        { label: '消费者', metric: 'rabbitmq_overview_consumers', unit: 'counts' }
      ]
    }
  ],
  charts: [
    {
      title: '内存压力趋势',
      subtitle: '已用 vs 上限',
      metric: 'rabbitmq_node_mem_used',
      guide: [{ label: '内存压力', detail: '虚线为内存上限，实线为已用量。两线收敛即内存告警风险。' }],
      series: [
        { metric: 'rabbitmq_node_mem_used', label: '已用内存', color: '#8a5cff', unit: 'bytes' },
        { metric: 'rabbitmq_node_mem_limit', label: '内存上限', color: '#9aa9bf', unit: 'bytes', style: 'limit' }
      ]
    },
    {
      title: '消息流转趋势',
      subtitle: '总量、Ready、未确认、发布速率',
      metric: 'rabbitmq_overview_messages',
      guide: [{ label: '消息流转', detail: '对比总消息、ready、未确认与发布速率，识别积压结构是堆积未消费还是确认滞后。' }],
      series: [
        { metric: 'rabbitmq_overview_messages', label: '总消息', color: '#2f6bff', unit: 'counts' },
        { metric: 'rabbitmq_overview_messages_ready', label: 'Ready', color: '#ff8a1f', unit: 'counts' },
        { metric: 'rabbitmq_overview_messages_unacked', label: '未确认', color: '#faad14', unit: 'counts' },
        { metric: 'rabbitmq_overview_messages_published_rate', label: '发布速率', color: '#27c274', unit: 'counts' }
      ]
    },
    {
      title: '句柄资源趋势',
      subtitle: 'FD、Socket、进程',
      metric: 'rabbitmq_node_fd_used',
      guide: [{ label: '句柄资源', detail: '对比文件描述符、Socket 与 Erlang 进程使用量，识别资源耗尽风险。' }],
      series: [
        { metric: 'rabbitmq_node_fd_used', label: 'FD', color: '#2f6bff', unit: 'counts' },
        { metric: 'rabbitmq_node_sockets_used', label: 'Socket', color: '#13c2c2', unit: 'counts' },
        { metric: 'rabbitmq_node_proc_used', label: '进程', color: '#8a5cff', unit: 'counts' }
      ]
    },
    {
      title: '节点负载趋势',
      subtitle: '运行队列、Mnesia 事务',
      metric: 'rabbitmq_node_run_queue',
      guide: [{ label: '节点负载', detail: '运行队列反映 CPU 排队压力，Mnesia 事务速率反映元数据写盘压力。' }],
      series: [
        { metric: 'rabbitmq_node_run_queue', label: '运行队列', color: '#ff8a1f', unit: 'counts' },
        { metric: 'rabbitmq_node_mnesia_disk_tx_count_rate', label: 'Mnesia 事务', color: '#13c2c2', unit: 'counts' }
      ]
    }
  ],
  ringPanels: [
    {
      title: '节点内存分布',
      subtitle: '已用 vs 剩余',
      centerMetric: 'rabbitmq_node_mem_used_pct',
      centerCaption: '内存使用率',
      centerUnit: 'percent',
      guide: [{ label: '内存分布', detail: '按已用与剩余拆分节点内存，中心为使用率。' }],
      segments: [
        { label: '已用内存', metric: 'rabbitmq_node_mem_used', color: '#8a5cff', unit: 'bytes' },
        { label: '剩余内存', metric: 'rabbitmq_node_mem_free', color: '#e8f0fe', unit: 'bytes' }
      ]
    }
  ],
  statusPanels: [],
  details: [
    {
      title: '队列与资源详情',
      subtitle: '队列、磁盘、连接',
      rows: [
        { label: '队列数', metric: 'rabbitmq_overview_queues', unit: 'counts' },
        { label: '磁盘剩余空间', metric: 'rabbitmq_node_disk_free', unit: 'bytes' },
        { label: '连接数', metric: 'rabbitmq_overview_connections', unit: 'counts' }
      ]
    }
  ]
};
