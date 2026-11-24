/** 「节点压力排行」TopN 节点数量;单一常量同时驱动 topk / bottomk 查询与展示。 */
export const ES_TOP_N = 8;

interface GuideItem { label: string; detail: string }

export interface EsTopNodeQuery {
  /** 用作 React key 与 state 键 */
  key: string;
  title: string;
  /** formatMetricValue 用的单位 */
  unit: string;
  color: string;
  /** 按 node_name 聚合 + topk/bottomk 的查询;__$labels__ 由 buildSearchParams 注入实例过滤 */
  query: string;
  guide: GuideItem[];
}

// node_name 是 ES 唯一贯穿节点级指标(JVM/CPU/磁盘/熔断/HTTP/线程池)的自由维度。
// 选 JVM 堆使用率、进程 CPU(topk 取热点)与节点可用磁盘(bottomk 取最紧张节点)三项定位瓶颈节点。
export const ES_TOP_NODE_QUERIES: EsTopNodeQuery[] = [
  {
    key: 'jvm_heap',
    title: 'JVM 堆使用率 Top',
    unit: 'percent',
    color: '#2563EB',
    query: `topk(${ES_TOP_N}, max by (node_name) (elasticsearch_jvm_mem_heap_used_percent{__$labels__}))`,
    guide: [{ label: 'JVM 堆排行', detail: '各节点 JVM 堆内存使用率,定位 GC 压力集中的节点。' }]
  },
  {
    key: 'process_cpu',
    title: '进程 CPU Top',
    unit: 'percent',
    color: '#F97316',
    query: `topk(${ES_TOP_N}, max by (node_name) (elasticsearch_process_cpu_percent{__$labels__}))`,
    guide: [{ label: '进程 CPU 排行', detail: '各节点 ES 进程 CPU 使用率,定位计算负载集中的节点。' }]
  },
  {
    key: 'fs_available',
    title: '节点可用磁盘 Bottom',
    unit: 'bytes',
    color: '#EF4444',
    query: `bottomk(${ES_TOP_N}, min by (node_name) (elasticsearch_fs_data_0_available_in_bytes{__$labels__}))`,
    guide: [{ label: '磁盘紧张排行', detail: '各节点数据目录可用磁盘空间(取最小),定位磁盘水位紧张的节点。' }]
  }
];

/** 已发布原始序列。专业盘的源时间、能力探测和即时读数都打在这些名字上。 */
export const ES_RAW_METRIC = {
  health: 'elasticsearch_cluster_health_status_code',
  primary: 'elasticsearch_cluster_health_active_primary_shards',
  unassigned: 'elasticsearch_cluster_health_unassigned_shards',
  heap: 'elasticsearch_jvm_mem_heap_used_percent',
  cpu: 'elasticsearch_process_cpu_percent',
  disk: 'elasticsearch_fs_data_0_available_in_bytes',
  fd: 'elasticsearch_process_open_file_descriptors',
  deleted: 'elasticsearch_indices_docs_deleted',
  write: 'elasticsearch_fs_io_stats_total_write_kilobytes',
  gc: 'elasticsearch_jvm_gc_collectors_young_collection_time_in_millis',
  httpOpen: 'elasticsearch_http_current_open',
  httpOpened: 'elasticsearch_http_total_opened',
  writeQueue: 'elasticsearch_thread_pool_write_queue',
  searchQueue: 'elasticsearch_thread_pool_search_queue',
  breakerField: 'elasticsearch_breakers_fielddata_tripped',
  breakerRequest: 'elasticsearch_breakers_request_tripped',
  breakerParent: 'elasticsearch_breakers_parent_tripped'
} as const;

export type EsMetricId = keyof typeof ES_RAW_METRIC;

/** 有瞬时原值的序列。速率卡的当前值来自窗口趋势，不另做 last_over_time。 */
export const ES_GAUGE_METRIC_IDS = [
  'health',
  'primary',
  'unassigned',
  'heap',
  'cpu',
  'disk',
  'fd',
  'deleted',
  'httpOpen',
  'writeQueue',
  'searchQueue'
] as const satisfies readonly EsMetricId[];

const sourceTimeQuery = (metric: string) => `tlast_over_time(${metric}{__$labels__}[20m])`;
const capabilityQuery = (metric: string) => `tlast_over_time(${metric}{__$labels__}[24h])`;
const gaugeQuery = (metric: string) => `last_over_time(${metric}{__$labels__}[20m])`;

const instantQueries = () => {
  const queries: Record<string, string> = {};
  (Object.keys(ES_RAW_METRIC) as EsMetricId[]).forEach((id) => {
    const metric = ES_RAW_METRIC[id];
    queries[`src:${id}`] = sourceTimeQuery(metric);
    queries[`cap:${id}`] = capabilityQuery(metric);
  });
  ES_GAUGE_METRIC_IDS.forEach((id) => {
    queries[`val:${id}`] = gaugeQuery(ES_RAW_METRIC[id]);
  });
  return queries;
};

/** 20 分钟源时间、24 小时能力、仪表原值。窗口写在原始选择器上。 */
export const ES_INSTANT_QUERIES: Record<string, string> = instantQueries();

/** 趋势。时间窗只替换 __$window__，不拿来判断采集新鲜度。 */
export const ES_RANGE_QUERIES = {
  heapNodes: 'topk(8, max by (node_name) (elasticsearch_jvm_mem_heap_used_percent{__$labels__}))',
  cpuNodes: 'topk(8, max by (node_name) (elasticsearch_process_cpu_percent{__$labels__}))',
  diskNodes: 'bottomk(8, min by (node_name) (elasticsearch_fs_data_0_available_in_bytes{__$labels__}))',
  fdNodes: 'topk(8, max by (node_name) (elasticsearch_process_open_file_descriptors{__$labels__}))',
  writeNodes: 'topk(8, max by (node_name) (rate(elasticsearch_fs_io_stats_total_write_kilobytes{__$labels__}[__$window__]) * 1024))',
  deletedNodes: 'topk(8, max by (node_name) (elasticsearch_indices_docs_deleted{__$labels__}))',
  gcNodes: 'topk(8, max by (node_name) (rate(elasticsearch_jvm_gc_collectors_young_collection_time_in_millis{__$labels__}[__$window__])))',
  writeQueueAgg: 'max by (instance_id) (elasticsearch_thread_pool_write_queue{__$labels__})',
  searchQueueAgg: 'max by (instance_id) (elasticsearch_thread_pool_search_queue{__$labels__})',
  writeQueueNodes: 'topk(8, max by (node_name) (elasticsearch_thread_pool_write_queue{__$labels__}))',
  searchQueueNodes: 'topk(8, max by (node_name) (elasticsearch_thread_pool_search_queue{__$labels__}))',
  httpOpenAgg: 'sum by (instance_id) (elasticsearch_http_current_open{__$labels__})',
  httpRateAgg: 'sum by (instance_id) (rate(elasticsearch_http_total_opened{__$labels__}[__$window__]))',
  breakerField: 'sum by (instance_id) (rate(elasticsearch_breakers_fielddata_tripped{__$labels__}[__$window__]))',
  breakerRequest: 'sum by (instance_id) (rate(elasticsearch_breakers_request_tripped{__$labels__}[__$window__]))',
  breakerParent: 'sum by (instance_id) (rate(elasticsearch_breakers_parent_tripped{__$labels__}[__$window__]))'
} as const;

export type EsRangeQueryId = keyof typeof ES_RANGE_QUERIES;
