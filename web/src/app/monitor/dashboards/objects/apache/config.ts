import type { SimpleDashboardConfig } from '../common/simple-dashboard-core';

export const APACHE_DASHBOARD_CONFIG: SimpleDashboardConfig = {
  routeKey: 'apache',
  pageTitle: 'Apache 监控仪表盘',
  objectFallbackName: 'Apache',
  instanceType: 'apache',
  collectionStatusQuery: "count({instance_type='apache', collect_type='middleware', __$labels__}) by (instance_id)",
  metaItems: ['Telegraf', 'middleware'],
  metrics: [
    {
      name: 'apache_ServerUptimeSeconds',
      display_name: '服务运行时长',
      description: 'Apache 服务自启动以来的运行时长。',
      unit: 's',
      query: 'apache_ServerUptimeSeconds{__$labels__}',
      color: '#27c274'
    },
    {
      name: 'apache_ReqPerSec',
      display_name: '请求处理速率',
      description: 'Apache 每秒处理请求数量。',
      unit: 'cps',
      query: 'apache_ReqPerSec{__$labels__}',
      color: '#2f6bff'
    },
    {
      name: 'apache_BytesPerSec',
      display_name: '数据传输速率',
      description: 'Apache 每秒传输数据量。',
      unit: 'kibyteps',
      query: 'apache_BytesPerSec{__$labels__}',
      color: '#13c2c2'
    },
    {
      name: 'apache_BusyWorkers',
      display_name: '忙碌 Worker',
      description: '当前正在处理请求的 Apache Worker 数量。',
      unit: 'counts',
      query: 'apache_BusyWorkers{__$labels__}',
      color: '#ff8a1f'
    },
    {
      name: 'apache_IdleWorkers',
      display_name: '空闲 Worker',
      description: '当前空闲可接收请求的 Apache Worker 数量。',
      unit: 'counts',
      query: 'apache_IdleWorkers{__$labels__}',
      color: '#27c274'
    },
    {
      name: 'apache_worker_saturation_pct',
      display_name: 'Worker 饱和度',
      description: '忙碌 Worker 占总 Worker 的比例，反映请求处理容量的使用程度。',
      unit: 'percent',
      query: '100 * (apache_BusyWorkers{__$labels__} / clamp_min(apache_BusyWorkers{__$labels__} + apache_IdleWorkers{__$labels__}, 1))',
      color: '#ff8a1f'
    },
    {
      name: 'apache_CPULoad',
      display_name: 'CPU Load',
      description: 'Apache 进程 CPU 负载。',
      unit: 'percent',
      query: 'apache_CPULoad{__$labels__}',
      color: '#8a5cff'
    },
    {
      name: 'apache_Load1',
      display_name: '1 分钟负载',
      description: '系统 1 分钟平均负载。',
      unit: 'none',
      query: 'apache_Load1{__$labels__}',
      color: '#2f6bff'
    },
    {
      name: 'apache_Load5',
      display_name: '5 分钟负载',
      description: '系统 5 分钟平均负载。',
      unit: 'none',
      query: 'apache_Load5{__$labels__}',
      color: '#13c2c2'
    },
    {
      name: 'apache_Load15',
      display_name: '15 分钟负载',
      description: '系统 15 分钟平均负载。',
      unit: 'none',
      query: 'apache_Load15{__$labels__}',
      color: '#9aa9bf'
    },
    {
      name: 'apache_TotalAccesses_rate',
      display_name: '请求变化速率',
      description: 'Apache 总访问次数变化速率。',
      unit: 'cps',
      query: 'apache_TotalAccesses_rate{__$labels__}',
      color: '#27c274'
    },
    {
      name: 'apache_scboard_open',
      display_name: 'Open 连接',
      description: 'Apache scoreboard 中 open 状态连接数量。',
      unit: 'counts',
      query: 'apache_scboard_open{__$labels__}',
      color: '#9aa9bf'
    },
    {
      name: 'apache_scboard_waiting',
      display_name: 'Waiting 连接',
      description: 'Apache scoreboard 中 waiting 状态连接数量。',
      unit: 'counts',
      query: 'apache_scboard_waiting{__$labels__}',
      color: '#27c274'
    },
    {
      name: 'apache_scboard_reading',
      display_name: 'Reading 连接',
      description: 'Apache scoreboard 中 reading 状态连接数量。',
      unit: 'counts',
      query: 'apache_scboard_reading{__$labels__}',
      color: '#2f6bff'
    },
    {
      name: 'apache_scboard_sending',
      display_name: 'Sending 连接',
      description: 'Apache scoreboard 中 sending 状态连接数量。',
      unit: 'counts',
      query: 'apache_scboard_sending{__$labels__}',
      color: '#d48806'
    },
    {
      name: 'apache_scboard_open_rate',
      display_name: 'Open 连接变化速率',
      description: 'Apache scoreboard open 状态连接变化速率。',
      unit: 'cps',
      query: 'apache_scboard_open_rate{__$labels__}',
      color: '#9aa9bf'
    },
    {
      name: 'apache_CacheCurrentEntries',
      display_name: '缓存当前条目',
      description: 'Apache 当前缓存条目数量。',
      unit: 'counts',
      query: 'apache_CacheCurrentEntries{__$labels__}',
      color: '#2f6bff'
    },
    {
      name: 'apache_ParentServerConfigGeneration',
      display_name: '配置重载次数',
      description: 'Apache 父进程配置重载次数，每次 reload 递增。突增通常对应变更事件或故障重启。',
      unit: 'counts',
      query: 'apache_ParentServerConfigGeneration{__$labels__}',
      color: '#faad14'
    }
  ],
  summaryCards: [
    {
      title: '服务运行时长',
      metric: 'apache_ServerUptimeSeconds',
      color: '#27c274',
      icon: 'clock',
      formatter: 'duration',
      isUptimeCard: true,
      guide: [{ label: '运行时长', detail: 'Apache 服务自启动以来持续运行的时间。' }],
      footer: [{ label: 'CPU Load', metric: 'apache_CPULoad', unit: 'percent' }]
    },
    {
      title: '请求处理速率',
      metric: 'apache_ReqPerSec',
      color: '#2f6bff',
      icon: 'thunder',
      guide: [{ label: '请求速率', detail: 'Apache 每秒处理请求数量，反映实时吞吐。' }],
      footer: [{ label: '访问变化', metric: 'apache_TotalAccesses_rate', unit: 'cps' }]
    },
    {
      title: '数据传输速率',
      metric: 'apache_BytesPerSec',
      color: '#13c2c2',
      icon: 'api',
      guide: [{ label: '传输速率', detail: 'Apache 每秒传输数据量，反映网络输出压力。' }],
      footer: [{ label: '忙碌 Worker', metric: 'apache_BusyWorkers', unit: 'counts' }]
    },
    {
      title: 'Worker 饱和度',
      metric: 'apache_worker_saturation_pct',
      unit: 'percent',
      color: '#ff8a1f',
      icon: 'node',
      compare: true,
      compareFavorableDirection: 'down',
      guide: [{ label: 'Worker 饱和度', detail: '忙碌 Worker 占总 Worker 比例。逼近 100% 说明处理容量即将耗尽，新请求将排队等待。' }],
      footer: [{ label: '空闲 Worker', metric: 'apache_IdleWorkers', unit: 'counts' }]
    },
    {
      title: 'CPU Load',
      metric: 'apache_CPULoad',
      color: '#8a5cff',
      icon: 'thunder',
      guide: [
        { label: 'CPU Load', detail: 'Apache 进程 CPU 占比，仅反映 httpd 进程自身用量。' },
        { label: '注意', detail: '与系统负载（apache_Load*）不同：系统负载含所有进程，不能等同于 Apache 的 CPU 压力。' }
      ],
      footer: [{ label: '5 分钟负载', metric: 'apache_Load5', unit: 'none' }]
    }
  ],
  charts: [
    {
      title: '请求吞吐趋势',
      subtitle: '请求量 vs 流量',
      metric: 'apache_ReqPerSec',
      guide: [{ label: '请求吞吐', detail: '对比请求处理速率（req/s）与字节传输速率（bytes/s），两线同步上升为正常，流量飙升而请求平稳则可能有大文件传输。' }],
      series: [
        { metric: 'apache_ReqPerSec', label: '请求处理速率', color: '#2f6bff', unit: 'cps' },
        { metric: 'apache_BytesPerSec', label: '数据传输速率', color: '#13c2c2', unit: 'kibyteps' }
      ]
    },
    {
      title: 'Worker 状态趋势',
      subtitle: '忙碌、空闲',
      metric: 'apache_BusyWorkers',
      guide: [{ label: 'Worker 状态', detail: '对比忙碌和空闲 Worker 数量，识别处理容量是否紧张。' }],
      series: [
        { metric: 'apache_BusyWorkers', label: '忙碌 Worker', color: '#ff8a1f', unit: 'counts' },
        { metric: 'apache_IdleWorkers', label: '空闲 Worker', color: '#27c274', unit: 'counts' }
      ]
    },
    {
      title: 'Scoreboard 状态趋势',
      subtitle: '连接状态变化',
      metric: 'apache_scboard_open',
      guide: [{ label: 'Scoreboard', detail: 'Apache scoreboard 中 open、waiting、reading、sending 状态的连接变化。' }],
      series: [
        { metric: 'apache_scboard_open', label: 'Open', color: '#9aa9bf', unit: 'counts' },
        { metric: 'apache_scboard_waiting', label: 'Waiting', color: '#27c274', unit: 'counts' },
        { metric: 'apache_scboard_reading', label: 'Reading', color: '#2f6bff', unit: 'counts' },
        { metric: 'apache_scboard_sending', label: 'Sending', color: '#d48806', unit: 'counts' }
      ]
    },
    {
      title: '系统负载趋势',
      subtitle: '1、5、15 分钟',
      metric: 'apache_Load1',
      guide: [
        { label: '系统负载', detail: '对比 1、5、15 分钟平均负载，判断压力是否持续。' },
        { label: '注意', detail: '系统负载含所有进程（非仅 Apache），不能直接等同于 Apache 的 CPU 压力。' }
      ],
      series: [
        { metric: 'apache_Load1', label: '1 分钟', color: '#2f6bff', unit: 'none' },
        { metric: 'apache_Load5', label: '5 分钟', color: '#13c2c2', unit: 'none' },
        { metric: 'apache_Load15', label: '15 分钟', color: '#9aa9bf', unit: 'none' }
      ]
    }
  ],
  ringPanels: [
    {
      title: 'Worker 使用分布',
      subtitle: '忙碌、空闲',
      centerMetric: 'apache_worker_saturation_pct',
      centerCaption: 'Worker 饱和度',
      centerUnit: 'percent',
      guide: [{ label: 'Worker 分布', detail: '当前忙碌与空闲 Worker 数量分布，中心为饱和度百分比。' }],
      segments: [
        { label: '忙碌 Worker', metric: 'apache_BusyWorkers', color: '#ff8a1f', unit: 'counts' },
        { label: '空闲 Worker', metric: 'apache_IdleWorkers', color: '#27c274', unit: 'counts' }
      ]
    }
  ],
  details: [
    {
      title: '运行细节',
      subtitle: '连接速率 · 缓存 · 配置',
      rows: [
        { label: 'Open 连接变化速率', metric: 'apache_scboard_open_rate', unit: 'cps' },
        { label: '缓存当前条目', metric: 'apache_CacheCurrentEntries', unit: 'counts' },
        { label: '配置重载次数', metric: 'apache_ParentServerConfigGeneration', unit: 'counts' }
      ]
    }
  ]
};
