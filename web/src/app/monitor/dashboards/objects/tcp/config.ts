import type { SimpleDashboardConfig } from '../common/simple-dashboard-core';
import type { MetricEnumMap } from '../../shared/types';

const TCP_RESULT_CODE_ENUM: MetricEnumMap = {
  0: { label: '成功', color: '#27c274' },
  1: { label: '超时', color: '#ff4d4f' },
  2: { label: '连接失败', color: '#ff4d4f' },
  3: { label: '读取失败', color: '#ff4d4f' },
  4: { label: '返回不匹配', color: '#faad14' }
};

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
      color: '#2f6bff'
    },
    {
      name: 'tcp_response_time_min',
      display_name: '最小响应时间',
      description: 'TCP 建连的最小往返耗时（毫秒）。',
      unit: 'ms',
      query: 'min(net_response_response_time{__$labels__}) * 1000',
      color: '#13c2c2'
    },
    {
      name: 'tcp_response_time_max',
      display_name: '最大响应时间',
      description: 'TCP 建连的最大往返耗时（毫秒）。',
      unit: 'ms',
      query: 'max(net_response_response_time{__$labels__}) * 1000',
      color: '#ff8a1f'
    },
    {
      name: 'tcp_success_rate',
      display_name: '连通成功率',
      description: '结果码为 0（成功）的探测占比。',
      unit: 'percent',
      query: 'avg(net_response_result_code{__$labels__} == bool 0) * 100',
      color: '#27c274'
    },
    {
      name: 'tcp_failure_rate',
      display_name: '探测失败率',
      description: '结果码非 0（超时/连接失败/读取失败/返回不匹配）的探测占比。',
      unit: 'percent',
      query: 'avg(net_response_result_code{__$labels__} != bool 0) * 100',
      color: '#ff4d4f'
    },
    {
      name: 'tcp_result_code_max',
      display_name: '最差结果码',
      description: '当前最差的 TCP 探测结果码。',
      unit: 'none',
      query: 'max(net_response_result_code{__$labels__})',
      color: '#9aa9bf'
    },
    {
      name: 'tcp_string_found_rate',
      display_name: '返回匹配率',
      description: '配置了期望返回串时，命中期望串的探测占比。',
      unit: 'percent',
      query: 'avg(net_response_string_found{__$labels__}) * 100',
      color: '#597ef7'
    }
  ],
  summaryCards: [
    {
      title: '连通成功率',
      metric: 'tcp_success_rate',
      unit: 'percent',
      color: '#27c274',
      icon: 'health',
      compare: true,
      compareFavorableDirection: 'up',
      guide: [{ label: '连通成功率', detail: '结果码为 0 的探测占比，反映 TCP 端口整体可达性。' }],
      footer: [{ label: '最差结果码', metric: 'tcp_result_code_max', formatter: 'enumHealth', enumMap: TCP_RESULT_CODE_ENUM }]
    },
    {
      title: '平均响应时间',
      metric: 'tcp_response_time_avg',
      unit: 'ms',
      color: '#2f6bff',
      icon: 'clock',
      compare: true,
      compareFavorableDirection: 'down',
      guide: [],
      footer: [{ label: '最大响应时间', metric: 'tcp_response_time_max', unit: 'ms' }]
    },
    {
      title: '最大响应时间',
      metric: 'tcp_response_time_max',
      unit: 'ms',
      color: '#ff8a1f',
      icon: 'clock',
      compare: true,
      compareFavorableDirection: 'down',
      guide: [{ label: '最大响应时间', detail: '探测节点的最大建连耗时，用于捕捉延迟尖刺。' }],
      footer: [{ label: '平均响应时间', metric: 'tcp_response_time_avg', unit: 'ms' }]
    },
    {
      title: '探测失败率',
      metric: 'tcp_failure_rate',
      unit: 'percent',
      color: '#ff4d4f',
      icon: 'api',
      compare: true,
      compareFavorableDirection: 'down',
      guide: [{ label: '探测失败率', detail: '结果码非 0 的探测占比，升高表示端口不可达或响应异常。' }],
      footer: [{ label: '返回匹配率', metric: 'tcp_string_found_rate', unit: 'percent' }]
    },
    {
      title: '返回匹配率',
      metric: 'tcp_string_found_rate',
      unit: 'percent',
      color: '#597ef7',
      icon: 'api',
      compare: true,
      compareFavorableDirection: 'up',
      guide: [{ label: '返回匹配率', detail: '仅在配置了期望返回串时统计，命中期望串的探测占比。' }],
      footer: [{ label: '最小响应时间', metric: 'tcp_response_time_min', unit: 'ms' }]
    }
  ],
  charts: [
    {
      title: '响应时间趋势',
      subtitle: '平均、最小与最大',
      metric: 'tcp_response_time_avg',
      guide: [{ label: '响应时间趋势', detail: '观察 TCP 建连耗时的平均、最小和最大变化。' }],
      series: [
        { metric: 'tcp_response_time_avg', label: '平均响应时间', color: '#2f6bff', unit: 'ms' },
        { metric: 'tcp_response_time_min', label: '最小响应时间', color: '#13c2c2', unit: 'ms' },
        { metric: 'tcp_response_time_max', label: '最大响应时间', color: '#ff8a1f', unit: 'ms' }
      ]
    },
    {
      title: '连通成功率趋势',
      subtitle: '成功率变化',
      metric: 'tcp_success_rate',
      guide: [{ label: '连通成功率趋势', detail: '观察 TCP 探测连通成功率随时间变化。' }],
      series: [{ metric: 'tcp_success_rate', label: '连通成功率', color: '#27c274', unit: 'percent' }]
    }
  ],
  ringPanels: [
    {
      title: '探测结果分布',
      subtitle: '成功与失败占比',
      centerMetric: 'tcp_success_rate',
      centerCaption: '连通成功率',
      centerUnit: 'percent',
      guide: [{ label: '探测结果分布', detail: '展示 TCP 探测成功与失败的当前结构。' }],
      segments: [
        { label: '成功占比', metric: 'tcp_success_rate', color: '#27c274', unit: 'percent' },
        { label: '失败占比', metric: 'tcp_failure_rate', color: '#ffccc7', unit: 'percent' }
      ]
    }
  ],
  barPanels: [],
  details: []
};
