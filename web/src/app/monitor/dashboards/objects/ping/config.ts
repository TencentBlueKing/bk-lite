import type { SimpleDashboardConfig } from '../common/simple-dashboard-core';

export const PING_DASHBOARD_CONFIG: SimpleDashboardConfig = {
  routeKey: 'ping',
  pageTitle: 'Ping 监控仪表盘',
  objectFallbackName: 'Ping',
  instanceType: 'ping',
  collectionStatusQuery: "count({instance_type='ping', collect_type='ping', __$labels__}) by (instance_id)",
  metaItems: ['Telegraf', 'ping'],
  metrics: [
    {
      name: 'ping_latency_avg',
      display_name: '平均延迟',
      description: 'Ping 探测节点的平均延迟。',
      unit: 'ms',
      query: 'avg(ping_average_response_ms{__$labels__})',
      color: '#2f6bff'
    },
    {
      name: 'ping_latency_min',
      display_name: '最小延迟',
      description: 'Ping 探测节点的最小延迟。',
      unit: 'ms',
      query: 'min(ping_minimum_response_ms{__$labels__})',
      color: '#13c2c2'
    },
    {
      name: 'ping_latency_max',
      display_name: '最大延迟',
      description: 'Ping 探测节点的最大延迟。',
      unit: 'ms',
      query: 'max(ping_maximum_response_ms{__$labels__})',
      color: '#ff8a1f'
    },
    {
      name: 'ping_packet_loss_avg',
      display_name: '平均丢包率',
      description: 'Ping 探测节点的平均丢包率。',
      unit: 'percent',
      query: 'avg(ping_percent_packet_loss{__$labels__})',
      color: '#ff4d4f'
    },
    {
      name: 'ping_success_rate_avg',
      display_name: '连通成功率',
      description: 'Ping 探测节点的平均连通成功率。',
      unit: 'percent',
      query: 'clamp_max(100 - avg(ping_percent_packet_loss{__$labels__}), 100)',
      color: '#27c274'
    },
    {
      name: 'ping_ttl_avg',
      display_name: '平均 TTL',
      description: 'Ping 探测节点的平均 TTL。',
      unit: 'counts',
      query: 'avg(ping_ttl{__$labels__})',
      color: '#597ef7'
    },
    {
      name: 'ping_result_code_max',
      display_name: '最差结果码',
      description: 'Ping 探测节点当前最差结果码。',
      unit: 'none',
      query: 'max(ping_result_code{__$labels__})',
      color: '#9aa9bf'
    }
  ],
  summaryCards: [
    {
      title: '连通成功率',
      metric: 'ping_success_rate_avg',
      color: '#27c274',
      icon: 'api',
      compare: true,
      compareFavorableDirection: 'up',
      guide: [],
      footer: [{ label: '平均丢包率', metric: 'ping_packet_loss_avg', unit: 'percent' }]
    },
    {
      title: '平均延迟',
      metric: 'ping_latency_avg',
      color: '#2f6bff',
      icon: 'clock',
      compare: true,
      guide: [],
      footer: [{ label: '最大延迟', metric: 'ping_latency_max', unit: 'ms' }]
    },
    {
      title: '最大延迟',
      metric: 'ping_latency_max',
      unit: 'ms',
      color: '#ff8a1f',
      icon: 'clock',
      compare: true,
      compareFavorableDirection: 'down',
      guide: [{ label: '最大延迟', detail: '探测节点的最大往返延迟，用于捕捉延迟尖刺。' }],
      footer: [{ label: '平均延迟', metric: 'ping_latency_avg', unit: 'ms' }]
    },
    {
      title: '平均丢包率',
      metric: 'ping_packet_loss_avg',
      color: '#ff4d4f',
      icon: 'api',
      compare: true,
      compareFavorableDirection: 'down',
      guide: [],
      footer: [{ label: '平均 TTL', metric: 'ping_ttl_avg', unit: 'counts' }],
    }
  ],
  charts: [
    {
      title: '延迟趋势',
      subtitle: '平均、最小与最大',
      metric: 'ping_latency_avg',
      guide: [{ label: '延迟趋势', detail: '观察 Ping 平均、最小和最大延迟变化。' }],
      series: [
        { metric: 'ping_latency_avg', label: '平均延迟', color: '#2f6bff', unit: 'ms' },
        { metric: 'ping_latency_min', label: '最小延迟', color: '#13c2c2', unit: 'ms' },
        { metric: 'ping_latency_max', label: '最大延迟', color: '#ff8a1f', unit: 'ms' }
      ]
    },
    {
      title: '丢包率趋势',
      subtitle: '丢包率变化',
      metric: 'ping_packet_loss_avg',
      guide: [{ label: '丢包趋势', detail: '观察 Ping 丢包率随时间变化。' }],
      series: [{ metric: 'ping_packet_loss_avg', label: '平均丢包率', color: '#ff4d4f', unit: 'percent' }]
    },
    {
      title: 'TTL 趋势',
      subtitle: 'TTL 变化',
      metric: 'ping_ttl_avg',
      guide: [{ label: 'TTL 趋势', detail: '观察 Ping 探测 TTL 的变化情况。' }],
      series: [{ metric: 'ping_ttl_avg', label: '平均 TTL', color: '#597ef7', unit: 'counts' }]
    }
  ],
  ringPanels: [
    {
      title: '连通质量分布',
      subtitle: '成功与丢包占比',
      centerMetric: 'ping_success_rate_avg',
      centerCaption: '连通成功率',
      centerUnit: 'percent',
      guide: [{ label: '连通质量', detail: '展示 Ping 成功率与丢包率的当前结构。' }],
      segments: [
        { label: '成功占比', metric: 'ping_success_rate_avg', color: '#27c274', unit: 'percent' },
        { label: '丢包占比', metric: 'ping_packet_loss_avg', color: '#ffccc7', unit: 'percent' }
      ]
    }
  ],
  barPanels: [],
  details: [
    {
      title: '网络探测详情',
      subtitle: 'TTL 与丢包',
      rows: [
        { label: '平均丢包率', metric: 'ping_packet_loss_avg', unit: 'percent', tone: 'warning' },
        { label: '平均 TTL', metric: 'ping_ttl_avg', unit: 'counts' }
      ]
    }
  ]
};
