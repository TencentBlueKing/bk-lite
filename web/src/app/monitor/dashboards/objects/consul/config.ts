import type { SimpleDashboardConfig } from '../common/simple-dashboard-core';

const CONSUL_STATUS_ENUM = {
  0: { label: '通过', color: '#27c274' },
  1: { label: '警告', color: '#faad14' },
  2: { label: '危险', color: '#ff4d4f' }
};

export const CONSUL_DASHBOARD_CONFIG: SimpleDashboardConfig = {
  routeKey: 'consul',
  pageTitle: 'Consul 监控仪表盘',
  objectFallbackName: 'Consul',
  instanceType: 'consul',
  collectionStatusQuery: "count({instance_type='consul', collect_type='middleware', __$labels__}) by (instance_id)",
  metaItems: ['Telegraf', 'middleware', 'Health Check'],
  metrics: [
    {
      name: 'consul_checks_overall',
      display_name: '整体健康状态',
      description: 'Consul 节点所有健康检查的最坏状态（0 通过 / 1 警告 / 2 危险），由各检查状态取最大值聚合得出。',
      unit: 'none',
      query: 'max(consul_health_checks_status{__$labels__})',
      color: '#27c274'
    },
    {
      name: 'consul_checks_total',
      display_name: '检查总数',
      description: 'Consul 节点上的健康检查总数量（按检查序列计数聚合）。',
      unit: 'counts',
      query: 'count(consul_health_checks_status{__$labels__})',
      color: '#2f6bff'
    },
    {
      name: 'consul_checks_passing',
      display_name: '通过检查数',
      description: '当前处于「通过」状态的健康检查数量（按逐检查通过标志求和聚合）。',
      unit: 'counts',
      query: 'sum(consul_health_checks_passing{__$labels__})',
      color: '#27c274'
    },
    {
      name: 'consul_checks_warning',
      display_name: '警告检查数',
      description: '当前处于「警告」状态的健康检查数量（按逐检查警告标志求和聚合）。',
      unit: 'counts',
      query: 'sum(consul_health_checks_warning{__$labels__})',
      color: '#faad14'
    },
    {
      name: 'consul_checks_critical',
      display_name: '危险检查数',
      description: '当前处于「危险」状态的健康检查数量（按逐检查危险标志求和聚合），非零即需立即排查。',
      unit: 'counts',
      query: 'sum(consul_health_checks_critical{__$labels__})',
      color: '#ff4d4f'
    }
  ],
  summaryCards: [
    {
      title: '整体健康状态',
      metric: 'consul_checks_overall',
      color: '#27c274',
      icon: 'api',
      enumMap: CONSUL_STATUS_ENUM,
      guide: [{ label: '整体状态', detail: '所有健康检查的最坏状态，存在危险/警告检查时整体即降级，用于一眼判断节点健康。' }],
      footer: [{ label: '危险检查', metric: 'consul_checks_critical', unit: 'counts' }]
    },
    {
      title: '检查总数',
      metric: 'consul_checks_total',
      unit: 'counts',
      color: '#2f6bff',
      icon: 'node',
      guide: [{ label: '检查总数', detail: '当前注册的健康检查总数，反映该 Consul 节点纳管的服务/检查规模。' }],
      footer: [{ label: '通过检查', metric: 'consul_checks_passing', unit: 'counts' }]
    },
    {
      title: '危险检查数',
      metric: 'consul_checks_critical',
      unit: 'counts',
      color: '#ff4d4f',
      icon: 'api',
      compare: true,
      compareFavorableDirection: 'down',
      guide: [{ label: '危险检查', detail: '处于危险状态的检查数量，非零代表有服务不可用，需立即排查。' }],
      footer: [{ label: '警告检查', metric: 'consul_checks_warning', unit: 'counts' }]
    },
    {
      title: '通过检查数',
      metric: 'consul_checks_passing',
      unit: 'counts',
      color: '#27c274',
      icon: 'node',
      guide: [{ label: '通过检查', detail: '处于通过状态的检查数量，正常情况下应等于检查总数。' }],
      footer: [{ label: '检查总数', metric: 'consul_checks_total', unit: 'counts' }]
    }
  ],
  charts: [
    {
      title: '健康检查趋势',
      subtitle: '通过 / 警告 / 危险 计数',
      metric: 'consul_checks_passing',
      guide: [{ label: '健康趋势', detail: '通过/警告/危险检查数随时间变化，回答「检查何时开始劣化」。危险或警告曲线抬升即需关注。' }],
      series: [
        { metric: 'consul_checks_passing', label: '通过', color: '#27c274', unit: 'counts' },
        { metric: 'consul_checks_warning', label: '警告', color: '#faad14', unit: 'counts' },
        { metric: 'consul_checks_critical', label: '危险', color: '#ff4d4f', unit: 'counts' }
      ]
    }
  ],
  statusPanels: [],
  details: [],
  ringPanels: [
    {
      title: '健康检查状态分布',
      subtitle: '通过 / 警告 / 危险 占比',
      centerMetric: 'consul_checks_total',
      centerCaption: '检查总数',
      centerUnit: 'counts',
      guide: [{ label: '状态分布', detail: '按通过/警告/危险拆分全部健康检查，中心为检查总数。绿环占满即全部健康。' }],
      segments: [
        { label: '通过', metric: 'consul_checks_passing', color: '#27c274', unit: 'counts' },
        { label: '警告', metric: 'consul_checks_warning', color: '#faad14', unit: 'counts' },
        { label: '危险', metric: 'consul_checks_critical', color: '#ff4d4f', unit: 'counts' }
      ]
    }
  ],
  barPanels: []
};
