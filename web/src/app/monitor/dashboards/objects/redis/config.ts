import type { SimpleDashboardConfig } from '../common/simple-dashboard-core';

/**
 * Redis 仪表盘配置(config-driven)。
 *
 * Redis metrics.json 的全部指标均为实例级,无 db/keyspace 等自由维度,
 * 故不设「TopN 排行」分区(见审计计划 dimensionTopN=null)。
 *
 * 内存使用率 / 缓存命中率均带 maxmemory>0 / 命中分母的空态语义:
 * 查询层用 clamp_min / clamp_max 规避除零,UI 层无数据自动降级为 '--'。
 */
export const REDIS_DASHBOARD_CONFIG: SimpleDashboardConfig = {
  routeKey: 'redis',
  pageTitle: 'Redis 监控仪表盘',
  objectFallbackName: 'Redis',
  instanceType: 'redis',
  collectionStatusQuery: "count({instance_type='redis', collect_type='database', __$labels__}) by (instance_id)",
  metaItems: ['Telegraf', 'database'],
  metrics: [
    {
      name: 'redis_uptime',
      display_name: '运行时长',
      description: 'Redis 实例持续运行时间，反映服务稳定性。',
      unit: 's',
      query: 'redis_uptime{__$labels__}',
      color: '#597ef7'
    },
    {
      name: 'redis_used_memory',
      display_name: '内存使用量',
      description: 'Redis 实例当前占用的总内存，包括数据存储和内部数据结构。',
      unit: 'bytes',
      query: 'redis_used_memory{__$labels__}',
      color: '#2f6bff'
    },
    {
      name: 'redis_maxmemory',
      display_name: '内存上限配置',
      description: 'Redis 实例配置的最大可用内存限制。',
      unit: 'bytes',
      query: 'redis_maxmemory{__$labels__}',
      color: '#9aa9bf'
    },
    {
      name: 'redis_mem_available',
      display_name: '剩余可用内存',
      description: '配置上限内尚可使用的内存(上限减去已用),用于环图占比展示。',
      unit: 'bytes',
      query: 'clamp_min(max by (instance_id) (redis_maxmemory{__$labels__}) - max by (instance_id) (redis_used_memory{__$labels__}), 0)',
      color: '#e8f0fe'
    },
    {
      name: 'redis_memory_utilization',
      display_name: '内存使用率',
      description: '当前内存使用量占配置上限的比例。',
      unit: 'percent',
      query: 'clamp_max(100 * max by (instance_id) (redis_used_memory{__$labels__}) / on(instance_id) clamp_min(max by (instance_id) (redis_maxmemory{__$labels__}), 1), 100)',
      color: '#ff8a1f'
    },
    {
      name: 'redis_mem_fragmentation_ratio',
      display_name: '内存碎片率',
      description: '操作系统分配内存与 Redis 实际使用内存的比值，高比值表示碎片严重。',
      unit: 'none',
      query: 'redis_mem_fragmentation_ratio{__$labels__}',
      color: '#faad14'
    },
    {
      name: 'redis_instantaneous_ops_per_sec',
      display_name: '实时 OPS',
      description: 'Redis 实例当前每秒处理的命令数量。',
      unit: 'cps',
      query: 'redis_instantaneous_ops_per_sec{__$labels__}',
      color: '#27c274'
    },
    {
      name: 'redis_total_commands_processed_rate',
      display_name: '命令处理速率',
      description: 'Redis 实例处理命令的平均速率。',
      unit: 'cps',
      query: 'rate(redis_total_commands_processed{__$labels__}[5m])',
      color: '#13c2c2'
    },
    {
      name: 'redis_keyspace_hits_rate',
      display_name: '键命中频率',
      description: '键空间成功命中的频率，反映缓存命中效率。',
      unit: 'cps',
      query: 'rate(redis_keyspace_hits{__$labels__}[5m])',
      color: '#2f6bff'
    },
    {
      name: 'redis_keyspace_misses_rate',
      display_name: '键未命中频率',
      description: '键空间未命中的频率，高频率可能需要优化缓存策略。',
      unit: 'cps',
      query: 'rate(redis_keyspace_misses{__$labels__}[5m])',
      color: '#ff4d4f'
    },
    {
      name: 'redis_keyspace_hitrate',
      display_name: '缓存命中率',
      description: '键空间命中操作占总操作的比例，核心缓存性能指标。',
      unit: 'percent',
      query: 'redis_keyspace_hitrate{__$labels__}',
      color: '#8a5cff'
    },
    {
      name: 'redis_total_net_input_bytes_rate',
      display_name: '网络入流量',
      description: 'Redis 实例接收网络数据的速率。',
      unit: 'byteps',
      query: 'rate(redis_total_net_input_bytes{__$labels__}[5m])',
      color: '#2f6bff'
    },
    {
      name: 'redis_total_net_output_bytes_rate',
      display_name: '网络出流量',
      description: 'Redis 实例发送网络数据的速率。',
      unit: 'byteps',
      query: 'rate(redis_total_net_output_bytes{__$labels__}[5m])',
      color: '#27c274'
    },
    {
      name: 'redis_clients',
      display_name: '客户端连接数',
      description: '当前活跃的客户端连接数量。',
      unit: 'counts',
      query: 'redis_clients{__$labels__}',
      color: '#2f6bff'
    },
    {
      name: 'redis_blocked_clients',
      display_name: '阻塞客户端数',
      description: '当前处于阻塞等待状态的客户端数量。',
      unit: 'counts',
      query: 'redis_blocked_clients{__$labels__}',
      color: '#ff8a1f'
    },
    {
      name: 'redis_expired_keys_rate',
      display_name: '键过期频率',
      description: '键因到期自动删除的频率。',
      unit: 'cps',
      query: 'rate(redis_expired_keys{__$labels__}[5m])',
      color: '#faad14'
    },
    {
      name: 'redis_evicted_keys_rate',
      display_name: '键驱逐频率',
      description: '因内存达到上限而被主动淘汰的键频率，非零说明内存压力大。',
      unit: 'cps',
      query: 'rate(redis_evicted_keys{__$labels__}[5m])',
      color: '#ff4d4f'
    },
    {
      name: 'redis_rejected_connections_rate',
      display_name: '连接拒绝频率',
      description: '因达到最大连接数而被拒绝的连接请求频率。',
      unit: 'cps',
      query: 'rate(redis_rejected_connections{__$labels__}[5m])',
      color: '#ff4d4f'
    }
  ],
  summaryCards: [
    {
      title: '运行时长',
      metric: 'redis_uptime',
      unit: 's',
      formatter: 'duration',
      isUptimeCard: true,
      color: '#597ef7',
      icon: 'clock',
      guide: [{ label: '运行时长', detail: 'Redis 实例持续运行时间,反映服务稳定性;期间发生重启会重新计时。' }],
      footer: [{ label: '启动', metric: 'redis_uptime', formatter: 'startedAt' }]
    },
    {
      title: '内存使用率',
      metric: 'redis_memory_utilization',
      color: '#ff8a1f',
      icon: 'memory',
      compare: true,
      guide: [{ label: '内存使用率', detail: '已用内存占配置上限的比例,接近 100% 时可能触发键驱逐。未配置 maxmemory 时无数据。' }],
      footer: [
        { label: '已用内存', metric: 'redis_used_memory', unit: 'bytes' }
      ]
    },
    {
      title: '缓存命中率',
      metric: 'redis_keyspace_hitrate',
      color: '#8a5cff',
      icon: 'database',
      compare: true,
      compareFavorableDirection: 'up',
      guide: [{ label: '缓存命中率', detail: '键空间命中占总查询的比例,偏低说明热点数据未驻留缓存。' }],
      footer: [{ label: '未命中频率', metric: 'redis_keyspace_misses_rate', unit: 'cps' }]
    },
    {
      title: '键驱逐频率',
      metric: 'redis_evicted_keys_rate',
      color: '#ff4d4f',
      icon: 'thunder',
      compare: true,
      guide: [{ label: '键驱逐', detail: '因内存达到上限被主动淘汰的键频率,非零说明内存压力大。' }],
      footer: [{ label: '键过期频率', metric: 'redis_expired_keys_rate', unit: 'cps' }]
    },
    {
      title: '客户端连接数',
      metric: 'redis_clients',
      color: '#2f6bff',
      icon: 'node',
      guide: [{ label: '客户端连接', detail: '当前活跃的客户端连接数量。' }],
      footer: [{ label: '阻塞客户端', metric: 'redis_blocked_clients', unit: 'counts' }]
    }
  ],
  charts: [
    {
      title: '内存压力趋势',
      subtitle: '已用内存与上限',
      metric: 'redis_used_memory',
      guide: [
        { label: '已用内存', detail: 'Redis 实例当前占用内存。' },
        { label: '内存上限', detail: '配置的最大可用内存(maxmemory),虚线表示;未配置时无此线。' }
      ],
      series: [
        { metric: 'redis_used_memory', label: '已用内存', color: '#2f6bff', unit: 'bytes' },
        { metric: 'redis_maxmemory', label: '内存上限', color: '#9aa9bf', unit: 'bytes', style: 'limit' }
      ]
    },
    {
      title: '命中未命中趋势',
      subtitle: '键命中与未命中',
      metric: 'redis_keyspace_hits_rate',
      guide: [
        { label: '键命中', detail: '键空间成功命中频率。' },
        { label: '键未命中', detail: '键空间未命中频率,持续升高需优化缓存策略。' }
      ],
      series: [
        { metric: 'redis_keyspace_hits_rate', label: '键命中', color: '#2f6bff', unit: 'cps' },
        { metric: 'redis_keyspace_misses_rate', label: '键未命中', color: '#ff4d4f', unit: 'cps' }
      ]
    },
    {
      title: '命令吞吐趋势',
      subtitle: '实时 OPS 与命令速率',
      metric: 'redis_instantaneous_ops_per_sec',
      guide: [
        { label: '实时 OPS', detail: '当前每秒处理命令数(瞬时)。' },
        { label: '命令速率', detail: '过去 5 分钟命令处理平均速率。' }
      ],
      series: [
        { metric: 'redis_instantaneous_ops_per_sec', label: '实时 OPS', color: '#27c274', unit: 'cps' },
        { metric: 'redis_total_commands_processed_rate', label: '命令速率', color: '#13c2c2', unit: 'cps' }
      ]
    },
    {
      title: '键生命周期',
      subtitle: '过期、驱逐与连接拒绝',
      metric: 'redis_expired_keys_rate',
      guide: [
        { label: '键过期频率', detail: '键到期被自动清除的速率。' },
        { label: '键驱逐频率', detail: '内存压力下被驱逐键的速率,非零说明内存吃紧。' },
        { label: '连接拒绝频率', detail: '因超出 maxclients 被拒绝的连接速率。' }
      ],
      series: [
        { metric: 'redis_expired_keys_rate', label: '键过期频率', color: '#2f6bff', unit: 'cps' },
        { metric: 'redis_evicted_keys_rate', label: '键驱逐频率', color: '#ff4d4f', unit: 'cps' },
        { metric: 'redis_rejected_connections_rate', label: '连接拒绝频率', color: '#faad14', unit: 'cps' }
      ]
    },
    {
      title: '网络流量',
      subtitle: '入流量与出流量',
      metric: 'redis_total_net_input_bytes_rate',
      guide: [
        { label: '网络入流量', detail: 'Redis 接收网络数据的速率。' },
        { label: '网络出流量', detail: 'Redis 发送网络数据的速率。' }
      ],
      series: [
        { metric: 'redis_total_net_input_bytes_rate', label: '网络入流量', color: '#2f6bff', unit: 'byteps' },
        { metric: 'redis_total_net_output_bytes_rate', label: '网络出流量', color: '#27c274', unit: 'byteps' }
      ]
    },
    {
      title: '内存碎片',
      subtitle: '碎片率',
      metric: 'redis_mem_fragmentation_ratio',
      guide: [
        { label: '内存碎片率', detail: '操作系统分配内存与 Redis 实际使用内存的比值,>1.5 通常表示碎片严重。' }
      ],
      series: [
        { metric: 'redis_mem_fragmentation_ratio', label: '内存碎片率', color: '#8a5cff', unit: 'none' }
      ]
    }
  ],
  ringPanels: [
    {
      title: '命中分布',
      subtitle: '命中与未命中',
      centerMetric: 'redis_keyspace_hitrate',
      centerCaption: '缓存命中率',
      centerUnit: 'percent',
      guide: [{ label: '命中结构', detail: '对比键空间命中与未命中频率,直观看出缓存有效性。' }],
      segments: [
        { label: '命中', metric: 'redis_keyspace_hits_rate', color: '#27c274', unit: 'cps' },
        { label: '未命中', metric: 'redis_keyspace_misses_rate', color: '#ff4d4f', unit: 'cps' }
      ]
    }
  ],
  barPanels: [
    {
      title: '客户端状态',
      subtitle: '连接、阻塞与拒绝',
      showTrend: true,
      guide: [{ label: '客户端状态', detail: '汇总客户端连接、阻塞等待与连接拒绝。阻塞或拒绝非零即需排查。' }],
      items: [
        { label: '客户端连接', metric: 'redis_clients', color: '#2f6bff', unit: 'counts' },
        { label: '阻塞客户端', metric: 'redis_blocked_clients', color: '#ff8a1f', unit: 'counts' },
        { label: '连接拒绝', metric: 'redis_rejected_connections_rate', color: '#ff4d4f', unit: 'cps' }
      ]
    }
  ],
  // 键生命周期 / 网络流量 / 内存碎片 已改为 charts(折线图),不再用 detail 缩略图。
  details: []
};
