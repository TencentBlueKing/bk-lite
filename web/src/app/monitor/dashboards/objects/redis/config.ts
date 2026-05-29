import { RedisMetricConfig, TrendLegendItem } from './types';

export const REDIS_COLLECTION_STATUS_QUERY = "count({instance_type='redis', collect_type='database', __$labels__}) by (instance_id)";

export const DASHBOARD_METRICS: RedisMetricConfig[] = [
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
    name: 'redis_memory_utilization',
    display_name: '内存使用率',
    description: '当前内存使用量占配置上限的比例。',
    unit: 'percent',
    query: '100 * max by (instance_id) (redis_used_memory{__$labels__}) / on(instance_id) clamp_min(max by (instance_id) (redis_maxmemory{__$labels__}), 1)',
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
];

export const DEFAULT_METRIC_COLORS = ['#2f6bff', '#27c274', '#ff8a1f', '#ff4d4f', '#8a5cff', '#13c2c2', '#faad14', '#597ef7'];

export const DASHBOARD_METRIC_MAP = new Map(DASHBOARD_METRICS.map((metric) => [metric.name, metric]));

export const DASHBOARD_FALLBACK_GROUPS: Record<string, string> = {
  redis_uptime: 'Base',
  redis_used_memory: 'Memory',
  redis_maxmemory: 'Memory',
  redis_memory_utilization: 'Memory',
  redis_mem_fragmentation_ratio: 'Memory',
  redis_instantaneous_ops_per_sec: 'Performance',
  redis_total_commands_processed_rate: 'Performance',
  redis_keyspace_hits_rate: 'Performance',
  redis_keyspace_misses_rate: 'Performance',
  redis_keyspace_hitrate: 'Performance',
  redis_total_net_input_bytes_rate: 'Network',
  redis_total_net_output_bytes_rate: 'Network',
  redis_clients: 'Client',
  redis_blocked_clients: 'Client',
  redis_expired_keys_rate: 'Error',
  redis_evicted_keys_rate: 'Error',
  redis_rejected_connections_rate: 'Error'
};

export const TREND_LEGENDS: Record<string, TrendLegendItem[]> = {
  ops: [
    { label: '实时 OPS', color: '#27c274', primary: true },
    { label: '命令处理速率', color: '#13c2c2' }
  ],
  cache: [
    { label: '键命中频率', color: '#2f6bff', primary: true },
    { label: '键未命中频率', color: '#ff4d4f' }
  ],
  memory: [
    { label: '已用内存', color: '#2f6bff', primary: true },
    { label: '内存上限', color: '#9aa9bf', dashed: true }
  ],
  network: [
    { label: '入流量', color: '#2f6bff', primary: true },
    { label: '出流量', color: '#27c274' }
  ]
};
