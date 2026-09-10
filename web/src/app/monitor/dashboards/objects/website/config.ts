import type { SimpleDashboardConfig } from '../common/simple-dashboard-core';

// http_node_success_rate 不是 telegraf 上报的原始指标,而是 metrics.json 里按表达式实时计算的
// (与「全量指标」视图一致)。仪表盘必须用同款表达式,不能直接查裸指标名 http_node_success_rate
// ——后者只有预置种子数据(website_01/02/03)才有存储序列,真实下发实例查不到 → 三卡片无数据。
const SUCCESS_RATE_EXPR =
  'avg by (instance_id) ((sum without (result) (count_over_time(http_response_result_type{result="success",__$labels__}[__$window__])) or sum without (result) (count_over_time(http_response_result_type{__$labels__}[__$window__])) * 0) / sum without (result) (count_over_time(http_response_result_type{__$labels__}[__$window__])) * 100)';

/** 网站拨测监控高对比鲜活色板 */
const WEBSITE_PALETTE = {
  emerald: '#10B981',   // 成功/健康 (探测成功率、2xx 节点)
  blue: '#2563EB',      // 响应时间主色 (平均响应时间)
  cyan: '#06B6D4',      // 3xx 节点
  indigo: '#6366F1',    // 峰值响应时间
  amber: '#F59E0B',     // 警告/不匹配 (4xx 节点、内容/状态码不匹配)
  orange: '#F97316',    // 读体失败、失败占比
  rose: '#EF4444',      // 严重失败 (5xx 节点、连接失败)
  crimson: '#E11D48',   // 超时
  ruby: '#991B1B'       // DNS 错误
} as const;

export const WEBSITE_DASHBOARD_CONFIG: SimpleDashboardConfig = {
  routeKey: 'website',
  pageTitle: '网站监控仪表盘',
  objectFallbackName: '网站',
  instanceType: 'web',
  // Layer 0：任意 result_type 样本即表示采集在跑；不要求 success，避免失败时误报「无采集」。
  collectionStatusQuery: "count(http_response_result_type{instance_type='web', collect_type='web', __$labels__}) by (instance_id)",
  metaItems: ['Telegraf', 'web'],
  metrics: [
    {
      name: 'website_success_rate_avg',
      display_name: '探测成功率',
      description: '网站探测节点平均成功率（Telegraf result_type=success，不等于 HTTP 2xx）。',
      unit: 'percent',
      query: SUCCESS_RATE_EXPR,
      color: WEBSITE_PALETTE.emerald
    },
    {
      name: 'website_failure_rate_avg',
      display_name: '失败占比',
      description: '网站探测节点平均失败占比。',
      unit: 'percent',
      query: `clamp_max(100 - ${SUCCESS_RATE_EXPR}, 100)`,
      color: WEBSITE_PALETTE.orange
    },
    {
      name: 'website_response_time_avg',
      display_name: '平均响应时间',
      description: '网站探测平均响应时间。',
      unit: 's',
      query: 'avg by (instance_id) (http_response_response_time{__$labels__})',
      color: WEBSITE_PALETTE.blue
    },
    {
      name: 'website_response_time_max',
      display_name: '最大响应时间',
      description: '网站探测最大响应时间。',
      unit: 's',
      query: 'max by (instance_id) (http_response_response_time{__$labels__})',
      color: WEBSITE_PALETTE.indigo
    },
    {
      name: 'website_result_success_rate',
      display_name: '成功占比',
      description: 'result_code=0 的探测占比。',
      unit: 'percent',
      query: 'avg(http_response_result_code{__$labels__} == bool 0) * 100',
      color: WEBSITE_PALETTE.emerald
    },
    {
      name: 'website_result_body_mismatch_rate',
      display_name: '响应内容不匹配占比',
      description: 'result_code=1 的探测占比。',
      unit: 'percent',
      query: 'avg(http_response_result_code{__$labels__} == bool 1) * 100',
      color: WEBSITE_PALETTE.amber
    },
    {
      name: 'website_result_body_read_fail_rate',
      display_name: '响应体读取失败占比',
      description: 'result_code=2 的探测占比。',
      unit: 'percent',
      query: 'avg(http_response_result_code{__$labels__} == bool 2) * 100',
      color: WEBSITE_PALETTE.orange
    },
    {
      name: 'website_result_conn_fail_rate',
      display_name: '连接失败占比',
      description: 'result_code=3 的探测占比。',
      unit: 'percent',
      query: 'avg(http_response_result_code{__$labels__} == bool 3) * 100',
      color: WEBSITE_PALETTE.rose
    },
    {
      name: 'website_result_timeout_rate',
      display_name: '超时占比',
      description: 'result_code=4 的探测占比。',
      unit: 'percent',
      query: 'avg(http_response_result_code{__$labels__} == bool 4) * 100',
      color: WEBSITE_PALETTE.crimson
    },
    {
      name: 'website_result_dns_fail_rate',
      display_name: 'DNS错误占比',
      description: 'result_code=5 的探测占比。',
      unit: 'percent',
      query: 'avg(http_response_result_code{__$labels__} == bool 5) * 100',
      color: WEBSITE_PALETTE.ruby
    },
    {
      name: 'website_result_status_mismatch_rate',
      display_name: '响应状态码不匹配占比',
      description: 'result_code=6 的探测占比。',
      unit: 'percent',
      query: 'avg(http_response_result_code{__$labels__} == bool 6) * 100',
      color: WEBSITE_PALETTE.amber
    },
    {
      name: 'website_status_code_2xx_count',
      display_name: '2xx 节点数',
      description: '当前返回 2xx 状态码的探测节点数。',
      unit: 'counts',
      query: 'count((http_response_http_response_code{__$labels__} >= 200) and (http_response_http_response_code{__$labels__} < 300)) or on() vector(0)',
      color: WEBSITE_PALETTE.emerald
    },
    {
      name: 'website_status_code_3xx_count',
      display_name: '3xx 节点数',
      description: '当前返回 3xx 状态码的探测节点数。',
      unit: 'counts',
      query: 'count((http_response_http_response_code{__$labels__} >= 300) and (http_response_http_response_code{__$labels__} < 400)) or on() vector(0)',
      color: WEBSITE_PALETTE.cyan
    },
    {
      name: 'website_status_code_4xx_count',
      display_name: '4xx 节点数',
      description: '当前返回 4xx 状态码的探测节点数。',
      unit: 'counts',
      query: 'count((http_response_http_response_code{__$labels__} >= 400) and (http_response_http_response_code{__$labels__} < 500)) or on() vector(0)',
      color: WEBSITE_PALETTE.amber
    },
    {
      name: 'website_status_code_5xx_count',
      display_name: '5xx 节点数',
      description: '当前返回 5xx 状态码的探测节点数。',
      unit: 'counts',
      query: 'count(http_response_http_response_code{__$labels__} >= 500) or on() vector(0)',
      color: WEBSITE_PALETTE.rose
    }
  ],
  // Layer0 + A 成功率 + B 响应时间；失败归因交给下方「探测结果分布 / 状态码分布」
  summaryCards: [
    {
      title: '探测成功率',
      guide: [
        {
          label: '探测成功率',
          detail: '基于 Telegraf http_response 的 result_type=success。成功 ≠ HTTP 2xx；未配置期望状态码时非 2xx 仍可能计为成功。'
        },
        {
          label: '失败占比',
          detail: '与成功率互补。下跌时先看「探测结果分布」区分建连/超时/DNS 与内容/状态码校验失败。'
        }
      ],
      metric: 'website_success_rate_avg',
      color: WEBSITE_PALETTE.emerald,
      icon: 'api',
      compare: true,
      compareFavorableDirection: 'up',
      footer: [{ label: '失败占比', metric: 'website_failure_rate_avg', unit: 'percent' }]
    },
    {
      title: '平均响应时间',
      guide: [{ label: '平均响应时间', detail: '优先观察平均响应是否持续升高，再对比峰值判断是整体变慢还是尖刺。' }],
      metric: 'website_response_time_avg',
      color: WEBSITE_PALETTE.blue,
      icon: 'clock',
      compare: true,
      footer: [{ label: '峰值响应', metric: 'website_response_time_max', unit: 's' }]
    }
  ],
  charts: [
    {
      title: '探测成功率趋势',
      subtitle: '可用性变化',
      metric: 'website_success_rate_avg',
      guide: [
        {
          label: '成功率趋势',
          detail: '下跌时先看探测结果分布与响应时间；连接失败/超时/DNS 不会产生 HTTP 状态码。'
        }
      ],
      series: [{ metric: 'website_success_rate_avg', label: '探测成功率', color: WEBSITE_PALETTE.emerald, unit: 'percent' }]
    },
    {
      title: '响应时间趋势',
      subtitle: '平均与峰值',
      guide: [{ label: '响应时间趋势', detail: '对比平均值与峰值，优先识别整体变慢还是局部尖刺。' }],
      metric: 'website_response_time_avg',
      series: [
        { metric: 'website_response_time_avg', label: '平均响应', color: WEBSITE_PALETTE.blue, unit: 's' },
        { metric: 'website_response_time_max', label: '峰值响应', color: WEBSITE_PALETTE.indigo, unit: 's' }
      ]
    }
  ],
  ringPanels: [
    {
      title: '探测结果分布',
      subtitle: '按 result_code 失败归因',
      guide: [
        {
          label: '探测结果分布',
          detail: 'Telegraf http_response result_code 占比：成功、内容不匹配、读体失败、连接失败、超时、DNS错误、状态码不匹配。'
        }
      ],
      centerMetric: 'website_result_success_rate',
      centerCaption: '成功占比',
      centerUnit: 'percent',
      emptyWhenAllZero: true,
      emptyDescription: '当前窗口无探测结果码样本',
      segments: [
        { label: '成功', metric: 'website_result_success_rate', color: WEBSITE_PALETTE.emerald, unit: 'percent' },
        { label: '内容不匹配', metric: 'website_result_body_mismatch_rate', color: WEBSITE_PALETTE.amber, unit: 'percent' },
        { label: '读体失败', metric: 'website_result_body_read_fail_rate', color: WEBSITE_PALETTE.orange, unit: 'percent' },
        { label: '连接失败', metric: 'website_result_conn_fail_rate', color: WEBSITE_PALETTE.rose, unit: 'percent' },
        { label: '超时', metric: 'website_result_timeout_rate', color: WEBSITE_PALETTE.crimson, unit: 'percent' },
        { label: 'DNS错误', metric: 'website_result_dns_fail_rate', color: WEBSITE_PALETTE.ruby, unit: 'percent' },
        { label: '状态码不匹配', metric: 'website_result_status_mismatch_rate', color: WEBSITE_PALETTE.amber, unit: 'percent' }
      ]
    },
    {
      title: '状态码分布',
      subtitle: '有 HTTP 响应时的码段结构',
      guide: [
        {
          label: '状态码结构',
          detail: '仅在拿到 HTTP 状态码时有意义。优先看 4xx vs 5xx；全空表示失败发生在建连/TLS/超时阶段，或尚未采集到状态码。'
        }
      ],
      centerMetric: 'website_status_code_2xx_count',
      centerCaption: '2xx 节点',
      centerUnit: 'counts',
      emptyWhenAllZero: true,
      emptyDescription: '当前窗口无 HTTP 状态码（失败可能发生在建连/TLS/超时阶段，或尚未采集到状态码）',
      segments: [
        { label: '2xx', metric: 'website_status_code_2xx_count', color: WEBSITE_PALETTE.emerald, unit: 'counts' },
        { label: '3xx', metric: 'website_status_code_3xx_count', color: WEBSITE_PALETTE.cyan, unit: 'counts' },
        { label: '4xx', metric: 'website_status_code_4xx_count', color: WEBSITE_PALETTE.amber, unit: 'counts' },
        { label: '5xx', metric: 'website_status_code_5xx_count', color: WEBSITE_PALETTE.rose, unit: 'counts' }
      ]
    }
  ],
  barPanels: [],
  details: []
};
