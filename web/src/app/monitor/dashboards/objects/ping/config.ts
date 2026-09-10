import type { SimpleDashboardConfig } from '../common/simple-dashboard-core';

/** Ping 拨测监控高对比鲜活色板 */
const PING_PALETTE = {
  rose: '#EF4444',      // 平均丢包率、错误占比
  blue: '#2563EB',      // 平均延迟
  cyan: '#06B6D4',      // 最小延迟
  indigo: '#6366F1',    // 最大延迟
  emerald: '#10B981',   // 连通成功率、成功占比
  crimson: '#E11D48'    // 无法解析占比
} as const;

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
      color: PING_PALETTE.blue
    },
    {
      name: 'ping_latency_min',
      display_name: '最小延迟',
      description: 'Ping 探测节点的最小延迟。',
      unit: 'ms',
      query: 'min(ping_minimum_response_ms{__$labels__})',
      color: PING_PALETTE.cyan
    },
    {
      name: 'ping_latency_max',
      display_name: '最大延迟',
      description: 'Ping 探测节点的最大延迟。',
      unit: 'ms',
      query: 'max(ping_maximum_response_ms{__$labels__})',
      color: PING_PALETTE.indigo
    },
    {
      name: 'ping_packet_loss_avg',
      display_name: '平均丢包率',
      description: 'Ping 探测节点的平均丢包率。',
      unit: 'percent',
      query: 'avg(ping_percent_packet_loss{__$labels__})',
      color: PING_PALETTE.rose
    },
    {
      name: 'ping_success_rate_avg',
      display_name: '连通成功率',
      description: '由丢包率换算的连通成功率（100−丢包率）。',
      unit: 'percent',
      query: 'clamp_max(100 - avg(ping_percent_packet_loss{__$labels__}), 100)',
      color: PING_PALETTE.emerald
    },
    {
      name: 'ping_result_success_rate',
      display_name: '成功占比',
      description: 'result_code=0 的探测占比。',
      unit: 'percent',
      query: 'avg(ping_result_code{__$labels__} == bool 0) * 100',
      color: PING_PALETTE.emerald
    },
    {
      name: 'ping_result_error_rate',
      display_name: '错误占比',
      description: 'result_code=1 的探测占比。',
      unit: 'percent',
      query: 'avg(ping_result_code{__$labels__} == bool 1) * 100',
      color: PING_PALETTE.rose
    },
    {
      name: 'ping_result_resolve_fail_rate',
      display_name: '无法解析占比',
      description: 'result_code=2 的探测占比。',
      unit: 'percent',
      query: 'avg(ping_result_code{__$labels__} == bool 2) * 100',
      color: PING_PALETTE.crimson
    }
  ],
  // Layer0 + A 丢包（原生）+ B 延迟；C 结果码进分布环
  summaryCards: [
    {
      title: '平均丢包率',
      metric: 'ping_packet_loss_avg',
      color: PING_PALETTE.rose,
      icon: 'api',
      compare: true,
      compareFavorableDirection: 'down',
      guide: [
        {
          label: '平均丢包率',
          detail: 'ICMP 丢包百分比，Ping 可用性的原生指标。非零表示链路不稳；持续升高优先查拥塞、错包与对端可达性。'
        },
        {
          label: '连通成功率',
          detail: '由 100−丢包率换算，与丢包互为镜像，故不单独占主卡。'
        }
      ],
      footer: [
        { label: '连通成功率', metric: 'ping_success_rate_avg', unit: 'percent' }
      ]
    },
    {
      title: '平均延迟',
      metric: 'ping_latency_avg',
      color: PING_PALETTE.blue,
      icon: 'clock',
      compare: true,
      guide: [{ label: '平均延迟', detail: '往返时延均值；持续升高结合最大延迟判断是整体变慢还是尖刺抖动。' }],
      footer: [
        { label: '最大延迟', metric: 'ping_latency_max', unit: 'ms' },
        { label: '最小延迟', metric: 'ping_latency_min', unit: 'ms' }
      ]
    }
  ],
  charts: [
    {
      title: '丢包率趋势',
      subtitle: '链路稳定性',
      metric: 'ping_packet_loss_avg',
      guide: [{ label: '丢包趋势', detail: '丢包升高时对照延迟与结果码分布；持续高位优先查链路与目标可达性。' }],
      series: [{ metric: 'ping_packet_loss_avg', label: '平均丢包率', color: PING_PALETTE.rose, unit: 'percent' }]
    },
    {
      title: '延迟趋势',
      subtitle: '平均与最大',
      metric: 'ping_latency_avg',
      guide: [{ label: '延迟趋势', detail: '对比平均与最大延迟，判断整体变慢还是尖刺抖动。' }],
      series: [
        { metric: 'ping_latency_avg', label: '平均延迟', color: PING_PALETTE.blue, unit: 'ms' },
        { metric: 'ping_latency_max', label: '最大延迟', color: PING_PALETTE.indigo, unit: 'ms' }
      ]
    }
  ],
  ringPanels: [
    {
      title: '结果码分布',
      subtitle: '失败形态归因',
      guide: [
        {
          label: '结果码分布',
          detail: '按 Telegraf ping result_code：成功、错误、无法解析。丢包升高时用于区分对端不可达与域名解析失败。'
        }
      ],
      centerMetric: 'ping_result_success_rate',
      centerCaption: '成功占比',
      centerUnit: 'percent',
      emptyWhenAllZero: true,
      emptyDescription: '当前窗口无 Ping 探测结果码样本',
      segments: [
        { label: '成功', metric: 'ping_result_success_rate', color: PING_PALETTE.emerald, unit: 'percent' },
        { label: '错误', metric: 'ping_result_error_rate', color: PING_PALETTE.rose, unit: 'percent' },
        { label: '无法解析', metric: 'ping_result_resolve_fail_rate', color: PING_PALETTE.crimson, unit: 'percent' }
      ]
    }
  ],
  barPanels: [],
  details: []
};
