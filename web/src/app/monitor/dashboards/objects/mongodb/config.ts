import { MongoMetricConfig, TrendLegendItem } from './types';

export const MONGODB_COLLECTION_STATUS_QUERY =
  "count({instance_type='mongodb', collect_type='database', __$labels__}) by (instance_id)";

export const DASHBOARD_METRICS: MongoMetricConfig[] = [
  {
    name: 'mongodb_uptime_ns',
    display_name: '运行时长',
    description: 'MongoDB 实例自上次启动后的持续运行时间。',
    unit: 'ns',
    query: 'mongodb_uptime_ns{__$labels__}',
    color: '#5b8ff9'
  },
  {
    name: 'mongodb_connections_current',
    display_name: '当前连接数',
    description: '当前活跃客户端连接数量。',
    unit: 'counts',
    query: 'mongodb_connections_current{__$labels__}',
    color: '#2f6bff'
  },
  {
    name: 'mongodb_connections_available',
    display_name: '可用连接数',
    description: '当前仍可使用的连接槽位数量。',
    unit: 'counts',
    query: 'mongodb_connections_available{__$labels__}',
    color: '#9aa9bf'
  },
  {
    name: 'mongodb_open_connections',
    display_name: '打开连接数',
    description: '当前打开连接总数，包括活跃和空闲连接。',
    unit: 'counts',
    query: 'mongodb_open_connections{__$labels__}',
    color: '#13c2c2'
  },
  {
    name: 'mongodb_commands_rate',
    display_name: '命令吞吐',
    description: 'MongoDB 每秒处理命令的速率。',
    unit: 'cps',
    query: 'rate(mongodb_commands{__$labels__}[5m])',
    color: '#2f6bff'
  },
  {
    name: 'mongodb_queries_rate',
    display_name: '查询吞吐',
    description: 'MongoDB 每秒查询请求的速率。',
    unit: 'cps',
    query: 'rate(mongodb_queries{__$labels__}[5m])',
    color: '#13c2c2'
  },
  {
    name: 'mongodb_write_ops_rate',
    display_name: '写入吞吐',
    description: 'MongoDB 每秒插入、更新、删除操作的总速率。',
    unit: 'cps',
    query:
      'rate(mongodb_inserts{__$labels__}[5m]) + rate(mongodb_updates{__$labels__}[5m]) + rate(mongodb_deletes{__$labels__}[5m])',
    color: '#ff9f43'
  },
  {
    name: 'mongodb_latency_reads_avg',
    display_name: '读延迟',
    description: 'MongoDB 读请求的平均响应延迟。',
    unit: 'ns',
    query: 'mongodb_latency_reads{__$labels__}/clamp_min(mongodb_latency_reads_count{__$labels__}, 1)',
    color: '#27c274'
  },
  {
    name: 'mongodb_latency_commands_avg',
    display_name: '命令延迟',
    description: 'MongoDB 命令请求的平均响应延迟。',
    unit: 'ns',
    query: 'mongodb_latency_commands{__$labels__}/clamp_min(mongodb_latency_commands_count{__$labels__}, 1)',
    color: '#faad14'
  },
  {
    name: 'mongodb_page_faults_rate',
    display_name: '缺页频率',
    description: '缺页中断的发生速率，通常反映内存压力或工作集不匹配。',
    unit: 'cps',
    query: 'rate(mongodb_page_faults{__$labels__}[5m])',
    color: '#ff4d4f'
  },
  {
    name: 'mongodb_active_reads',
    display_name: '活跃读操作',
    description: '当前正在执行的读操作数量。',
    unit: 'counts',
    query: 'mongodb_active_reads{__$labels__}',
    color: '#2f6bff'
  },
  {
    name: 'mongodb_active_writes',
    display_name: '活跃写操作',
    description: '当前正在执行的写操作数量。',
    unit: 'counts',
    query: 'mongodb_active_writes{__$labels__}',
    color: '#27c274'
  },
  {
    name: 'mongodb_queued_reads',
    display_name: '排队读操作',
    description: '当前等待执行的读操作数量。',
    unit: 'counts',
    query: 'mongodb_queued_reads{__$labels__}',
    color: '#5b8ff9'
  },
  {
    name: 'mongodb_queued_writes',
    display_name: '排队写操作',
    description: '当前等待执行的写操作数量。',
    unit: 'counts',
    query: 'mongodb_queued_writes{__$labels__}',
    color: '#ff9f43'
  },
  {
    name: 'mongodb_resident_megabytes',
    display_name: '常驻内存',
    description: 'MongoDB 进程实际驻留在物理内存中的大小。',
    unit: 'mebibytes',
    query: 'mongodb_resident_megabytes{__$labels__}',
    color: '#2f6bff'
  },
  {
    name: 'mongodb_vsize_megabytes',
    display_name: '虚拟内存',
    description: 'MongoDB 进程申请的虚拟内存空间大小。',
    unit: 'mebibytes',
    query: 'mongodb_vsize_megabytes{__$labels__}',
    color: '#9aa9bf'
  },
  {
    name: 'mongodb_tcmalloc_current_allocated_bytes',
    display_name: '已分配内存',
    description: '当前由 tcmalloc 分配并仍在使用的内存。',
    unit: 'bytes',
    query: 'mongodb_tcmalloc_current_allocated_bytes{__$labels__}',
    color: '#13c2c2'
  },
  {
    name: 'mongodb_wtcache_current_bytes',
    display_name: '缓存已用',
    description: 'WiredTiger 当前已占用的缓存大小。',
    unit: 'bytes',
    query: 'mongodb_wtcache_current_bytes{__$labels__}',
    color: '#2f6bff'
  },
  {
    name: 'mongodb_wtcache_max_bytes_configured',
    display_name: '缓存上限',
    description: 'WiredTiger 配置的缓存容量上限。',
    unit: 'bytes',
    query: 'mongodb_wtcache_max_bytes_configured{__$labels__}',
    color: '#9aa9bf'
  },
  {
    name: 'mongodb_wtcache_tracked_dirty_bytes',
    display_name: '脏数据',
    description: 'WiredTiger 缓存中已修改但尚未落盘的数据量。',
    unit: 'bytes',
    query: 'mongodb_wtcache_tracked_dirty_bytes{__$labels__}',
    color: '#ff9f43'
  },
  {
    name: 'mongodb_wtcache_usage_ratio',
    display_name: '缓存使用率',
    description: 'WiredTiger 已用缓存占配置上限的比例。',
    unit: 'percent',
    query:
      '100 * max by (instance_id) (mongodb_wtcache_current_bytes{__$labels__}) / on(instance_id) clamp_min(max by (instance_id) (mongodb_wtcache_max_bytes_configured{__$labels__}), 1)',
    color: '#2f6bff'
  },
  {
    name: 'mongodb_wtcache_dirty_ratio',
    display_name: '脏数据占比',
    description: 'WiredTiger 脏数据占当前缓存的比例。',
    unit: 'percent',
    query:
      '100 * max by (instance_id) (mongodb_wtcache_tracked_dirty_bytes{__$labels__}) / on(instance_id) clamp_min(max by (instance_id) (mongodb_wtcache_current_bytes{__$labels__}), 1)',
    color: '#ff9f43'
  },
  {
    name: 'mongodb_net_in_bytes_count_rate',
    display_name: '网络入流量',
    description: 'MongoDB 接收网络数据的速率。',
    unit: 'byteps',
    query: 'rate(mongodb_net_in_bytes_count{__$labels__}[5m])',
    color: '#2f6bff'
  },
  {
    name: 'mongodb_net_out_bytes_count_rate',
    display_name: '网络出流量',
    description: 'MongoDB 返回网络数据的速率。',
    unit: 'byteps',
    query: 'rate(mongodb_net_out_bytes_count{__$labels__}[5m])',
    color: '#27c274'
  },
  {
    name: 'mongodb_cursor_timed_out_count',
    display_name: '游标超时数',
    description: '累计游标超时数量，用于观察长查询或游标管理问题。',
    unit: 'counts',
    query: 'mongodb_cursor_timed_out_count{__$labels__}',
    color: '#faad14'
  },
  {
    name: 'mongodb_assert_user',
    display_name: '用户断言',
    description: '累计用户断言数量，用于发现应用逻辑或数据异常信号。',
    unit: 'counts',
    query: 'mongodb_assert_user{__$labels__}',
    color: '#ff4d4f'
  }
];

export const DEFAULT_METRIC_COLORS = [
  '#2f6bff',
  '#27c274',
  '#ff9f43',
  '#ff4d4f',
  '#13c2c2',
  '#5b8ff9',
  '#9aa9bf',
  '#faad14'
];

export const TREND_LEGENDS: Record<string, TrendLegendItem[]> = {
  throughput: [
    { label: '命令吞吐', color: '#2f6bff', primary: true },
    { label: '查询吞吐', color: '#13c2c2' },
    { label: '写入吞吐', color: '#ff9f43' }
  ],
  latency: [
    { label: '读延迟', color: '#27c274', primary: true },
    { label: '命令延迟', color: '#faad14' }
  ],
  queue: [
    { label: '活跃读', color: '#2f6bff', primary: true },
    { label: '活跃写', color: '#27c274' },
    { label: '排队读', color: '#5b8ff9' },
    { label: '排队写', color: '#ff9f43' }
  ],
  cache: [
    { label: '缓存已用', color: '#2f6bff', primary: true },
    { label: '缓存上限', color: '#9aa9bf', dashed: true }
  ],
  memory: [
    { label: '常驻内存', color: '#27c274', primary: true },
    { label: '虚拟内存', color: '#9aa9bf' }
  ],
  network: [
    { label: '入流量', color: '#2f6bff', primary: true },
    { label: '出流量', color: '#27c274' }
  ]
};
