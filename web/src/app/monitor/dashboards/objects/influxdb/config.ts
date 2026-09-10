import type { SimpleDashboardConfig } from '../common/simple-dashboard-core';

/** InfluxDB 监控高对比鲜活科技色板 */
const INFLUX_PALETTE = {
  emerald: '#10B981',   // 写请求速率
  blue: '#2563EB',      // Series 数
  cyan: '#06B6D4',      // 查询请求速率
  indigo: '#6366F1',    // 堆内存、认证失败
  amber: '#F59E0B',     // HTTP 4XX 速率
  orange: '#F97316',    // 写点丢弃速率
  rose: '#EF4444'       // 写入持久化失败、HTTP 5XX
} as const;

/**
 * InfluxDB v1 专业盘：叙事中心是高基数 (series) + 写入持久化完整性，
 * 不是通用 RDBMS 会话/表空间模型。仅 9 个指标，刻意做瘦盘。
 */
export const INFLUXDB_DASHBOARD_CONFIG: SimpleDashboardConfig = {
  routeKey: 'influxdb',
  pageTitle: 'InfluxDB 监控仪表盘',
  objectFallbackName: 'InfluxDB',
  instanceType: 'influxdb',
  collectionStatusQuery:
    "count({instance_type='influxdb', collect_type='database', __$labels__}) by (instance_id)",
  metaItems: ['Telegraf', 'database', 'Cardinality'],
  metrics: [
    {
      name: 'influxdb_num_series',
      display_name: 'Series 数',
      description: '所有数据库序列总数，是 InfluxDB 高基数风险的核心指标。',
      unit: 'counts',
      query: 'sum by (instance_id) (influxdb_database_numSeries{__$labels__})',
      color: INFLUX_PALETTE.blue
    },
    {
      name: 'influxdb_write_req_rate',
      display_name: '写请求速率',
      description: 'HTTP 写入请求速率。',
      unit: 'cps',
      query: 'sum by (instance_id) (rate(influxdb_httpd_writeReq{__$labels__}[__$window__]))',
      color: INFLUX_PALETTE.emerald
    },
    {
      name: 'influxdb_query_req_rate',
      display_name: '查询请求速率',
      description: 'HTTP 查询请求速率。',
      unit: 'cps',
      query: 'sum by (instance_id) (rate(influxdb_httpd_queryReq{__$labels__}[__$window__]))',
      color: INFLUX_PALETTE.cyan
    },
    {
      name: 'influxdb_points_fail_rate',
      display_name: '写入持久化失败速率',
      description: '已接收但持久化失败的数据点速率，直接关联数据丢失风险。',
      unit: 'cps',
      query: 'sum by (instance_id) (rate(influxdb_httpd_pointsWrittenFail{__$labels__}[__$window__]))',
      color: INFLUX_PALETTE.rose
    },
    {
      name: 'influxdb_points_dropped_rate',
      display_name: '写点丢弃速率',
      description: '已接收但在持久化前被丢弃的数据点速率。',
      unit: 'cps',
      query: 'sum by (instance_id) (rate(influxdb_httpd_pointsWrittenDropped{__$labels__}[__$window__]))',
      color: INFLUX_PALETTE.orange
    },
    {
      name: 'influxdb_server_error_rate',
      display_name: 'HTTP 5XX 速率',
      description: 'HTTP 5XX 错误速率。',
      unit: 'cps',
      query: 'sum by (instance_id) (rate(influxdb_httpd_serverError{__$labels__}[__$window__]))',
      color: INFLUX_PALETTE.rose
    },
    {
      name: 'influxdb_client_error_rate',
      display_name: 'HTTP 4XX 速率',
      description: 'HTTP 4XX 错误速率。',
      unit: 'cps',
      query: 'sum by (instance_id) (rate(influxdb_httpd_clientError{__$labels__}[__$window__]))',
      color: INFLUX_PALETTE.amber
    },
    {
      name: 'influxdb_auth_fail_rate',
      display_name: '认证失败速率',
      description: 'HTTP 认证失败速率。',
      unit: 'cps',
      query: 'sum by (instance_id) (rate(influxdb_httpd_authFail{__$labels__}[__$window__]))',
      color: INFLUX_PALETTE.indigo
    },
    {
      name: 'influxdb_heap_alloc',
      display_name: '运行时堆内存',
      description: 'Go 运行时堆上已分配且正在使用的内存。',
      unit: 'bytes',
      query: 'max by (instance_id) (influxdb_runtime_HeapAlloc{__$labels__})',
      color: INFLUX_PALETTE.indigo
    }
  ],
  summaryCards: [
    {
      title: 'Series 数',
      metric: 'influxdb_num_series',
      unit: 'counts',
      color: INFLUX_PALETTE.blue,
      icon: 'database',
      compare: true,
      compareFavorableDirection: 'down',
      guide: [
        {
          label: 'Series 基数',
          detail: '所有库序列总数。持续膨胀是 InfluxDB v1 最常见的容量/性能风险，需控制 tag 基数。'
        }
      ]
    },
    {
      title: '写请求速率',
      metric: 'influxdb_write_req_rate',
      unit: 'cps',
      color: INFLUX_PALETTE.emerald,
      icon: 'publish',
      compare: true,
      guide: [
        {
          label: '写入负载',
          detail: 'HTTP 写入请求速率。需与下方「失败/丢弃」成对看，有请求不等于写成功。'
        }
      ],
      footer: [{ label: '查询速率', metric: 'influxdb_query_req_rate', unit: 'cps' }]
    },
    {
      title: '持久化失败',
      metric: 'influxdb_points_fail_rate',
      unit: 'cps',
      color: INFLUX_PALETTE.rose,
      icon: 'thunder',
      compare: true,
      compareFavorableDirection: 'down',
      guide: [
        {
          label: '写入失败',
          detail: '已接收但持久化失败的点速率，非零即存在数据丢失风险。'
        }
      ],
      footer: [
        { label: '丢弃', metric: 'influxdb_points_dropped_rate', unit: 'cps' },
        { label: '堆内存', metric: 'influxdb_heap_alloc', unit: 'bytes' }
      ]
    }
  ],
  charts: [
    {
      title: '读写请求',
      subtitle: '写入 vs 查询',
      metric: 'influxdb_write_req_rate',
      guide: [
        { label: '写入', detail: 'HTTP 写入请求速率。' },
        { label: '查询', detail: 'HTTP 查询请求速率。' }
      ],
      series: [
        { metric: 'influxdb_write_req_rate', label: '写入', color: INFLUX_PALETTE.emerald, unit: 'cps' },
        { metric: 'influxdb_query_req_rate', label: '查询', color: INFLUX_PALETTE.cyan, unit: 'cps' }
      ]
    },
    {
      title: '写入完整性',
      subtitle: '持久化失败 vs 丢弃',
      metric: 'influxdb_points_fail_rate',
      guide: [
        {
          label: '写入路径',
          detail: '失败=已接收但落盘失败；丢弃=持久化前被丢。两者抬升都意味着 ingest 不完整。'
        }
      ],
      series: [
        { metric: 'influxdb_points_fail_rate', label: '持久化失败', color: INFLUX_PALETTE.rose, unit: 'cps' },
        { metric: 'influxdb_points_dropped_rate', label: '丢弃', color: INFLUX_PALETTE.orange, unit: 'cps' }
      ]
    },
    {
      title: 'HTTP 错误',
      subtitle: '5XX / 4XX / 认证失败',
      metric: 'influxdb_server_error_rate',
      guide: [
        { label: '5XX', detail: '服务端错误。' },
        { label: '4XX', detail: '客户端/协议错误。' },
        { label: '认证失败', detail: '鉴权失败，可能是配置错误或扫描噪声。' }
      ],
      series: [
        { metric: 'influxdb_server_error_rate', label: '5XX', color: INFLUX_PALETTE.rose, unit: 'cps' },
        { metric: 'influxdb_client_error_rate', label: '4XX', color: INFLUX_PALETTE.amber, unit: 'cps' },
        { metric: 'influxdb_auth_fail_rate', label: '认证失败', color: INFLUX_PALETTE.indigo, unit: 'cps' }
      ]
    },
    {
      title: '堆内存趋势',
      subtitle: 'HeapAlloc',
      metric: 'influxdb_heap_alloc',
      guide: [{ label: '堆内存', detail: 'Go 运行时堆分配大小随时间变化。' }],
      series: [
        { metric: 'influxdb_heap_alloc', label: 'HeapAlloc', color: INFLUX_PALETTE.indigo, unit: 'bytes' }
      ]
    }
  ],
  statusPanels: [],
  ringPanels: [],
  barPanels: [],
  details: []
};
