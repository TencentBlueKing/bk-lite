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
      name: 'website_status_code_2xx_count',
      display_name: '2xx 节点数',
      description: '当前返回 2xx 状态码的探测节点数。',
      unit: 'counts',
      query: 'count((http_response_http_response_code{__$labels__} >= 200) and (http_response_http_response_code{__$labels__} < 300)) or on() vector(0)',
      color: '#27c274'
    },
    {
      name: 'website_status_code_3xx_count',
      display_name: '3xx 节点数',
      description: '当前返回 3xx 状态码的探测节点数。',
      unit: 'counts',
      query: 'count((http_response_http_response_code{__$labels__} >= 300) and (http_response_http_response_code{__$labels__} < 400)) or on() vector(0)',
      color: '#2f6bff'
    },
    {
      name: 'website_status_code_4xx_count',
      display_name: '4xx 节点数',
      description: '当前返回 4xx 状态码的探测节点数。',
      unit: 'counts',
      query: 'count((http_response_http_response_code{__$labels__} >= 400) and (http_response_http_response_code{__$labels__} < 500)) or on() vector(0)',
      color: '#ff8a1f'
    },
    {
      name: 'website_status_code_5xx_count',
      display_name: '5xx 节点数',
      description: '当前返回 5xx 状态码的探测节点数。',
      unit: 'counts',
      query: 'count(http_response_http_response_code{__$labels__} >= 500) or on() vector(0)',
      color: '#ff4d4f'
    },
  ],
  summaryCards: [
    {
      title: '探测成功率',
      guide: [{ label: '探测成功率', detail: '优先确认当前可用性是否已下降，并结合失败占比判断影响面。' }],
      metric: 'website_success_rate_avg',
      color: '#27c274',
      icon: 'api',
      compare: true,
      compareFavorableDirection: 'up',
      footer: [{ label: '失败占比', metric: 'website_failure_rate_avg', unit: 'percent' }]
    },
    {
      title: '异常状态码',
      guide: [{ label: '异常状态码', detail: '当前返回 5xx 的探测节点数，非零表示服务端错误，需立即排查。' }],
      metric: 'website_status_code_5xx_count',
      unit: 'counts',
      color: '#ff4d4f',
      icon: 'api',
      compare: true,
      compareFavorableDirection: 'down',
      footer: [{ label: '4xx 节点', metric: 'website_status_code_4xx_count', unit: 'counts' }]
    },
    {
      title: '平均响应时间',
      guide: [{ label: '平均响应时间', detail: '优先观察平均响应是否持续升高，再对比峰值判断是否存在抖动。' }],
      metric: 'website_response_time_avg',
      color: '#2f6bff',
      icon: 'clock',
      compare: true,
      footer: [{ label: '峰值响应', metric: 'website_response_time_max', unit: 's' }]
    },
    {
      title: '可用节点(2xx)',
      guide: [{ label: '可用节点(2xx)', detail: '当前返回 2xx 状态码的探测节点数,反映正常服务的探测覆盖面。' }],
      metric: 'website_status_code_2xx_count',
      unit: 'counts',
      color: '#27c274',
      icon: 'api',
      compare: true,
      compareFavorableDirection: 'up',
      footer: [{ label: '3xx 节点', metric: 'website_status_code_3xx_count', unit: 'counts' }]
    },
    {
      title: '平均内容长度',
      guide: [{ label: '平均内容长度', detail: '网站返回内容平均字节数;骤增减常意味页面改版、错误页或被劫持,需核对页面内容。' }],
      metric: 'website_content_length_avg',
      unit: 'bytes',
      color: '#597ef7',
      icon: 'database',
      compare: true,
      footer: [{ label: '探测成功率', metric: 'website_success_rate_avg', unit: 'percent' }]
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
      subtitle: '平均与峰值',
      guide: [{ label: '响应时间趋势', detail: '对比平均值与峰值，优先识别整体变慢还是局部尖刺。' }],
      metric: 'website_response_time_avg',
      series: [
        { metric: 'website_response_time_avg', label: '平均响应', color: '#2f6bff', unit: 's' },
        { metric: 'website_response_time_max', label: '峰值响应', color: '#ff8a1f', unit: 's' }
      ]
    },
    {
      title: '内容长度趋势',
      subtitle: '返回内容大小',
      metric: 'website_content_length_avg',
      guide: [{ label: '内容长度', detail: '单次响应正文字节数(bytes);骤增减常意味页面改版、错误页或被劫持,需核对页面内容。' }],
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
  ],
  barPanels: [
    {
      title: '状态码分布',
      subtitle: '2xx~5xx节点',
      guide: [{ label: '状态码结构', detail: '优先判断当前异常请求主要集中在 4xx 还是 5xx。' }],
      items: [
        { label: '2xx', metric: 'website_status_code_2xx_count', color: '#27c274', unit: 'counts' },
        { label: '3xx', metric: 'website_status_code_3xx_count', color: '#2f6bff', unit: 'counts' },
        { label: '4xx', metric: 'website_status_code_4xx_count', color: '#ff8a1f', unit: 'counts' },
        { label: '5xx', metric: 'website_status_code_5xx_count', color: '#ff4d4f', unit: 'counts' }
      ]
    }
  ],
  details: []
};
