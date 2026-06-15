/** 「节点压力排行」TopN 节点数量;单一常量同时驱动 topk / bottomk 查询与展示。 */
export const ES_TOP_N = 8;

type GuideItem = { label: string; detail: string };

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
    color: '#2f6bff',
    query: `topk(${ES_TOP_N}, max by (node_name) (elasticsearch_jvm_mem_heap_used_percent{__$labels__}))`,
    guide: [{ label: 'JVM 堆排行', detail: '各节点 JVM 堆内存使用率,定位 GC 压力集中的节点。' }]
  },
  {
    key: 'process_cpu',
    title: '进程 CPU Top',
    unit: 'percent',
    color: '#ff8a1f',
    query: `topk(${ES_TOP_N}, max by (node_name) (elasticsearch_process_cpu_percent{__$labels__}))`,
    guide: [{ label: '进程 CPU 排行', detail: '各节点 ES 进程 CPU 使用率,定位计算负载集中的节点。' }]
  },
  {
    key: 'fs_available',
    title: '节点可用磁盘 Bottom',
    unit: 'bytes',
    color: '#ff4d4f',
    query: `bottomk(${ES_TOP_N}, min by (node_name) (elasticsearch_fs_data_0_available_in_bytes{__$labels__}))`,
    guide: [{ label: '磁盘紧张排行', detail: '各节点数据目录可用磁盘空间(取最小),定位磁盘水位紧张的节点。' }]
  }
];
