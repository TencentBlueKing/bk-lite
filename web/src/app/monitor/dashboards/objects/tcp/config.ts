import type { SimpleDashboardConfig } from '../common/simple-dashboard-core';

/** TCP 拨测监控高对比鲜活色板 */
const TCP_PALETTE = {
  emerald: '#10B981',   // 连通成功率、成功占比
  blue: '#2563EB',      // 平均响应时间
  cyan: '#06B6D4',      // 最小响应时间
  indigo: '#6366F1',    // 最大响应时间
  amber: '#F59E0B',     // 返回不匹配
  orange: '#F97316',    // 读取失败
  rose: '#EF4444',      // 探测失败率、超时占比
  crimson: '#E11D48'    // 连接失败占比
} as const;

export const TCP_DASHBOARD_CONFIG: SimpleDashboardConfig = {
  routeKey: 'tcp',
  pageTitle: 'TCP 监控仪表盘',
  objectFallbackName: 'TCP',
  instanceType: 'tcp',
  collectionStatusQuery: "count({instance_type='tcp', collect_type='tcp', __$labels__}) by (instance_id)",
  metaItems: ['Telegraf', 'tcp'],
  metrics: [
    {
      name: 'tcp_response_time_avg',
      display_name: '平均响应时间',
      description: 'TCP 建连的平均往返耗时（毫秒）。',
      unit: 'ms',
      query: 'avg(net_response_response_time{__$labels__}) * 1000',
      color: TCP_PALETTE.blue
    },
    {
      name: 'tcp_response_time_min',
      display_name: '最小响应时间',
      description: 'TCP 建连的最小往返耗时（毫秒）。',
      unit: 'ms',
      query: 'min(net_response_response_time{__$labels__}) * 1000',
      color: TCP_PALETTE.cyan
    },
    {
      name: 'tcp_response_time_max',
      display_name: '最大响应时间',
      description: 'TCP 建连的最大往返耗时（毫秒）。',
      unit: 'ms',
      query: 'max(net_response_response_time{__$labels__}) * 1000',
      color: TCP_PALETTE.indigo
    },
    {
      name: 'tcp_success_rate',
      display_name: '连通成功率',
      description: '结果码为 0（成功）的探测占比。',
      unit: 'percent',
      query: 'avg(net_response_result_code{__$labels__} == bool 0) * 100',
      color: TCP_PALETTE.emerald
    },
    {
      name: 'tcp_failure_rate',
      display_name: '探测失败率',
      description: '结果码非 0 的探测占比。',
      unit: 'percent',
      query: 'avg(net_response_result_code{__$labels__} != bool 0) * 100',
      color: TCP_PALETTE.rose
    },
    {
      name: 'tcp_result_success_rate',
      display_name: '成功占比',
      description: '结果码为成功的探测占比。',
      unit: 'percent',
      query: 'avg(net_response_result_code{__$labels__} == bool 0) * 100',
      color: TCP_PALETTE.emerald
    },
    {
      name: 'tcp_result_timeout_rate',
      display_name: '超时占比',
      description: '结果码为超时的探测占比。',
      unit: 'percent',
      query: 'avg(net_response_result_code{__$labels__} == bool 1) * 100',
      color: TCP_PALETTE.rose
    },
    {
      name: 'tcp_result_conn_fail_rate',
      display_name: '连接失败占比',
      description: '结果码为连接失败的探测占比。',
      unit: 'percent',
      query: 'avg(net_response_result_code{__$labels__} == bool 2) * 100',
      color: TCP_PALETTE.crimson
    },
    {
      name: 'tcp_result_read_fail_rate',
      display_name: '读取失败占比',
      description: '结果码为读取失败的探测占比。',
      unit: 'percent',
      query: 'avg(net_response_result_code{__$labels__} == bool 3) * 100',
      color: TCP_PALETTE.orange
    },
    {
      name: 'tcp_result_mismatch_rate',
      display_name: '返回不匹配占比',
      description: '结果码为返回不匹配的探测占比。',
      unit: 'percent',
      query: 'avg(net_response_result_code{__$labels__} == bool 4) * 100',
      color: TCP_PALETTE.amber
    }
  ],
  // Layer0 + A 连通成功率 + B 平均响应；最大响应/结果码进副文案与环图，不另占主卡
  summaryCards: [
    {
      title: '连通成功率',
      metric: 'tcp_success_rate',
      unit: 'percent',
      color: TCP_PALETTE.emerald,
      icon: 'health',
      compare: true,
      compareFavorableDirection: 'up',
      guide: [
        {
          label: '连通成功率',
          detail: '结果码为 0 的探测占比，反映 TCP 端口整体可达性。失败形态看「结果码分布」。'
        }
      ],
      footer: [
        { label: '失败占比', metric: 'tcp_failure_rate', unit: 'percent' }
      ]
    },
    {
      title: '平均响应时间',
      metric: 'tcp_response_time_avg',
      unit: 'ms',
      color: TCP_PALETTE.blue,
      icon: 'clock',
      compare: true,
      compareFavorableDirection: 'down',
      guide: [
        {
          label: '平均响应时间',
          detail: 'TCP 建连平均耗时；峰值见副文案与趋势图，不再单独占主卡。'
        }
      ],
      footer: [
        { label: '最大响应时间', metric: 'tcp_response_time_max', unit: 'ms' },
        { label: '最小响应时间', metric: 'tcp_response_time_min', unit: 'ms' }
      ]
    }
  ],
  charts: [
    {
      title: '连通成功率趋势',
      subtitle: '端口可达性',
      metric: 'tcp_success_rate',
      guide: [{ label: '连通成功率趋势', detail: '下跌时优先查端口监听、防火墙与对端进程；对照结果码分布。' }],
      series: [{ metric: 'tcp_success_rate', label: '连通成功率', color: TCP_PALETTE.emerald, unit: 'percent' }]
    },
    {
      title: '响应时间趋势',
      subtitle: '平均与最大',
      metric: 'tcp_response_time_avg',
      guide: [{ label: '响应时间趋势', detail: '对比平均与最大建连耗时，判断整体变慢还是尖刺。' }],
      series: [
        { metric: 'tcp_response_time_avg', label: '平均响应时间', color: TCP_PALETTE.blue, unit: 'ms' },
        { metric: 'tcp_response_time_max', label: '最大响应时间', color: TCP_PALETTE.indigo, unit: 'ms' }
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
          detail: '按 Telegraf net_response result_code：成功、超时、连接失败、读取失败、返回不匹配。用于定位失败形态。'
        }
      ],
      centerMetric: 'tcp_success_rate',
      centerCaption: '连通成功率',
      centerUnit: 'percent',
      emptyWhenAllZero: true,
      emptyDescription: '当前窗口无 TCP 探测结果码样本',
      segments: [
        { label: '成功', metric: 'tcp_result_success_rate', color: TCP_PALETTE.emerald, unit: 'percent' },
        { label: '超时', metric: 'tcp_result_timeout_rate', color: TCP_PALETTE.rose, unit: 'percent' },
        { label: '连接失败', metric: 'tcp_result_conn_fail_rate', color: TCP_PALETTE.crimson, unit: 'percent' },
        { label: '读取失败', metric: 'tcp_result_read_fail_rate', color: TCP_PALETTE.orange, unit: 'percent' },
        { label: '返回不匹配', metric: 'tcp_result_mismatch_rate', color: TCP_PALETTE.amber, unit: 'percent' }
      ]
    }
  ],
  barPanels: [],
  details: []
};
