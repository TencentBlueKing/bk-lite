import type { SimpleDashboardConfig } from '../common/simple-dashboard-core';

/** Elasticsearch 监控高对比鲜活科技色板 */
const ES_PALETTE = {
  emerald: '#10B981',   // 集群健康正常、HTTP 新建连接
  blue: '#2563EB',      // 活跃主分片、堆内存、写入队列
  cyan: '#06B6D4',      // 可用磁盘空间
  indigo: '#6366F1',    // HTTP 当前连接、打开文件描述符
  amber: '#F59E0B',     // 请求熔断、集群健康警告
  orange: '#F97316',    // 进程 CPU、Young GC、搜索队列
  rose: '#EF4444'       // 未分配分片、Fielddata 熔断、集群健康严重
} as const;

export const ELASTICSEARCH_DASHBOARD_CONFIG: SimpleDashboardConfig = {
  routeKey: 'elasticsearch',
  pageTitle: 'Elasticsearch 监控仪表盘',
  objectFallbackName: 'Elasticsearch',
  instanceType: 'elasticsearch',
  collectionStatusQuery: "count({instance_type='elasticsearch', collect_type='database', __$labels__}) by (instance_id)",
  metaItems: ['Telegraf', 'database'],
  metrics: [
    {
      name: 'elasticsearch_cluster_health_status_code',
      display_name: '集群健康状态',
      description: '集群健康状态编码，1 正常、2 警告、3 严重。',
      unit: 'counts',
      query: 'elasticsearch_cluster_health_status_code{__$labels__}',
      color: ES_PALETTE.emerald
    },
    {
      name: 'elasticsearch_cluster_health_active_primary_shards',
      display_name: '活跃主分片数',
      description: '集群中活跃主分片数量。',
      unit: 'counts',
      query: 'elasticsearch_cluster_health_active_primary_shards{__$labels__}',
      color: ES_PALETTE.blue
    },
    {
      name: 'elasticsearch_cluster_health_unassigned_shards',
      display_name: '未分配分片数',
      description: '未分配分片数量，非零需排查。',
      unit: 'counts',
      query: 'elasticsearch_cluster_health_unassigned_shards{__$labels__}',
      color: ES_PALETTE.rose
    },
    {
      name: 'elasticsearch_shard_assignment_ratio',
      display_name: '主分片分配率',
      description: '活跃主分片占主分片总数的比例。',
      unit: 'percent',
      query: '100 * elasticsearch_cluster_health_active_primary_shards{__$labels__} / clamp_min(elasticsearch_cluster_health_active_primary_shards{__$labels__} + elasticsearch_cluster_health_unassigned_shards{__$labels__}, 1)',
      color: ES_PALETTE.blue
    },
    {
      name: 'elasticsearch_jvm_mem_heap_used_percent',
      display_name: 'JVM 堆内存使用率',
      description: 'JVM 堆内存使用百分比。',
      unit: 'percent',
      query: 'elasticsearch_jvm_mem_heap_used_percent{__$labels__}',
      color: ES_PALETTE.blue
    },
    {
      name: 'elasticsearch_jvm_gc_collectors_young_collection_time_in_millis_rate',
      display_name: '新生代 GC 耗时速率',
      description: '新生代 GC 每秒累计耗时（ms/s）；升高表示 GC 占用墙钟时间增多。',
      unit: 'ms',
      query: 'rate(elasticsearch_jvm_gc_collectors_young_collection_time_in_millis{__$labels__}[__$window__])',
      color: ES_PALETTE.orange
    },
    {
      name: 'elasticsearch_fs_data_0_available_in_bytes',
      display_name: '节点可用磁盘空间',
      description: '节点数据目录可用磁盘空间。',
      unit: 'bytes',
      query: 'elasticsearch_fs_data_0_available_in_bytes{__$labels__}',
      color: ES_PALETTE.cyan
    },
    {
      name: 'elasticsearch_process_cpu_percent',
      display_name: '进程 CPU 使用率',
      description: 'Elasticsearch 进程 CPU 使用率。',
      unit: 'percent',
      query: 'elasticsearch_process_cpu_percent{__$labels__}',
      color: ES_PALETTE.orange
    },
    {
      name: 'elasticsearch_process_open_file_descriptors',
      display_name: '打开文件描述符数',
      description: '进程已打开文件描述符数量。',
      unit: 'counts',
      query: 'elasticsearch_process_open_file_descriptors{__$labels__}',
      color: ES_PALETTE.indigo
    },
    {
      name: 'elasticsearch_breakers_fielddata_tripped_rate',
      display_name: 'Fielddata 熔断速率',
      description: 'Fielddata 熔断触发速率。',
      unit: 'cps',
      query: 'rate(elasticsearch_breakers_fielddata_tripped{__$labels__}[__$window__])',
      color: ES_PALETTE.rose
    },
    {
      name: 'elasticsearch_breakers_request_tripped_rate',
      display_name: '请求熔断速率',
      description: '请求级熔断触发速率。',
      unit: 'cps',
      query: 'rate(elasticsearch_breakers_request_tripped{__$labels__}[__$window__])',
      color: ES_PALETTE.amber
    },
    {
      name: 'elasticsearch_http_current_open',
      display_name: 'HTTP 当前连接数',
      description: 'HTTP 服务当前打开连接数。',
      unit: 'counts',
      query: 'elasticsearch_http_current_open{__$labels__}',
      color: ES_PALETTE.indigo
    },
    {
      name: 'elasticsearch_http_total_opened_rate',
      display_name: 'HTTP 新建连接速率',
      description: 'HTTP 服务新建连接速率。',
      unit: 'cps',
      query: 'rate(elasticsearch_http_total_opened{__$labels__}[__$window__])',
      color: ES_PALETTE.emerald
    },
    {
      name: 'elasticsearch_thread_pool_write_queue',
      display_name: '写线程池队列',
      description: '写线程池待处理队列长度。',
      unit: 'counts',
      query: 'elasticsearch_thread_pool_write_queue{__$labels__}',
      color: ES_PALETTE.blue
    },
    {
      name: 'elasticsearch_thread_pool_search_queue',
      display_name: '搜索线程池队列',
      description: '搜索线程池待处理队列长度。',
      unit: 'counts',
      query: 'elasticsearch_thread_pool_search_queue{__$labels__}',
      color: ES_PALETTE.orange
    }
  ],
  summaryCards: [
    {
      title: '集群健康状态',
      metric: 'elasticsearch_cluster_health_status_code',
      formatter: 'enumHealth',
      color: ES_PALETTE.emerald,
      icon: 'node',
      guide: [{ label: '健康状态', detail: '集群健康编码:1 绿(正常)、2 黄(副本未分配)、3 红(主分片缺失)。非 1 时查未分配分片与节点状态。' }],
      footer: [
        { label: '未分配分片', metric: 'elasticsearch_cluster_health_unassigned_shards', unit: 'counts' },
        { label: '状态编码', metric: 'elasticsearch_cluster_health_status_code', formatter: 'enumHealth' }
      ]
    },
    {
      title: 'JVM 堆使用率',
      metric: 'elasticsearch_jvm_mem_heap_used_percent',
      color: ES_PALETTE.blue,
      icon: 'database',
      compare: true,
      guide: [{ label: 'JVM 堆', detail: 'JVM 堆内存使用率，持续高值会增加 GC 压力。' }],
      footer: [{ label: 'Young GC', metric: 'elasticsearch_jvm_gc_collectors_young_collection_time_in_millis_rate', unit: 'ms' }]
    },
    {
      title: '进程 CPU',
      metric: 'elasticsearch_process_cpu_percent',
      color: ES_PALETTE.orange,
      icon: 'api',
      compare: true,
      guide: [{ label: '进程 CPU', detail: 'Elasticsearch 进程 CPU 使用率，高负载会影响读写性能。' }],
      footer: [{ label: '打开文件', metric: 'elasticsearch_process_open_file_descriptors', unit: 'counts' }]
    },
    {
      title: '节点可用磁盘',
      metric: 'elasticsearch_fs_data_0_available_in_bytes',
      color: ES_PALETTE.cyan,
      icon: 'database',
      guide: [{ label: '可用磁盘', detail: '节点数据目录可用磁盘空间，空间不足会触发分片迁移或写入保护。' }],
      footer: [{ label: '主分片', metric: 'elasticsearch_cluster_health_active_primary_shards', unit: 'counts' }]
    },
    {
      title: '未分配分片',
      metric: 'elasticsearch_cluster_health_unassigned_shards',
      color: ES_PALETTE.rose,
      icon: 'thunder',
      guide: [{ label: '未分配分片', detail: '未能分配到节点的分片数(个);非零会降低冗余 / 可用性。排查节点掉线、磁盘水位或分配规则。' }],
      footer: [{ label: '健康状态', metric: 'elasticsearch_cluster_health_status_code', unit: 'counts' }]
    },
    {
      title: '主分片分配率',
      metric: 'elasticsearch_shard_assignment_ratio',
      color: ES_PALETTE.blue,
      icon: 'database',
      compare: true,
      compareFavorableDirection: 'up',
      guide: [{ label: '分配率', detail: '活跃主分片占主分片总数的比例，低于 100% 时说明仍有分片未恢复。' }],
      footer: [{ label: '未分配分片', metric: 'elasticsearch_cluster_health_unassigned_shards', unit: 'counts' }]
    },
    {
      title: 'HTTP 当前连接',
      metric: 'elasticsearch_http_current_open',
      color: ES_PALETTE.indigo,
      icon: 'node',
      guide: [{ label: 'HTTP 连接', detail: 'HTTP 服务当前打开连接数。' }],
      footer: [{ label: '新建速率', metric: 'elasticsearch_http_total_opened_rate', unit: 'cps' }]
    }
  ],
  charts: [
    {
      title: '资源使用率',
      subtitle: '堆内存与 CPU',
      metric: 'elasticsearch_jvm_mem_heap_used_percent',
      guide: [
        { label: 'JVM 堆', detail: 'JVM 堆内存使用百分比。' },
        { label: '进程 CPU', detail: 'Elasticsearch 进程 CPU 使用率。' }
      ],
      series: [
        { metric: 'elasticsearch_jvm_mem_heap_used_percent', label: 'JVM 堆使用率', color: ES_PALETTE.blue, unit: 'percent' },
        { metric: 'elasticsearch_process_cpu_percent', label: '进程 CPU', color: ES_PALETTE.orange, unit: 'percent' }
      ]
    },
    {
      title: 'GC 耗时速率趋势',
      subtitle: 'Young GC',
      metric: 'elasticsearch_jvm_gc_collectors_young_collection_time_in_millis_rate',
      guide: [{ label: 'GC 耗时', detail: '新生代 GC 每秒累计耗时。' }],
      series: [
        { metric: 'elasticsearch_jvm_gc_collectors_young_collection_time_in_millis_rate', label: 'Young GC 耗时', color: ES_PALETTE.orange, unit: 'ms' }
      ]
    },
    {
      title: '线程池队列',
      subtitle: '写入与搜索队列',
      metric: 'elasticsearch_thread_pool_write_queue',
      guide: [{ label: '线程池队列', detail: '写入与搜索线程池待处理队列长度。' }],
      series: [
        { metric: 'elasticsearch_thread_pool_write_queue', label: '写入队列', color: ES_PALETTE.blue, unit: 'counts' },
        { metric: 'elasticsearch_thread_pool_search_queue', label: '搜索队列', color: ES_PALETTE.orange, unit: 'counts' }
      ]
    },
    {
      title: 'HTTP 新建连接',
      subtitle: '新建连接速率',
      metric: 'elasticsearch_http_total_opened_rate',
      guide: [{ label: '新建连接', detail: 'HTTP 服务新建连接速率。' }],
      series: [
        { metric: 'elasticsearch_http_total_opened_rate', label: '新建速率', color: ES_PALETTE.emerald, unit: 'cps' }
      ]
    },
    {
      title: '熔断器触发',
      subtitle: '熔断触发',
      metric: 'elasticsearch_breakers_fielddata_tripped_rate',
      guide: [
        { label: 'Fielddata', detail: 'Fielddata 内存保护熔断触发速率。' },
        { label: '请求熔断', detail: '请求级内存保护熔断触发速率。' }
      ],
      series: [
        { metric: 'elasticsearch_breakers_fielddata_tripped_rate', label: 'Fielddata 熔断', color: ES_PALETTE.rose, unit: 'cps' },
        { metric: 'elasticsearch_breakers_request_tripped_rate', label: '请求熔断', color: ES_PALETTE.amber, unit: 'cps' }
      ]
    }
  ],
  ringPanels: [],
  barPanels: [],
  details: []
};
