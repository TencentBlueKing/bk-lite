import type { SimpleDashboardConfig } from '../common/simple-dashboard-core';

/**
 * HAProxy 专业盘：LB 语义。
 * 所有指标带 pxname + svname；实例级 KPI 必须按角色过滤，禁止 FE+BE+server 三重加总。
 * - 入口流量/会话/请求 → svname="FRONTEND"
 * - 队列/时延/5xx/后端健康 → svname="BACKEND"
 */
export const HAPROXY_DASHBOARD_CONFIG: SimpleDashboardConfig = {
  routeKey: 'haproxy',
  pageTitle: 'HAProxy 监控仪表盘',
  objectFallbackName: 'Haproxy',
  instanceType: 'haproxy',
  collectionStatusQuery:
    "count({instance_type='haproxy', collect_type='middleware', __$labels__}) by (instance_id)",
  metaItems: ['Telegraf', 'middleware', 'Load Balancer'],
  metrics: [
    {
      name: 'haproxy_fe_sessions',
      display_name: '前端当前会话',
      description: 'FRONTEND 当前活跃会话数（按前端代理汇总）。',
      unit: 'counts',
      query: 'sum by (instance_id) (haproxy_scur{svname="FRONTEND",__$labels__})',
      color: '#2f6bff'
    },
    {
      name: 'haproxy_fe_req_rate',
      display_name: '前端 HTTP 请求速率',
      description: 'FRONTEND HTTP 请求速率。',
      unit: 'cps',
      query: 'sum by (instance_id) (haproxy_req_rate{svname="FRONTEND",__$labels__})',
      color: '#27c274'
    },
    {
      name: 'haproxy_fe_session_rate',
      display_name: '前端会话建立速率',
      description: 'FRONTEND 新建会话速率。',
      unit: 'cps',
      query: 'sum by (instance_id) (haproxy_rate{svname="FRONTEND",__$labels__})',
      color: '#13c2c2'
    },
    {
      name: 'haproxy_be_rtime',
      display_name: '后端平均响应时间',
      description: 'BACKEND 平均响应时间（最近约 1024 请求）。',
      unit: 'ms',
      query: 'avg by (instance_id) (haproxy_rtime{svname="BACKEND",__$labels__})',
      color: '#ff8a1f'
    },
    {
      name: 'haproxy_be_qtime',
      display_name: '后端平均排队时间',
      description: 'BACKEND 平均排队等待时间。',
      unit: 'ms',
      query: 'avg by (instance_id) (haproxy_qtime{svname="BACKEND",__$labels__})',
      color: '#faad14'
    },
    {
      name: 'haproxy_be_ctime',
      display_name: '后端平均建连时间',
      description: 'BACKEND 平均连接建立时间。',
      unit: 'ms',
      query: 'avg by (instance_id) (haproxy_ctime{svname="BACKEND",__$labels__})',
      color: '#722ed1'
    },
    {
      name: 'haproxy_be_ttime',
      display_name: '后端平均端到端时间',
      description: 'BACKEND 平均总会话时间。',
      unit: 'ms',
      query: 'avg by (instance_id) (haproxy_ttime{svname="BACKEND",__$labels__})',
      color: '#8a5cff'
    },
    {
      name: 'haproxy_be_5xx_rate',
      display_name: '后端 5xx 速率',
      description: 'BACKEND HTTP 5xx 响应速率。',
      unit: 'cps',
      query: 'sum by (instance_id) (rate(haproxy_hrsp_5xx{svname="BACKEND",__$labels__}[__$window__]))',
      color: '#ff4d4f'
    },
    {
      name: 'haproxy_be_4xx_rate',
      display_name: '后端 4xx 速率',
      description: 'BACKEND HTTP 4xx 响应速率。',
      unit: 'cps',
      query: 'sum by (instance_id) (rate(haproxy_hrsp_4xx{svname="BACKEND",__$labels__}[__$window__]))',
      color: '#faad14'
    },
    {
      name: 'haproxy_be_2xx_rate',
      display_name: '后端 2xx 速率',
      description: 'BACKEND HTTP 2xx 响应速率。',
      unit: 'cps',
      query: 'sum by (instance_id) (rate(haproxy_hrsp_2xx{svname="BACKEND",__$labels__}[__$window__]))',
      color: '#27c274'
    },
    {
      name: 'haproxy_be_qcur',
      display_name: '后端排队请求',
      description: 'BACKEND 当前排队等待服务器的请求数。',
      unit: 'counts',
      query: 'sum by (instance_id) (haproxy_qcur{svname="BACKEND",__$labels__})',
      color: '#ff8a1f'
    },
    {
      name: 'haproxy_be_act',
      display_name: '活跃服务器数',
      description: 'BACKEND 当前活跃（非 backup）服务器数。',
      unit: 'counts',
      query: 'sum by (instance_id) (max by (instance_id, pxname) (haproxy_act{svname="BACKEND",__$labels__}))',
      color: '#27c274'
    },
    {
      name: 'haproxy_be_bck',
      display_name: '备份服务器数',
      description: 'BACKEND 当前可用备份服务器数。',
      unit: 'counts',
      query: 'sum by (instance_id) (max by (instance_id, pxname) (haproxy_bck{svname="BACKEND",__$labels__}))',
      color: '#8c8c8c'
    },
    {
      name: 'haproxy_be_chkfail_rate',
      display_name: '健康检查失败速率',
      description: 'BACKEND 健康检查失败速率。',
      unit: 'cps',
      query: 'sum by (instance_id) (rate(haproxy_chkfail{svname="BACKEND",__$labels__}[__$window__]))',
      color: '#ff4d4f'
    },
    {
      name: 'haproxy_be_chkdown_rate',
      display_name: '宕机切换速率',
      description: 'BACKEND UP→DOWN 切换速率。',
      unit: 'cps',
      query: 'sum by (instance_id) (rate(haproxy_chkdown{svname="BACKEND",__$labels__}[__$window__]))',
      color: '#ff4d4f'
    },
    {
      name: 'haproxy_be_econ_rate',
      display_name: '连接错误速率',
      description: '连接后端失败速率。',
      unit: 'cps',
      query: 'sum by (instance_id) (rate(haproxy_econ{svname="BACKEND",__$labels__}[__$window__]))',
      color: '#ff4d4f'
    },
    {
      name: 'haproxy_be_eresp_rate',
      display_name: '响应错误速率',
      description: '后端响应错误速率。',
      unit: 'cps',
      query: 'sum by (instance_id) (rate(haproxy_eresp{svname="BACKEND",__$labels__}[__$window__]))',
      color: '#ff8a1f'
    },
    {
      name: 'haproxy_be_wretr_rate',
      display_name: '连接重试速率',
      description: '后端连接重试速率。',
      unit: 'cps',
      query: 'sum by (instance_id) (rate(haproxy_wretr{svname="BACKEND",__$labels__}[__$window__]))',
      color: '#faad14'
    },
    {
      name: 'haproxy_be_wredis_rate',
      display_name: '请求再分发速率',
      description: '请求被再分发到其他后端服务器的速率。',
      unit: 'cps',
      query: 'sum by (instance_id) (rate(haproxy_wredis{svname="BACKEND",__$labels__}[__$window__]))',
      color: '#722ed1'
    },
    {
      name: 'haproxy_fe_bin_rate',
      display_name: '前端入流量速率',
      description: 'FRONTEND 入向字节速率。',
      unit: 'byteps',
      query: 'sum by (instance_id) (rate(haproxy_bin{svname="FRONTEND",__$labels__}[__$window__]))',
      color: '#2f6bff'
    },
    {
      name: 'haproxy_fe_bout_rate',
      display_name: '前端出流量速率',
      description: 'FRONTEND 出向字节速率。',
      unit: 'byteps',
      query: 'sum by (instance_id) (rate(haproxy_bout{svname="FRONTEND",__$labels__}[__$window__]))',
      color: '#13c2c2'
    }
  ],
  summaryCards: [
    {
      title: 'HTTP 请求速率',
      metric: 'haproxy_fe_req_rate',
      unit: 'cps',
      color: '#27c274',
      icon: 'thunder',
      compare: true,
      guide: [
        {
          label: '请求速率',
          detail: 'FRONTEND HTTP 请求速率，衡量入口负载。'
        }
      ]
    },
    {
      title: '平均响应时间',
      metric: 'haproxy_be_rtime',
      unit: 'ms',
      color: '#ff8a1f',
      icon: 'clock',
      compare: true,
      compareFavorableDirection: 'down',
      guide: [
        {
          label: '响应时间',
          detail: 'BACKEND 平均响应时间。升高时结合排队时间与建连时间拆分瓶颈。'
        }
      ],
      footer: [{ label: '排队', metric: 'haproxy_be_qtime', unit: 'ms' }]
    },
    {
      title: '活跃服务器',
      metric: 'haproxy_be_act',
      unit: 'counts',
      color: '#27c274',
      icon: 'health',
      compare: true,
      compareFavorableDirection: 'up',
      guide: [
        {
          label: '活跃服务器',
          detail: 'BACKEND 池中当前活跃服务器数（按 proxy 去重后汇总）。下跌结合健康检查失败/宕机切换排查。'
        }
      ],
      footer: [{ label: '备份', metric: 'haproxy_be_bck', unit: 'counts' }]
    }
  ],
  charts: [
    {
      title: '前端会话',
      subtitle: 'FRONTEND 当前会话数',
      metric: 'haproxy_fe_sessions',
      guide: [{ label: '会话', detail: 'FRONTEND 当前活跃会话数。' }],
      series: [{ metric: 'haproxy_fe_sessions', label: '当前会话', color: '#2f6bff', unit: 'counts' }]
    },
    {
      title: '前端请求速率',
      subtitle: 'HTTP 请求 / 会话建立',
      metric: 'haproxy_fe_req_rate',
      guide: [
        { label: '请求', detail: 'FRONTEND HTTP 请求速率。' },
        { label: '会话速率', detail: 'FRONTEND 新建会话速率。' }
      ],
      series: [
        { metric: 'haproxy_fe_req_rate', label: '请求速率', color: '#27c274', unit: 'cps' },
        { metric: 'haproxy_fe_session_rate', label: '会话速率', color: '#13c2c2', unit: 'cps' }
      ]
    },
    {
      title: '后端时延拆分',
      subtitle: '排队 / 建连 / 响应 / 端到端',
      metric: 'haproxy_be_rtime',
      guide: [
        {
          label: '时延',
          detail: 'BACKEND 时延拆分：排队(qtime)、建连(ctime)、响应(rtime)、端到端(ttime)。'
        }
      ],
      series: [
        { metric: 'haproxy_be_qtime', label: '排队', color: '#faad14', unit: 'ms' },
        { metric: 'haproxy_be_ctime', label: '建连', color: '#722ed1', unit: 'ms' },
        { metric: 'haproxy_be_rtime', label: '响应', color: '#ff8a1f', unit: 'ms' },
        { metric: 'haproxy_be_ttime', label: '端到端', color: '#8a5cff', unit: 'ms' }
      ]
    },
    {
      title: 'HTTP 状态速率',
      subtitle: 'BACKEND 2xx / 4xx / 5xx',
      metric: 'haproxy_be_2xx_rate',
      guide: [
        { label: '状态码', detail: 'BACKEND 响应状态码速率。关注 5xx 抬升。' }
      ],
      series: [
        { metric: 'haproxy_be_2xx_rate', label: '2xx', color: '#27c274', unit: 'cps' },
        { metric: 'haproxy_be_4xx_rate', label: '4xx', color: '#faad14', unit: 'cps' },
        { metric: 'haproxy_be_5xx_rate', label: '5xx', color: '#ff4d4f', unit: 'cps' }
      ]
    },
    {
      title: '后端健康与错误',
      subtitle: '检查失败 / 宕机 / 连接错误 / 重试',
      metric: 'haproxy_be_chkfail_rate',
      guide: [
        {
          label: '健康与错误',
          detail: '健康检查失败、宕机切换、连接/响应错误与重试再分发。'
        }
      ],
      series: [
        { metric: 'haproxy_be_chkfail_rate', label: '检查失败', color: '#ff4d4f', unit: 'cps' },
        { metric: 'haproxy_be_chkdown_rate', label: '宕机切换', color: '#ff8a1f', unit: 'cps' },
        { metric: 'haproxy_be_econ_rate', label: '连接错误', color: '#722ed1', unit: 'cps' },
        { metric: 'haproxy_be_wretr_rate', label: '重试', color: '#faad14', unit: 'cps' }
      ]
    },
    {
      title: '前端流量',
      subtitle: '入向 / 出向字节速率',
      metric: 'haproxy_fe_bin_rate',
      guide: [
        { label: '流量', detail: 'FRONTEND 入向与出向字节速率。' }
      ],
      series: [
        { metric: 'haproxy_fe_bin_rate', label: '入向', color: '#2f6bff', unit: 'byteps' },
        { metric: 'haproxy_fe_bout_rate', label: '出向', color: '#13c2c2', unit: 'byteps' }
      ]
    }
  ],
  statusPanels: [],
  ringPanels: [],
  barPanels: [],
  details: []
};
