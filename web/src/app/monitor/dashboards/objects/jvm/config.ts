import type { SimpleDashboardConfig } from '../common/simple-dashboard-core';
import type { MetricEnumMap } from '../../shared/types';

const JMX_SCRAPE_ERROR_ENUM: MetricEnumMap = {
  0: { label: '采集正常', color: '#27c274' },
  1: { label: '采集报错', color: '#ff4d4f' }
};

export const JVM_DASHBOARD_CONFIG: SimpleDashboardConfig = {
  routeKey: 'jvm',
  pageTitle: 'JVM 监控仪表盘',
  objectFallbackName: 'JVM',
  instanceType: 'jvm',
  collectionStatusQuery: "count({instance_type='jvm', collect_type='jmx', __$labels__}) by (instance_id)",
  metaItems: ['JVM-JMX', 'jmx'],
  metrics: [
    { name: 'heapUsageRatio', display_name: '堆使用率', description: 'JVM 已用堆内存占最大堆内存的比例。', unit: 'percent', query: '100 * jvm_memory_usage_used_value{__$labels__} / clamp_min(jvm_memory_usage_max_value{__$labels__}, 1)', color: '#2f6bff' },
    { name: 'heapUsed', display_name: '堆已用内存', description: 'JVM 当前实际使用的堆内存。', unit: 'bytes', query: 'jvm_memory_usage_used_value{__$labels__}', color: '#2f6bff' },
    { name: 'heapCommitted', display_name: '堆已提交内存', description: 'JVM 已向操作系统申请的堆内存。', unit: 'bytes', query: 'jvm_memory_usage_committed_value{__$labels__}', color: '#13c2c2' },
    { name: 'heapMax', display_name: '最大堆内存', description: 'JVM 配置允许使用的最大堆内存。', unit: 'bytes', query: 'jvm_memory_usage_max_value{__$labels__}', color: '#8a5cff' },
    { name: 'threads', display_name: '当前线程数', description: 'JVM 当前正在运行的线程数。', unit: 'counts', query: 'jvm_threads_count_value{__$labels__}', color: '#ff8a1f' },
    { name: 'daemonThreads', display_name: '守护线程数', description: 'JVM 当前活跃的守护线程数。', unit: 'counts', query: 'jvm_threads_daemon_count_value{__$labels__}', color: '#13c2c2' },
    { name: 'peakThreads', display_name: '峰值线程数', description: 'JVM 运行期间达到的线程数峰值。', unit: 'counts', query: 'jvm_threads_peak_count_value{__$labels__}', color: '#8a5cff' },
    { name: 'totalStartedThreads', display_name: '累计启动线程数', description: 'JVM 启动以来创建并启动的线程总数。', unit: 'counts', query: 'jvm_threads_total_started_count_value{__$labels__}', color: '#597ef7' },
    { name: 'gcTimeRatio', display_name: 'GC 时间占比', description: '最近五分钟内 GC 占用运行时间的比例。', unit: 'percent', query: '100 * sum(rate(jvm_gc_collectiontime_seconds_value{__$labels__}[5m])) by (instance_id)', color: '#ff4d4f' },
    { name: 'gcCountRate', display_name: 'GC 频率', description: '最近五分钟内每秒执行的 GC 次数。', unit: 'cps', query: 'sum(rate(jvm_gc_collectioncount_value{__$labels__}[5m])) by (instance_id)', color: '#ff8a1f' },
    { name: 'memoryPoolUsed', display_name: '内存池已用', description: 'JVM 内存池当前实际使用的内存。', unit: 'bytes', query: 'sum(jvm_memorypool_usage_used_value{__$labels__}) by (instance_id)', color: '#8a5cff' },
    { name: 'memoryPoolCommitted', display_name: '内存池已提交', description: 'JVM 内存池当前已提交的内存。', unit: 'bytes', query: 'sum(jvm_memorypool_usage_committed_value{__$labels__}) by (instance_id)', color: '#2f6bff' },
    { name: 'memoryPoolMax', display_name: '内存池上限', description: 'JVM 内存池允许使用的最大内存。', unit: 'bytes', query: 'sum(jvm_memorypool_usage_max_value{__$labels__}) by (instance_id)', color: '#9aa9bf' },
    { name: 'bufferUsed', display_name: 'NIO 缓冲已用', description: 'Java NIO 缓冲池当前已使用的内存。', unit: 'bytes', query: 'sum(jvm_bufferpool_memoryused_value{__$labels__}) by (instance_id)', color: '#13c2c2' },
    { name: 'bufferCapacity', display_name: 'NIO 缓冲容量', description: 'Java NIO 缓冲池总容量。', unit: 'bytes', query: 'sum(jvm_bufferpool_totalcapacity_value{__$labels__}) by (instance_id)', color: '#597ef7' },
    { name: 'physicalFree', display_name: '宿主可用内存', description: 'JVM 所在宿主机当前可用物理内存。', unit: 'bytes', query: 'jvm_os_memory_physical_free_value{__$labels__}', color: '#27c274' },
    { name: 'physicalTotal', display_name: '宿主总内存', description: 'JVM 所在宿主机物理内存总量。', unit: 'bytes', query: 'jvm_os_memory_physical_total_value{__$labels__}', color: '#9aa9bf' },
    { name: 'swapFree', display_name: '可用交换空间', description: 'JVM 所在宿主机当前可用交换空间。', unit: 'bytes', query: 'jvm_os_memory_swap_free_value{__$labels__}', color: '#13c2c2' },
    { name: 'scrapeDuration', display_name: '采集耗时', description: '最近一次 JMX 采集耗时。', unit: 's', query: 'jmx_scrape_duration_seconds_gauge{__$labels__}', color: '#597ef7' },
    { name: 'scrapeError', display_name: '采集状态', description: 'JMX 采集状态，0 为正常、1 为报错。', unit: 'none', query: 'jmx_scrape_error_gauge{__$labels__}', color: '#ff4d4f' }
  ],
  summaryCards: [
    { title: '堆使用率', metric: 'heapUsageRatio', color: '#2f6bff', icon: 'memory', compare: true, compareFavorableDirection: 'down', guide: [{ label: '堆容量风险', detail: '持续逼近 100% 时，优先排查内存泄漏、堆配置和 GC 压力。' }], footer: [{ label: '已用', metric: 'heapUsed', unit: 'bytes' }, { label: '已提交', metric: 'heapCommitted', unit: 'bytes' }, { label: '上限', metric: 'heapMax', unit: 'bytes' }] },
    { title: 'GC 时间占比', metric: 'gcTimeRatio', color: '#ff4d4f', icon: 'clock', compare: true, compareFavorableDirection: 'down', guide: [{ label: 'GC 开销', detail: '最近五分钟内 GC 实际占用的时间比例；升高表示应用有效执行时间被回收挤占。' }], footer: [{ label: 'GC 频率', metric: 'gcCountRate', unit: 'cps' }] },
    { title: '当前线程数', metric: 'threads', color: '#ff8a1f', icon: 'node', compare: true, compareFavorableDirection: 'down', guide: [{ label: '线程异常', detail: '持续高于历史水平时，结合守护线程和峰值线程判断请求堆积或线程泄漏。' }], footer: [{ label: '守护线程', metric: 'daemonThreads', unit: 'counts' }, { label: '历史峰值', metric: 'peakThreads', unit: 'counts' }] },
    { title: 'JMX 采集状态', metric: 'scrapeError', color: '#27c274', icon: 'health', enumMap: JMX_SCRAPE_ERROR_ENUM, guide: [{ label: '数据可信度', detail: '采集报错时，当前页其余指标可能过期或缺失，应先恢复 JMX 连通性。' }], footer: [{ label: '采集耗时', metric: 'scrapeDuration', unit: 's' }] }
  ],
  charts: [
    { title: '堆容量趋势', subtitle: '已用、已提交与最大堆内存', metric: 'heapUsed', guide: [{ label: '堆容量', detail: '已用内存接近已提交或最大堆内存时，GC 压力与 OOM 风险上升；虚线为最大堆上限。' }], series: [{ metric: 'heapUsed', label: '已用', color: '#2f6bff', unit: 'bytes' }, { metric: 'heapCommitted', label: '已提交', color: '#13c2c2', unit: 'bytes' }, { metric: 'heapMax', label: '最大堆', color: '#9aa9bf', unit: 'bytes', style: 'limit' }] },
    { title: '线程趋势', subtitle: '当前、守护与历史峰值线程数', metric: 'threads', guide: [{ label: '线程趋势', detail: '当前线程接近历史峰值或持续抬升时，排查线程池饱和、阻塞调用与线程泄漏。' }], series: [{ metric: 'threads', label: '当前线程', color: '#ff8a1f', unit: 'counts' }, { metric: 'daemonThreads', label: '守护线程', color: '#13c2c2', unit: 'counts' }, { metric: 'peakThreads', label: '历史峰值', color: '#9aa9bf', unit: 'counts', style: 'limit' }] },
    { title: 'GC 开销趋势', subtitle: '最近五分钟 GC 时间占比', metric: 'gcTimeRatio', guide: [{ label: 'GC 开销', detail: '这是速率换算后的时间占比，不展示不可直接比较的累计 GC 时长。' }], series: [{ metric: 'gcTimeRatio', label: 'GC 时间占比', color: '#ff4d4f', unit: 'percent' }] },
    { title: 'GC 频率趋势', subtitle: '最近五分钟每秒 GC 次数', metric: 'gcCountRate', guide: [{ label: 'GC 频率', detail: '频率与 GC 时间占比分开呈现；两者同时升高时，优先排查堆压力和对象分配。' }], series: [{ metric: 'gcCountRate', label: 'GC 频率', color: '#ff8a1f', unit: 'cps' }] }
  ],
  details: [
    { title: '内存池与缓冲', subtitle: '定位堆外、内存池与 NIO 缓冲压力。', rows: [{ label: '内存池已用', metric: 'memoryPoolUsed', unit: 'bytes', tone: 'warning' }, { label: '内存池已提交', metric: 'memoryPoolCommitted', unit: 'bytes' }, { label: '内存池上限', metric: 'memoryPoolMax', unit: 'bytes' }, { label: 'NIO 缓冲已用', metric: 'bufferUsed', unit: 'bytes', tone: 'warning' }, { label: 'NIO 缓冲容量', metric: 'bufferCapacity', unit: 'bytes' }] },
    { title: '宿主资源与线程生命周期', subtitle: '用于判断 JVM 压力是否受到宿主机资源约束。', rows: [{ label: '宿主可用内存', metric: 'physicalFree', unit: 'bytes', tone: 'warning' }, { label: '宿主总内存', metric: 'physicalTotal', unit: 'bytes' }, { label: '可用交换空间', metric: 'swapFree', unit: 'bytes', tone: 'warning' }, { label: '累计启动线程', metric: 'totalStartedThreads', unit: 'counts' }] }
  ]
};
