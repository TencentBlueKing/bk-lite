import type { SimpleDashboardConfig } from '../common/simple-dashboard-core';

export const WEBSITE_DASHBOARD_CONFIG: SimpleDashboardConfig = {
  routeKey: 'website',
  pageTitle: '网站监控仪表盘',
  objectFallbackName: '网站',
  instanceType: 'web',
  collectionStatusQuery: "count({instance_type='web', collect_type='web', __$labels__}) by (instance_id)",
  metaItems: ['Telegraf', 'web'],
  metrics: [
    {
      name: 'website_success_rate_avg',
      display_name: '探测成功率',
      description: '网站探测节点平均成功率。',
      unit: 'percent',
      query: 'avg(http_node_success_rate{__$labels__})',
      color: '#27c274'
    },
    {
      name: 'website_failure_rate_avg',
      display_name: '失败占比',
      description: '网站探测节点平均失败占比。',
      unit: 'percent',
      query: 'clamp_max(100 - avg(http_node_success_rate{__$labels__}), 100)',
      color: '#ff8a1f'
    },
    {
      name: 'website_response_time_avg',
      display_name: '平均响应时间',
      description: '网站探测平均响应时间。',
      unit: 's',
      query: 'avg(http_response_response_time{__$labels__})',
      color: '#2f6bff'
    },
    {
      name: 'website_response_time_min',
      display_name: '最小响应时间',
      description: '网站探测最小响应时间。',
      unit: 's',
      query: 'min(http_response_response_time{__$labels__})',
      color: '#13c2c2'
    },
    {
      name: 'website_response_time_max',
      display_name: '最大响应时间',
      description: '网站探测最大响应时间。',
      unit: 's',
      query: 'max(http_response_response_time{__$labels__})',
      color: '#ff8a1f'
    },
    {
      name: 'website_content_length_avg',
      display_name: '平均内容长度',
      description: '网站返回内容平均大小。',
      unit: 'bytes',
      query: 'avg(http_response_content_length{__$labels__})',
      color: '#597ef7'
    },
    {
      name: 'website_status_code_node_total',
      display_name: '状态码节点总数',
      description: '当前返回 HTTP 状态码的探测节点总数。',
      unit: 'counts',
      query: 'count(http_response_http_response_code{__$labels__})',
      color: '#2f6bff'
    },
    {
      name: 'website_status_code_2xx_count',
      display_name: '2xx 节点数',
      description: '当前返回 2xx 状态码的探测节点数。',
      unit: 'counts',
      query: 'count((http_response_http_response_code{__$labels__} >= 200) and (http_response_http_response_code{__$labels__} < 300))',
      color: '#27c274'
    },
    {
      name: 'website_status_code_3xx_count',
      display_name: '3xx 节点数',
      description: '当前返回 3xx 状态码的探测节点数。',
      unit: 'counts',
      query: 'count((http_response_http_response_code{__$labels__} >= 300) and (http_response_http_response_code{__$labels__} < 400))',
      color: '#2f6bff'
    },
    {
      name: 'website_status_code_4xx_count',
      display_name: '4xx 节点数',
      description: '当前返回 4xx 状态码的探测节点数。',
      unit: 'counts',
      query: 'count((http_response_http_response_code{__$labels__} >= 400) and (http_response_http_response_code{__$labels__} < 500))',
      color: '#ff8a1f'
    },
    {
      name: 'website_status_code_5xx_count',
      display_name: '5xx 节点数',
      description: '当前返回 5xx 状态码的探测节点数。',
      unit: 'counts',
      query: 'count(http_response_http_response_code{__$labels__} >= 500)',
      color: '#ff4d4f'
    },
  ],
  summaryCards: [
    {
      title: '探测成功率',
      metric: 'website_success_rate_avg',
      color: '#27c274',
      icon: 'api',
      compare: true,
      guide: [{ label: '探测成功率', detail: '统计网站探测节点的平均成功率。' }],
      footer: [{ label: '失败占比', metric: 'website_failure_rate_avg', unit: 'percent' }]
    },
    {
      title: '平均响应时间',
      metric: 'website_response_time_avg',
      color: '#2f6bff',
      icon: 'clock',
      compare: true,
      guide: [{ label: '响应时间', detail: '统计网站探测节点的平均响应时间。' }],
      footer: [{ label: '最大响应', metric: 'website_response_time_max', unit: 's' }]
    },
    {
      title: '平均内容长度',
      metric: 'website_content_length_avg',
      color: '#597ef7',
      icon: 'database',
      guide: [{ label: '内容长度', detail: '统计网站返回内容的平均体积。' }],
      footer: [{ label: '5xx 节点', metric: 'website_status_code_5xx_count', unit: 'counts' }]
    }
  ],
  charts: [
    {
      title: '探测成功率趋势',
      subtitle: '多节点成功率',
      metric: 'website_success_rate_avg',
      guide: [{ label: '成功率趋势', detail: '观察网站探测成功率的波动情况。' }],
      series: [{ metric: 'website_success_rate_avg', label: '探测成功率', color: '#27c274', unit: 'percent' }]
    },
    {
      title: '响应时间趋势',
      subtitle: '平均、最小与最大',
      metric: 'website_response_time_avg',
      guide: [{ label: '响应时间', detail: '对比网站平均、最小和最大响应时间。' }],
      series: [
        { metric: 'website_response_time_avg', label: '平均响应', color: '#2f6bff', unit: 's' },
        { metric: 'website_response_time_min', label: '最小响应', color: '#13c2c2', unit: 's' },
        { metric: 'website_response_time_max', label: '最大响应', color: '#ff8a1f', unit: 's' }
      ]
    },
    {
      title: '内容长度趋势',
      subtitle: '返回内容大小',
      metric: 'website_content_length_avg',
      guide: [{ label: '内容长度', detail: '观察网站返回内容长度变化，识别异常体积。' }],
      series: [{ metric: 'website_content_length_avg', label: '平均内容长度', color: '#597ef7', unit: 'bytes' }]
    }
  ],
  ringPanels: [
    {
      title: '可用性分布',
      subtitle: '成功与失败占比',
      centerMetric: 'website_success_rate_avg',
      centerCaption: '探测成功率',
      centerUnit: 'percent',
      guide: [{ label: '可用性分布', detail: '展示网站探测的成功与失败占比。' }],
      segments: [
        { label: '成功占比', metric: 'website_success_rate_avg', color: '#27c274', unit: 'percent' },
        { label: '失败占比', metric: 'website_failure_rate_avg', color: '#ffccc7', unit: 'percent' }
      ]
    },
    {
      title: '状态码分布',
      subtitle: '2xx~5xx分布',
      centerMetric: 'website_status_code_node_total',
      centerCaption: '探测节点',
      centerUnit: 'counts',
      guide: [{ label: '状态码分布', detail: '按探测节点当前返回的 HTTP 状态码类型统计 2xx、3xx、4xx、5xx 分布。' }],
      segments: [
        { label: '2xx', metric: 'website_status_code_2xx_count', color: '#27c274', unit: 'counts' },
        { label: '3xx', metric: 'website_status_code_3xx_count', color: '#2f6bff', unit: 'counts' },
        { label: '4xx', metric: 'website_status_code_4xx_count', color: '#ff8a1f', unit: 'counts' },
        { label: '5xx', metric: 'website_status_code_5xx_count', color: '#ff4d4f', unit: 'counts' }
      ]
    }
  ],
  details: []
};
