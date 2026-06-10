import type { SimpleDashboardConfig } from '../common/simple-dashboard-core';

export const TOMCAT_DASHBOARD_CONFIG: SimpleDashboardConfig = {
  routeKey: 'tomcat',
  pageTitle: 'Tomcat 监控仪表盘',
  objectFallbackName: 'Tomcat',
  instanceType: 'tomcat',
  collectionStatusQuery: "count({instance_type='tomcat', collect_type='middleware', __$labels__}) by (instance_id)",
  metaItems: ['Telegraf', 'middleware'],
  metrics: [
    // ── Raw metrics ──
    {
      name: 'tomcat_connector_request_count',
      display_name: '请求处理总量',
      description: 'Tomcat Connector 累计处理请求数量。',
      unit: 'counts',
      query: 'tomcat_connector_request_count{__$labels__}',
      color: '#2f6bff'
    },
    {
      name: 'tomcat_connector_error_count',
      display_name: '错误请求总量',
      description: 'Tomcat Connector 累计错误请求数量。',
      unit: 'counts',
      query: 'tomcat_connector_error_count{__$labels__}',
      color: '#ff4d4f'
    },
    {
      name: 'tomcat_connector_bytes_received',
      display_name: '接收字节总量',
      description: 'Tomcat Connector 累计接收字节数。',
      unit: 'bytes',
      query: 'tomcat_connector_bytes_received{__$labels__}',
      color: '#13c2c2'
    },
    {
      name: 'tomcat_connector_bytes_sent',
      display_name: '发送字节总量',
      description: 'Tomcat Connector 累计发送字节数。',
      unit: 'bytes',
      query: 'tomcat_connector_bytes_sent{__$labels__}',
      color: '#27c274'
    },
    {
      name: 'tomcat_connector_processing_time',
      display_name: '累计处理耗时',
      description: 'Tomcat Connector 累计请求处理耗时。',
      unit: 'ms',
      query: 'tomcat_connector_processing_time{__$labels__}',
      color: '#8a5cff'
    },
    {
      name: 'tomcat_connector_max_time',
      display_name: '最大处理耗时',
      description: 'Tomcat Connector 单次请求最大处理耗时。',
      unit: 'ms',
      query: 'tomcat_connector_max_time{__$labels__}',
      color: '#722ed1'
    },
    {
      name: 'tomcat_connector_current_thread_count',
      display_name: '当前线程数',
      description: 'Tomcat Connector 当前线程数量。',
      unit: 'counts',
      query: 'tomcat_connector_current_thread_count{__$labels__}',
      color: '#2f6bff'
    },
    {
      name: 'tomcat_connector_current_threads_busy',
      display_name: '忙碌线程数',
      description: 'Tomcat Connector 当前忙碌线程数量。',
      unit: 'counts',
      query: 'tomcat_connector_current_threads_busy{__$labels__}',
      color: '#ff8a1f'
    },
    {
      name: 'tomcat_connector_max_threads',
      display_name: '最大线程数',
      description: 'Tomcat Connector 最大线程数量。',
      unit: 'counts',
      query: 'tomcat_connector_max_threads{__$labels__}',
      color: '#9aa9bf'
    },
    {
      name: 'tomcat_jvm_memory_free',
      display_name: 'JVM 空闲内存',
      description: 'Tomcat JVM 当前空闲内存大小。',
      unit: 'bytes',
      query: 'tomcat_jvm_memory_free{__$labels__}',
      color: '#27c274'
    },
    {
      name: 'tomcat_jvm_memory_total',
      display_name: 'JVM 已分配内存',
      description: 'Tomcat JVM 当前已分配内存大小。',
      unit: 'bytes',
      query: 'tomcat_jvm_memory_total{__$labels__}',
      color: '#2f6bff'
    },
    {
      name: 'tomcat_jvm_memory_max',
      display_name: 'JVM 最大内存',
      description: 'Tomcat JVM 最大可用内存。',
      unit: 'bytes',
      query: 'tomcat_jvm_memory_max{__$labels__}',
      color: '#9aa9bf'
    },
    {
      name: 'tomcat_jvm_memorypool_used',
      display_name: 'MemoryPool 已用',
      description: 'Tomcat JVM MemoryPool 已用内存。',
      unit: 'bytes',
      query: 'tomcat_jvm_memorypool_used{__$labels__}',
      color: '#8a5cff'
    },
    {
      name: 'tomcat_jvm_memorypool_committed',
      display_name: 'MemoryPool 已提交',
      description: 'Tomcat JVM MemoryPool 已提交内存。',
      unit: 'bytes',
      query: 'tomcat_jvm_memorypool_committed{__$labels__}',
      color: '#2f6bff'
    },
    {
      name: 'tomcat_jvm_memorypool_max',
      display_name: 'MemoryPool 最大',
      description: 'Tomcat JVM MemoryPool 最大内存。',
      unit: 'bytes',
      query: 'tomcat_jvm_memorypool_max{__$labels__}',
      color: '#9aa9bf'
    },
    {
      name: 'tomcat_connector_request_count_rate',
      display_name: '请求处理速率',
      description: 'Tomcat Connector 请求处理速率。',
      unit: 'cps',
      query: 'rate(tomcat_connector_request_count{__$labels__}[5m])',
      color: '#2f6bff'
    },
    {
      name: 'tomcat_connector_error_count_rate',
      display_name: '错误请求速率',
      description: 'Tomcat Connector 错误请求速率。',
      unit: 'cps',
      query: 'rate(tomcat_connector_error_count{__$labels__}[5m])',
      color: '#ff4d4f'
    },
    {
      name: 'tomcat_connector_bytes_sent_rate',
      display_name: '数据发送速率',
      description: 'Tomcat Connector 数据发送速率。',
      unit: 'byteps',
      query: 'rate(tomcat_connector_bytes_sent{__$labels__}[5m])',
      color: '#27c274'
    },
    {
      name: 'tomcat_connector_current_thread_utilization',
      display_name: '线程池利用率',
      description: 'Tomcat Connector 线程池利用率（忙碌线程 / 最大线程 × 100）。',
      unit: 'percent',
      query: 'tomcat_connector_current_threads_busy{__$labels__} / clamp_min(tomcat_connector_max_threads{__$labels__}, 1) * 100',
      color: '#ff8a1f'
    },
    // ── Derived metrics ──
    {
      name: 'tomcat_connector_current_threads_free',
      display_name: '空闲线程数',
      description: '由最大线程数和忙碌线程数推导出的可用线程数量。',
      unit: 'counts',
      query: 'clamp_min(tomcat_connector_max_threads{__$labels__} - tomcat_connector_current_threads_busy{__$labels__}, 0)',
      color: '#27c274'
    },
    {
      name: 'tomcat_jvm_heap_used_pct',
      display_name: 'JVM 堆使用率',
      description: '由已分配内存、空闲内存和最大内存推导出的 JVM 堆使用率（(total - free) / max × 100）。',
      unit: 'percent',
      query: 'clamp_max(100 * ((tomcat_jvm_memory_total{__$labels__} - tomcat_jvm_memory_free{__$labels__}) / clamp_min(tomcat_jvm_memory_max{__$labels__}, 1)), 100)',
      color: '#8a5cff'
    },
    {
      name: 'tomcat_connector_error_rate_pct',
      display_name: '错误请求占比',
      description: '由错误请求速率与总请求速率推导出的错误占比（error_rate / request_rate × 100）。',
      unit: 'percent',
      query: '100 * (rate(tomcat_connector_error_count{__$labels__}[5m]) / clamp_min(rate(tomcat_connector_request_count{__$labels__}[5m]), 1))',
      color: '#faad14'
    }
  ],
  summaryCards: [
    {
      title: '线程池利用率',
      metric: 'tomcat_connector_current_thread_utilization',
      unit: 'percent',
      color: '#ff8a1f',
      icon: 'node',
      compare: true,
      compareFavorableDirection: 'down',
      guide: [{ label: '线程池利用率', detail: '忙碌线程相对线程池容量的比例，持续逼近 100% 说明线程池面临饱和风险，需扩容或限流。' }],
      footer: [
        { label: '忙碌线程', metric: 'tomcat_connector_current_threads_busy', unit: 'counts' },
        { label: '最大线程', metric: 'tomcat_connector_max_threads', unit: 'counts' }
      ]
    },
    {
      title: '错误占比',
      metric: 'tomcat_connector_error_rate_pct',
      unit: 'percent',
      color: '#ff4d4f',
      icon: 'api',
      compare: true,
      compareFavorableDirection: 'down',
      guide: [{ label: '错误占比', detail: '错误请求数占总请求数的百分比;持续偏高需排查接口报错与下游依赖。' }],
      footer: [
        { label: '错误速率', metric: 'tomcat_connector_error_count_rate', unit: 'cps' }
      ]
    },
    {
      title: '请求处理速率',
      metric: 'tomcat_connector_request_count_rate',
      unit: 'cps',
      color: '#2f6bff',
      icon: 'thunder',
      guide: [{ label: '请求处理速率', detail: 'Tomcat 每秒处理请求数量，反映实时业务吞吐，结合错误速率判断服务健康度。' }],
      footer: [{ label: '错误速率', metric: 'tomcat_connector_error_count_rate', unit: 'cps' }]
    },
    {
      title: 'JVM 堆使用率',
      metric: 'tomcat_jvm_heap_used_pct',
      unit: 'percent',
      color: '#8a5cff',
      icon: 'memory',
      compare: true,
      compareFavorableDirection: 'down',
      guide: [{ label: 'JVM 堆使用率', detail: 'JVM 堆已用内存占最大堆大小的比例，逼近 100% 时触发 GC 频繁或 OOM，需扩容堆或排查内存泄漏。' }],
      footer: [
        { label: '空闲内存', metric: 'tomcat_jvm_memory_free', unit: 'bytes' }
      ]
    },
    {
      title: '最大处理耗时',
      metric: 'tomcat_connector_max_time',
      unit: 'ms',
      color: '#722ed1',
      icon: 'clock',
      compare: true,
      compareFavorableDirection: 'down',
      guide: [{ label: '最大处理耗时', detail: '单次请求最大处理耗时，反映极端慢请求表现，持续偏高需排查慢接口或下游依赖。' }],
      footer: [
        { label: '请求速率', metric: 'tomcat_connector_request_count_rate', unit: 'cps' }
      ]
    }
  ],
  charts: [
    {
      title: '请求错误趋势',
      subtitle: '请求速率、错误速率',
      metric: 'tomcat_connector_request_count_rate',
      guide: [{ label: '请求错误', detail: '对比请求处理速率与错误请求速率（均为每秒次数），识别可靠性波动。' }],
      series: [
        { metric: 'tomcat_connector_request_count_rate', label: '请求速率', color: '#2f6bff', unit: 'cps' },
        { metric: 'tomcat_connector_error_count_rate', label: '错误速率', color: '#ff4d4f', unit: 'cps' }
      ]
    },
    {
      title: '线程池趋势',
      subtitle: '当前、忙碌、最大',
      metric: 'tomcat_connector_current_thread_count',
      guide: [{ label: '线程池', detail: '对比当前线程、忙碌线程和最大线程数，判断线程池容量压力。忙碌线程持续逼近最大线程数说明线程池趋于饱和。' }],
      series: [
        { metric: 'tomcat_connector_current_thread_count', label: '当前线程', color: '#2f6bff', unit: 'counts' },
        { metric: 'tomcat_connector_current_threads_busy', label: '忙碌线程', color: '#ff8a1f', unit: 'counts' },
        { metric: 'tomcat_connector_max_threads', label: '最大线程', color: '#9aa9bf', unit: 'counts' }
      ]
    },
    {
      title: 'JVM 内存趋势',
      subtitle: '空闲、已分配、最大',
      metric: 'tomcat_jvm_memory_total',
      guide: [{ label: 'JVM 内存', detail: '对比 JVM 空闲、已分配和最大内存，判断 JVM 堆容量状态。虚线为最大堆上限，实线收敛说明内存压力增大。' }],
      series: [
        { metric: 'tomcat_jvm_memory_free', label: '空闲内存', color: '#27c274', unit: 'bytes' },
        { metric: 'tomcat_jvm_memory_total', label: '已分配内存', color: '#2f6bff', unit: 'bytes' },
        { metric: 'tomcat_jvm_memory_max', label: '最大内存', color: '#9aa9bf', unit: 'bytes', style: 'limit' }
      ]
    },
    {
      title: '发送流量趋势',
      subtitle: '发送速率（接收速率为采集缺口，暂不展示）',
      metric: 'tomcat_connector_bytes_sent_rate',
      guide: [{ label: '发送流量', detail: 'Tomcat Connector 数据发送速率变化。注：接收速率当前为采集缺口，若需监控接收侧流量请扩展 Telegraf 采集配置。' }],
      series: [
        { metric: 'tomcat_connector_bytes_sent_rate', label: '发送流量', color: '#27c274', unit: 'byteps' }
      ]
    },
    {
      title: 'MemoryPool 趋势',
      subtitle: '已用、提交、最大',
      metric: 'tomcat_jvm_memorypool_used',
      guide: [{ label: 'MemoryPool', detail: '对比 MemoryPool 已用、已提交和最大内存，识别内存池压力。虚线为内存池上限。' }],
      series: [
        { metric: 'tomcat_jvm_memorypool_used', label: '已用', color: '#8a5cff', unit: 'bytes' },
        { metric: 'tomcat_jvm_memorypool_committed', label: '已提交', color: '#2f6bff', unit: 'bytes' },
        { metric: 'tomcat_jvm_memorypool_max', label: '最大', color: '#9aa9bf', unit: 'bytes', style: 'limit' }
      ]
    }
  ],
  ringPanels: [
    {
      title: '线程池占用分布',
      subtitle: '忙碌、空闲',
      centerMetric: 'tomcat_connector_current_thread_utilization',
      centerCaption: '线程池利用率',
      centerUnit: 'percent',
      guide: [{ label: '线程池分布', detail: '按忙碌和空闲线程拆分当前线程池使用状态，中心为利用率百分比。' }],
      segments: [
        { label: '忙碌线程', metric: 'tomcat_connector_current_threads_busy', color: '#ff8a1f', unit: 'counts' },
        { label: '空闲线程', metric: 'tomcat_connector_current_threads_free', color: '#27c274', unit: 'counts' }
      ]
    }
  ],
  details: [
    {
      title: 'Connector 实时速率详情',
      subtitle: '请求速率、错误与流量',
      rows: [
        { label: '请求速率', metric: 'tomcat_connector_request_count_rate', unit: 'cps' },
        { label: '错误速率', metric: 'tomcat_connector_error_count_rate', unit: 'cps', tone: 'error' },
        { label: '错误占比', metric: 'tomcat_connector_error_rate_pct', unit: 'percent', tone: 'warning' },
        { label: '线程利用率', metric: 'tomcat_connector_current_thread_utilization', unit: 'percent' },
        { label: '发送速率', metric: 'tomcat_connector_bytes_sent_rate', unit: 'byteps' }
      ]
    }
  ],
  barPanels: []
};
