import type { SimpleDashboardConfig } from '../common/simple-dashboard-core';

export const NGINX_DASHBOARD_CONFIG: SimpleDashboardConfig = {
  routeKey: 'nginx',
  pageTitle: 'Nginx 监控仪表盘',
  objectFallbackName: 'Nginx',
  instanceType: 'nginx',
  collectionStatusQuery: "count({instance_type='nginx', collect_type='middleware', __$labels__}) by (instance_id)",
  metaItems: ['Telegraf', 'middleware'],
  metrics: [
    {
      name: 'nginx_active',
      display_name: '活跃连接数',
      description: '当前活跃的客户端连接数。',
      unit: 'counts',
      query: 'nginx_active{__$labels__}',
      color: '#2f6bff'
    },
    {
      name: 'nginx_reading',
      display_name: '读取连接数',
      description: '正在读取请求头的连接数。',
      unit: 'counts',
      query: 'nginx_reading{__$labels__}',
      color: '#27c274'
    },
    {
      name: 'nginx_writing',
      display_name: '写入连接数',
      description: '正在写入响应的连接数。',
      unit: 'counts',
      query: 'nginx_writing{__$labels__}',
      color: '#ff8a1f'
    },
    {
      name: 'nginx_waiting',
      display_name: '等待连接数',
      description: '空闲等待请求的连接数。',
      unit: 'counts',
      query: 'nginx_waiting{__$labels__}',
      color: '#9aa9bf'
    },
    {
      name: 'nginx_requests_rate',
      display_name: '请求速率',
      description: 'Nginx 处理请求的速率。',
      unit: 'cps',
      query: 'rate(nginx_requests{__$labels__}[5m])',
      color: '#27c274'
    },
    {
      name: 'nginx_accepts_rate',
      display_name: '连接接受速率',
      description: 'Nginx 接受新连接的速率。',
      unit: 'cps',
      query: 'rate(nginx_accepts{__$labels__}[5m])',
      color: '#13c2c2'
    },
    {
      name: 'nginx_handled_rate',
      display_name: '连接处理速率',
      description: 'Nginx 处理连接的速率。',
      unit: 'cps',
      query: 'rate(nginx_handled{__$labels__}[5m])',
      color: '#597ef7'
    },
    {
      name: 'nginx_busy_connection_ratio',
      display_name: '繁忙连接占比',
      description: '读取和写入中的连接占活跃连接的比例。',
      unit: 'percent',
      query: 'clamp_max(100 * (nginx_reading{__$labels__} + nginx_writing{__$labels__}) / clamp_min(nginx_active{__$labels__}, 1), 100)',
      color: '#ff8a1f'
    },
    {
      name: 'nginx_waiting_connection_ratio',
      display_name: '等待连接占比',
      description: '等待连接占活跃连接的比例。',
      unit: 'percent',
      query: 'clamp_max(100 * nginx_waiting{__$labels__} / clamp_min(nginx_active{__$labels__}, 1), 100)',
      color: '#9aa9bf'
    },
    {
      name: 'nginx_handled_accept_ratio',
      display_name: '连接处理完成率',
      description: '连接处理速率相对接受速率的比例。',
      unit: 'percent',
      query: '100 * rate(nginx_handled{__$labels__}[5m]) / clamp_min(rate(nginx_accepts{__$labels__}[5m]), 1e-6)',
      color: '#27c274'
    }
  ],
  summaryCards: [
    {
      title: '活跃连接数',
      metric: 'nginx_active',
      color: '#2f6bff',
      icon: 'node',
      guide: [{ label: '活跃连接', detail: '当前活跃客户端连接数，反映服务并发负载。' }],
      footer: [{ label: '等待连接', metric: 'nginx_waiting', unit: 'counts' }]
    },
    {
      title: '请求速率',
      metric: 'nginx_requests_rate',
      color: '#27c274',
      icon: 'thunder',
      guide: [{ label: '请求速率', detail: '每秒处理请求数，反映 Nginx 实时吞吐。' }],
      footer: [{ label: '处理连接', metric: 'nginx_handled_rate', unit: 'cps' }]
    },
    {
      title: '繁忙连接占比',
      metric: 'nginx_busy_connection_ratio',
      color: '#ff8a1f',
      icon: 'api',
      guide: [{ label: '繁忙连接', detail: '读取和写入中的连接占活跃连接的比例，可快速判断当前是否处于忙碌处理状态。' }],
      footer: [{ label: '等待占比', metric: 'nginx_waiting_connection_ratio', unit: 'percent' }]
    },
    {
      title: '连接处理完成率',
      metric: 'nginx_handled_accept_ratio',
      color: '#27c274',
      icon: 'thunder',
      compare: true,
      compareFavorableDirection: 'up',
      guide: [{ label: '处理完成率', detail: '连接处理速率相对连接接受速率的比例，偏低时要关注连接处理失败或积压。' }],
      footer: [{ label: '接受速率', metric: 'nginx_accepts_rate', unit: 'cps' }]
    }
  ],
  charts: [
    {
      title: '连接状态趋势',
      subtitle: '连接状态变化',
      metric: 'nginx_active',
      guide: [{ label: '连接状态', detail: '活跃、读取、写入、等待连接数的时间变化。' }],
      series: [
        { metric: 'nginx_active', label: '活跃连接', color: '#2f6bff', unit: 'counts' },
        { metric: 'nginx_reading', label: '读取连接', color: '#27c274', unit: 'counts' },
        { metric: 'nginx_writing', label: '写入连接', color: '#ff8a1f', unit: 'counts' },
        { metric: 'nginx_waiting', label: '等待连接', color: '#9aa9bf', unit: 'counts' }
      ]
    },
    {
      title: '连接接受/处理速率',
      subtitle: '接受 vs 处理（差值即被丢弃的连接）',
      metric: 'nginx_accepts_rate',
      guide: [{ label: '吞吐速率', detail: '连接接受速率与连接处理速率的对比，两线分叉（处理 < 接受）即有连接被丢弃。请求速率见上方 KPI 卡。' }],
      series: [
        { metric: 'nginx_accepts_rate', label: '接受速率', color: '#13c2c2', unit: 'cps' },
        { metric: 'nginx_handled_rate', label: '处理速率', color: '#8a5cff', unit: 'cps' }
      ]
    },
    {
      title: '连接占比趋势',
      subtitle: '繁忙与等待占比',
      metric: 'nginx_busy_connection_ratio',
      guide: [{ label: '连接占比', detail: '对比繁忙连接与等待连接的占比变化，识别负载结构是否出现偏移。' }],
      series: [
        { metric: 'nginx_busy_connection_ratio', label: '繁忙占比', color: '#ff8a1f', unit: 'percent' },
        { metric: 'nginx_waiting_connection_ratio', label: '等待占比', color: '#9aa9bf', unit: 'percent' }
      ]
    }
  ],
  ringPanels: [
    {
      title: '连接状态分布',
      subtitle: '读取、写入与等待',
      centerMetric: 'nginx_active',
      centerCaption: '活跃连接',
      centerUnit: 'counts',
      guide: [{ label: '连接状态', detail: '按读取、写入、等待状态拆分当前连接结构。' }],
      segments: [
        { label: '读取连接', metric: 'nginx_reading', color: '#27c274', unit: 'counts' },
        { label: '写入连接', metric: 'nginx_writing', color: '#ff8a1f', unit: 'counts' },
        { label: '等待连接', metric: 'nginx_waiting', color: '#9aa9bf', unit: 'counts' }
      ]
    }
  ],
  barPanels: [
    {
      title: '连接压力',
      subtitle: 'Reading / Writing / Waiting',
      showTrend: true,
      guide: [{ label: '连接压力', detail: '读取/写入/等待中的连接构成。Reading、Writing 偏高代表处理压力大，Waiting 为 keepalive 空闲连接。' }],
      items: [
        { label: 'Reading', metric: 'nginx_reading', color: '#2f6bff', unit: 'counts' },
        { label: 'Writing', metric: 'nginx_writing', color: '#ff8a1f', unit: 'counts' },
        { label: 'Waiting', metric: 'nginx_waiting', color: '#9aa9bf', unit: 'counts' }
      ]
    }
  ],
  details: []
};
