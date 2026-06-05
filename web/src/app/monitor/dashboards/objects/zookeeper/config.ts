import type { SimpleDashboardConfig } from '../common/simple-dashboard-core';

export const ZOOKEEPER_DASHBOARD_CONFIG: SimpleDashboardConfig = {
  routeKey: 'zookeeper',
  pageTitle: 'Zookeeper 监控仪表盘',
  objectFallbackName: 'Zookeeper',
  instanceType: 'zookeeper',
  collectionStatusQuery: "count({instance_type='zookeeper', collect_type='middleware', __$labels__}) by (instance_id)",
  metaItems: ['Telegraf', 'middleware'],
  metaMetrics: [{ label: '版本', metric: 'zookeeper_version', unit: 'none' }],
  metrics: [
    // ── KPI (phase 1) ──
    {
      name: 'zookeeper_version',
      display_name: '版本信息',
      description: 'Zookeeper 版本信息。',
      unit: 'none',
      query: 'zookeeper_version{__$labels__}',
      color: '#9aa9bf'
    },
    {
      name: 'zookeeper_num_alive_connections',
      display_name: '存活连接数',
      description: 'Zookeeper 当前存活连接数量。',
      unit: 'counts',
      query: 'zookeeper_num_alive_connections{__$labels__}',
      color: '#2f6bff'
    },
    {
      name: 'zookeeper_outstanding_requests',
      display_name: 'Outstanding 请求',
      description: 'Zookeeper 当前未完成请求数量。',
      unit: 'counts',
      query: 'zookeeper_outstanding_requests{__$labels__}',
      color: '#ff8a1f'
    },
    {
      name: 'zookeeper_avg_latency',
      display_name: '平均延迟',
      description: 'Zookeeper 当前平均请求延迟。',
      unit: 'ms',
      query: 'zookeeper_avg_latency{__$labels__}',
      color: '#27c274'
    },
    {
      name: 'zookeeper_max_latency',
      display_name: '最大延迟',
      description: 'Zookeeper 当前最大请求延迟。',
      unit: 'ms',
      query: 'zookeeper_max_latency{__$labels__}',
      color: '#ff8a1f'
    },
    {
      name: 'zookeeper_znode_count',
      display_name: 'ZNode 数',
      description: 'Zookeeper 当前 znode 数量。',
      unit: 'counts',
      query: 'zookeeper_znode_count{__$labels__}',
      color: '#2f6bff'
    },
    {
      name: 'zookeeper_fd_used_pct',
      display_name: 'FD 使用率',
      description: '由已打开文件描述符数与最大文件描述符数推导出的使用率（已用 / 上限）。',
      unit: 'percent',
      query: 'clamp_max(100 * (zookeeper_open_file_descriptor_count{__$labels__} / clamp_min(zookeeper_max_file_descriptor_count{__$labels__}, 1)), 100)',
      color: '#faad14'
    },
    // ── Diagnostics (phase 2) ──
    {
      name: 'zookeeper_min_latency',
      display_name: '最小延迟',
      description: 'Zookeeper 当前最小请求延迟。',
      unit: 'ms',
      query: 'zookeeper_min_latency{__$labels__}',
      color: '#13c2c2'
    },
    {
      name: 'zookeeper_watch_count',
      display_name: 'Watch 数',
      description: 'Zookeeper 当前 watch 数量。',
      unit: 'counts',
      query: 'zookeeper_watch_count{__$labels__}',
      color: '#8a5cff'
    },
    {
      name: 'zookeeper_ephemerals_count',
      display_name: '临时节点数',
      description: 'Zookeeper 当前临时节点数量。',
      unit: 'counts',
      query: 'zookeeper_ephemerals_count{__$labels__}',
      color: '#13c2c2'
    },
    {
      name: 'zookeeper_approximate_data_size',
      display_name: '数据大小',
      description: 'Zookeeper 近似数据大小。',
      unit: 'bytes',
      query: 'zookeeper_approximate_data_size{__$labels__}',
      color: '#8a5cff'
    },
    {
      name: 'zookeeper_open_file_descriptor_count',
      display_name: '打开文件描述符',
      description: 'Zookeeper 当前打开文件描述符数量。',
      unit: 'counts',
      query: 'zookeeper_open_file_descriptor_count{__$labels__}',
      color: '#ff8a1f'
    },
    {
      name: 'zookeeper_max_file_descriptor_count',
      display_name: '最大文件描述符',
      description: 'Zookeeper 最大文件描述符数量。',
      unit: 'counts',
      query: 'zookeeper_max_file_descriptor_count{__$labels__}',
      color: '#9aa9bf'
    },
    {
      name: 'zookeeper_file_descriptor_free',
      display_name: '可用文件描述符',
      description: '由最大文件描述符数和已打开文件描述符数推导出的可用数量。',
      unit: 'counts',
      query: 'clamp_min(zookeeper_max_file_descriptor_count{__$labels__} - zookeeper_open_file_descriptor_count{__$labels__}, 0)',
      color: '#27c274'
    },
    {
      name: 'zookeeper_fsync_threshold_exceed_count',
      display_name: 'Fsync 超阈次数',
      description: 'Zookeeper fsync 超过阈值的累计次数。',
      unit: 'counts',
      query: 'zookeeper_fsync_threshold_exceed_count{__$labels__}',
      color: '#ff4d4f'
    },
    {
      name: 'zookeeper_packets_received_rate',
      display_name: '包接收速率',
      description: 'Zookeeper 网络包接收速率。',
      unit: 'cps',
      query: 'zookeeper_packets_received_rate{__$labels__}',
      color: '#2f6bff'
    },
    {
      name: 'zookeeper_packets_sent_rate',
      display_name: '包发送速率',
      description: 'Zookeeper 网络包发送速率。',
      unit: 'cps',
      query: 'zookeeper_packets_sent_rate{__$labels__}',
      color: '#27c274'
    },
    {
      name: 'zookeeper_fsync_threshold_exceed_rate',
      display_name: 'Fsync 超阈速率',
      description: 'Zookeeper fsync 超过阈值的速率。',
      unit: 'cps',
      query: 'zookeeper_fsync_threshold_exceed_rate{__$labels__}',
      color: '#ff4d4f'
    }
  ],
  summaryCards: [
    {
      title: '存活连接数',
      metric: 'zookeeper_num_alive_connections',
      color: '#2f6bff',
      icon: 'node',
      guide: [{ label: '存活连接', detail: '当前与 Zookeeper 保持连接的客户端数量。' }],
      footer: [{ label: 'Outstanding', metric: 'zookeeper_outstanding_requests', unit: 'counts' }]
    },
    {
      title: 'Outstanding 请求',
      metric: 'zookeeper_outstanding_requests',
      color: '#ff8a1f',
      icon: 'api',
      compare: true,
      compareFavorableDirection: 'down',
      guide: [{ label: 'Outstanding', detail: '当前未完成请求数量，持续升高表示处理积压。' }],
      footer: [{ label: '平均延迟', metric: 'zookeeper_avg_latency', unit: 'ms' }]
    },
    {
      title: '平均延迟',
      metric: 'zookeeper_avg_latency',
      color: '#27c274',
      icon: 'clock',
      compare: true,
      compareFavorableDirection: 'down',
      guide: [{ label: '平均延迟', detail: '当前平均请求延迟，反映常态响应速度。' }],
      footer: [{ label: '最大延迟', metric: 'zookeeper_max_latency', unit: 'ms' }]
    },
    {
      title: 'ZNode 数',
      metric: 'zookeeper_znode_count',
      color: '#2f6bff',
      icon: 'database',
      guide: [{ label: 'ZNode', detail: '当前 Zookeeper znode 数量，反映数据结构规模。' }],
      footer: [{ label: 'Watch 数', metric: 'zookeeper_watch_count', unit: 'counts' }]
    },
    {
      title: 'FD 使用率',
      metric: 'zookeeper_fd_used_pct',
      unit: 'percent',
      color: '#faad14',
      icon: 'database',
      compare: true,
      compareFavorableDirection: 'down',
      guide: [{ label: 'FD 使用率', detail: '已打开文件描述符占系统上限的比例。接近 100% 时进程可能无法建立新连接或写入文件。' }],
      footer: [
        { label: '已用 FD', metric: 'zookeeper_open_file_descriptor_count', unit: 'counts' },
        { label: '最大 FD', metric: 'zookeeper_max_file_descriptor_count', unit: 'counts' }
      ]
    }
  ],
  charts: [
    {
      title: '包收发速率趋势',
      subtitle: '接收、发送包',
      metric: 'zookeeper_packets_received_rate',
      guide: [{ label: '包速率', detail: '对比 Zookeeper 网络包接收和发送速率，观察交互吞吐。' }],
      series: [
        { metric: 'zookeeper_packets_received_rate', label: '接收包', color: '#2f6bff', unit: 'cps' },
        { metric: 'zookeeper_packets_sent_rate', label: '发送包', color: '#27c274', unit: 'cps' }
      ]
    },
    {
      title: '请求延迟趋势',
      subtitle: '最小（参考）、平均、最大',
      metric: 'zookeeper_avg_latency',
      guide: [{ label: '请求延迟', detail: '对比平均和最大延迟，判断 Zookeeper 响应稳定性。最小延迟为虚线参考基准。' }],
      series: [
        { metric: 'zookeeper_min_latency', label: '最小延迟', color: '#13c2c2', unit: 'ms', style: 'limit' },
        { metric: 'zookeeper_avg_latency', label: '平均延迟', color: '#27c274', unit: 'ms' },
        { metric: 'zookeeper_max_latency', label: '最大延迟', color: '#ff8a1f', unit: 'ms' }
      ]
    },
    {
      title: '连接数趋势',
      subtitle: '存活连接数变化',
      metric: 'zookeeper_num_alive_connections',
      guide: [{ label: '连接数趋势', detail: '存活连接数的历史走势，帮助识别连接风暴或客户端断开等事件。' }],
      series: [
        { metric: 'zookeeper_num_alive_connections', label: '存活连接数', color: '#2f6bff', unit: 'counts' }
      ]
    },
    {
      title: 'Outstanding 请求趋势',
      subtitle: '未完成请求数变化',
      metric: 'zookeeper_outstanding_requests',
      guide: [{ label: 'Outstanding 趋势', detail: '未完成请求数历史走势，持续升高说明服务端处理能力跟不上请求速率。' }],
      series: [
        { metric: 'zookeeper_outstanding_requests', label: 'Outstanding', color: '#ff8a1f', unit: 'counts' }
      ]
    },
    {
      title: '数据对象趋势',
      subtitle: 'Watch、临时节点',
      metric: 'zookeeper_watch_count',
      guide: [{ label: '数据对象', detail: '对比 watch 和临时节点数量变化，识别客户端注册压力或会话泄露。' }],
      series: [
        { metric: 'zookeeper_watch_count', label: 'Watch', color: '#8a5cff', unit: 'counts' },
        { metric: 'zookeeper_ephemerals_count', label: '临时节点', color: '#13c2c2', unit: 'counts' }
      ]
    }
  ],
  ringPanels: [
    {
      title: '文件描述符分布',
      subtitle: '打开、可用',
      centerMetric: 'zookeeper_open_file_descriptor_count',
      centerCaption: '打开 FD',
      centerUnit: 'counts',
      guide: [{ label: '文件描述符', detail: '按已打开和可用文件描述符拆分当前资源状态。' }],
      segments: [
        { label: '打开 FD', metric: 'zookeeper_open_file_descriptor_count', color: '#ff8a1f', unit: 'counts' },
        { label: '可用 FD', metric: 'zookeeper_file_descriptor_free', color: '#27c274', unit: 'counts' }
      ]
    }
  ],
  barPanels: [
    {
      title: 'Fsync 超阈快照',
      subtitle: '超阈次数、速率',
      showTrend: true,
      guide: [{ label: 'Fsync 超阈', detail: 'fsync 超过阈值的累计次数与当前速率。通常为 0；非零时表示磁盘同步存在延迟问题。' }],
      items: [
        { label: '超阈次数', metric: 'zookeeper_fsync_threshold_exceed_count', color: '#ff4d4f', unit: 'counts' },
        { label: '超阈速率', metric: 'zookeeper_fsync_threshold_exceed_rate', color: '#faad14', unit: 'cps' }
      ]
    }
  ],
  details: [
    {
      title: 'Zookeeper 详情',
      subtitle: '数据与容量',
      rows: [
        { label: '数据大小', metric: 'zookeeper_approximate_data_size', unit: 'bytes' },
        { label: 'Fsync 超阈次数', metric: 'zookeeper_fsync_threshold_exceed_count', unit: 'counts' }
      ]
    }
  ]
};
