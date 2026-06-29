import type { SimpleDashboardConfig } from '../common/simple-dashboard-core';

const NODE_CONDITION_ENUM = {
  0: { label: '未就绪', color: '#faad14' },
  1: { label: '就绪', color: '#27c274' }
};

export const NODE_DASHBOARD_CONFIG: SimpleDashboardConfig = {
  routeKey: 'k8s-node',
  pageTitle: 'K8s 节点监控仪表盘',
  objectFallbackName: 'K8s 节点',
  instanceType: 'k8s',
  clusterFilter: true,
  collectionStatusQuery:
    "count(prometheus_remote_write_kube_node_info{instance_type='k8s', __$labels__}) by (instance_id)",
  metaItems: ['Telegraf', 'k8s'],
  metrics: [
    {
      name: 'node_status_condition',
      display_name: '节点状态',
      description: '节点 Ready 状态(0 未就绪 / 1 就绪)。',
      unit: 'none',
      query: 'prometheus_remote_write_kube_node_status_condition{instance_type="k8s",condition="Ready",status="true",__$labels__}',
      color: '#27c274'
    },
    {
      name: 'node_cpu_utilization',
      display_name: 'CPU 使用率',
      description: '节点 CPU 总体使用率(100 - idle)。',
      unit: 'percent',
      query: '100 - avg by (instance_id, node) (prometheus_remote_write_cpu_usage_idle{instance_type="k8s", cpu="cpu-total", __$labels__})',
      color: '#2f6bff'
    },
    {
      name: 'node_cpu_user_rate',
      display_name: '用户态',
      description: '用户态进程占用的 CPU 百分比。',
      unit: 'percent',
      query: 'prometheus_remote_write_cpu_usage_user{instance_type="k8s",cpu="cpu-total", __$labels__}',
      color: '#13c2c2'
    },
    {
      name: 'node_cpu_system_rate',
      display_name: '内核态',
      description: '内核态进程占用的 CPU 百分比。',
      unit: 'percent',
      query: 'prometheus_remote_write_cpu_usage_system{instance_type="k8s",cpu="cpu-total", __$labels__}',
      color: '#597ef7'
    },
    {
      name: 'node_cpu_iowait_rate',
      display_name: 'IO 等待',
      description: 'CPU 等待 I/O 完成的时间百分比。',
      unit: 'percent',
      query: 'prometheus_remote_write_cpu_usage_iowait{instance_type="k8s",cpu="cpu-total", __$labels__}',
      color: '#ff8a1f'
    },
    {
      name: 'node_memory_utilization',
      display_name: '内存使用率',
      description: '节点已用内存百分比。',
      unit: 'percent',
      query: 'prometheus_remote_write_mem_used_percent{instance_type="k8s", __$labels__}',
      color: '#27c274'
    },
    {
      name: 'node_memory_available',
      display_name: '可用内存',
      description: '可供应用使用的内存量。',
      unit: 'bytes',
      query: 'prometheus_remote_write_mem_available{instance_type="k8s", __$labels__}',
      color: '#73d13d'
    },
    {
      name: 'node_memory_cached',
      display_name: '缓存',
      description: '用于文件缓存的内存(可回收)。',
      unit: 'bytes',
      query: 'prometheus_remote_write_mem_cached{instance_type="k8s", __$labels__}',
      color: '#36cfc9'
    },
    {
      name: 'node_memory_buffered',
      display_name: '缓冲',
      description: '用于块设备 I/O 缓冲的内存。',
      unit: 'bytes',
      query: 'prometheus_remote_write_mem_buffered{instance_type="k8s", __$labels__}',
      color: '#4096ff'
    },
    {
      name: 'node_memory_shared',
      display_name: '共享',
      description: '多进程间共享的内存。',
      unit: 'bytes',
      query: 'prometheus_remote_write_mem_shared{instance_type="k8s", __$labels__}',
      color: '#9254de'
    },
    {
      name: 'node_memory_swap_free',
      display_name: 'Swap 剩余',
      description: '剩余可用的 swap 空间。',
      unit: 'bytes',
      query: 'prometheus_remote_write_mem_swap_free{instance_type="k8s", __$labels__}',
      color: '#b37feb'
    },
    {
      name: 'node_disk_usage_rate',
      display_name: '磁盘使用率',
      description: '磁盘空间使用百分比。',
      unit: 'percent',
      query: 'max by (instance_id, node, device) (prometheus_remote_write_disk_used_percent{instance_type="k8s", __$labels__})',
      color: '#ff8a1f',
      dimensions: [{ name: 'device' }]
    },
    {
      name: 'node_disk_free',
      display_name: '磁盘可用',
      description: '当前可用的磁盘空间。',
      unit: 'bytes',
      query: 'max by (instance_id, node, device) (prometheus_remote_write_disk_free{instance_type="k8s", __$labels__})',
      color: '#73d13d',
      dimensions: [{ name: 'device' }]
    },
    {
      name: 'node_disk_inodes_used_percent',
      display_name: 'inode 使用率',
      description: '文件系统 inode 使用百分比。',
      unit: 'percent',
      query: 'max by (instance_id, node, device) (prometheus_remote_write_disk_inodes_used_percent{instance_type="k8s", __$labels__})',
      color: '#faad14',
      dimensions: [{ name: 'device' }]
    },
    {
      name: 'node_diskio_io_util',
      display_name: 'I/O 繁忙度',
      description: '磁盘设备处理 I/O 的时间占比。',
      unit: 'percent',
      query: 'prometheus_remote_write_diskio_io_util{instance_type="k8s", __$labels__}',
      color: '#ff7a45',
      dimensions: [{ name: 'name' }]
    },
    {
      name: 'node_diskio_reads_rate',
      display_name: '读 IOPS',
      description: '每秒磁盘读操作次数。',
      unit: 'counts',
      query: 'rate(prometheus_remote_write_diskio_reads{instance_type="k8s", __$labels__}[5m])',
      color: '#9254de',
      dimensions: [{ name: 'name' }]
    },
    {
      name: 'node_diskio_writes_rate',
      display_name: '写 IOPS',
      description: '每秒磁盘写操作次数。',
      unit: 'counts',
      query: 'rate(prometheus_remote_write_diskio_writes{instance_type="k8s", __$labels__}[5m])',
      color: '#f5a623',
      dimensions: [{ name: 'name' }]
    },
    {
      name: 'node_diskio_read_bytes_rate',
      display_name: '读吞吐',
      description: '每秒从磁盘读取的数据量。',
      unit: 'byteps',
      query: 'rate(prometheus_remote_write_diskio_read_bytes{instance_type="k8s", __$labels__}[5m])',
      color: '#9254de',
      dimensions: [{ name: 'name' }]
    },
    {
      name: 'node_diskio_write_bytes_rate',
      display_name: '写吞吐',
      description: '每秒写入磁盘的数据量。',
      unit: 'byteps',
      query: 'rate(prometheus_remote_write_diskio_write_bytes{instance_type="k8s", __$labels__}[5m])',
      color: '#f5a623',
      dimensions: [{ name: 'name' }]
    },
    {
      name: 'node_disk_read_latency',
      display_name: '读延迟',
      description: '磁盘读操作平均延迟。',
      unit: 'ms',
      query: 'rate(prometheus_remote_write_diskio_read_time{instance_type="k8s", __$labels__}[5m]) / clamp_min(rate(prometheus_remote_write_diskio_reads{instance_type="k8s", __$labels__}[5m]), 1e-9)',
      color: '#9254de',
      dimensions: [{ name: 'name' }]
    },
    {
      name: 'node_disk_write_latency',
      display_name: '写延迟',
      description: '磁盘写操作平均延迟。',
      unit: 'ms',
      query: 'rate(prometheus_remote_write_diskio_write_time{instance_type="k8s", __$labels__}[5m]) / clamp_min(rate(prometheus_remote_write_diskio_writes{instance_type="k8s", __$labels__}[5m]), 1e-9)',
      color: '#f5a623',
      dimensions: [{ name: 'name' }]
    },
    {
      name: 'node_net_bytes_recv_rate',
      display_name: '接收吞吐',
      description: '网络接口每秒接收的数据量。',
      unit: 'byteps',
      query: 'rate(prometheus_remote_write_net_bytes_recv{instance_type="k8s", __$labels__}[5m])',
      color: '#13c2c2',
      dimensions: [{ name: 'interface' }]
    },
    {
      name: 'node_net_bytes_sent_rate',
      display_name: '发送吞吐',
      description: '网络接口每秒发送的数据量。',
      unit: 'byteps',
      query: 'rate(prometheus_remote_write_net_bytes_sent{instance_type="k8s", __$labels__}[5m])',
      color: '#597ef7',
      dimensions: [{ name: 'interface' }]
    },
    {
      name: 'node_net_packets_recv_rate',
      display_name: '接收包速率',
      description: '网络接口每秒接收的数据包数。',
      unit: 'cps',
      query: 'rate(prometheus_remote_write_net_packets_recv{instance_type="k8s", __$labels__}[5m])',
      color: '#36cfc9',
      dimensions: [{ name: 'interface' }]
    },
    {
      name: 'node_net_packets_sent_rate',
      display_name: '发送包速率',
      description: '网络接口每秒发送的数据包数。',
      unit: 'cps',
      query: 'rate(prometheus_remote_write_net_packets_sent{instance_type="k8s", __$labels__}[5m])',
      color: '#9254de',
      dimensions: [{ name: 'interface' }]
    },
    {
      name: 'node_cpu_load1',
      display_name: '1 分钟负载',
      description: '最近 1 分钟系统平均负载。',
      unit: 'counts',
      query: 'prometheus_remote_write_system_load1{instance_type="k8s", __$labels__}',
      color: '#2f6bff'
    }
  ],
  summaryCards: [
    {
      title: '节点状态',
      guide: [{ label: '节点状态', detail: '节点 Ready 状态:就绪 = 可正常调度 Pod,未就绪 = 节点异常。未就绪时查看本页 CPU / 内存 / 磁盘水位及 kubelet。' }],
      metric: 'node_status_condition',
      unit: 'none',
      color: '#27c274',
      icon: 'health',
      enumMap: NODE_CONDITION_ENUM
    },
    {
      title: 'CPU 使用率',
      guide: [{ label: 'CPU 使用率', detail: '节点 CPU 总体使用率,越低越好。' }],
      metric: 'node_cpu_utilization',
      unit: 'percent',
      color: '#2f6bff',
      icon: 'thunder',
      compare: true,
      compareFavorableDirection: 'down'
    },
    {
      title: '内存使用率',
      guide: [{ label: '内存使用率', detail: '节点已用内存百分比,越低越好。' }],
      metric: 'node_memory_utilization',
      unit: 'percent',
      color: '#27c274',
      icon: 'memory',
      compare: true,
      compareFavorableDirection: 'down',
      footer: [{ label: '可用', metric: 'node_memory_available', unit: 'bytes' }]
    },
    {
      title: '磁盘使用率',
      guide: [{ label: '磁盘使用率', detail: '节点磁盘空间使用百分比,越低越好。' }],
      metric: 'node_disk_usage_rate',
      unit: 'percent',
      color: '#ff8a1f',
      icon: 'database',
      compare: true,
      compareFavorableDirection: 'down'
    },
    {
      title: '1 分钟负载',
      guide: [{ label: '系统负载', detail: '最近 1 分钟系统平均负载。' }],
      metric: 'node_cpu_load1',
      unit: 'counts',
      color: '#2f6bff',
      icon: 'node',
      compare: true,
      compareFavorableDirection: 'down'
    }
  ],
  charts: [
    {
      title: '资源水位趋势',
      subtitle: 'CPU / 内存 / 磁盘 使用率',
      guide: [{ label: '资源水位', detail: '节点 CPU、内存、磁盘使用率随时间变化;三条线越高说明资源越吃紧(接近占满)。' }],
      metric: 'node_cpu_utilization',
      series: [
        { metric: 'node_cpu_utilization', label: 'CPU 使用率', color: '#2f6bff', unit: 'percent' },
        { metric: 'node_memory_utilization', label: '内存使用率', color: '#27c274', unit: 'percent' },
        { metric: 'node_disk_usage_rate', label: '磁盘使用率', color: '#ff8a1f', unit: 'percent' }
      ]
    },
    {
      title: '吞吐趋势',
      subtitle: '网络与磁盘 I/O',
      guide: [{ label: '吞吐', detail: '网络收发与磁盘读写吞吐速率。' }],
      metric: 'node_net_bytes_recv_rate',
      series: [
        { metric: 'node_net_bytes_recv_rate', label: '网络接收', color: '#13c2c2', unit: 'byteps' },
        { metric: 'node_net_bytes_sent_rate', label: '网络发送', color: '#597ef7', unit: 'byteps' },
        { metric: 'node_diskio_read_bytes_rate', label: '磁盘读', color: '#9254de', unit: 'byteps' },
        { metric: 'node_diskio_write_bytes_rate', label: '磁盘写', color: '#f5a623', unit: 'byteps' }
      ]
    }
  ],
  ringPanels: [
    {
      title: 'CPU 时间分布',
      subtitle: '用户/内核/等待',
      guide: [{ label: 'CPU 时间分布', detail: 'CPU 时间在用户态、内核态、IO 等待间的分布。' }],
      centerMetric: 'node_cpu_utilization',
      centerCaption: 'CPU 使用率',
      centerUnit: 'percent',
      segments: [
        { label: '用户态', metric: 'node_cpu_user_rate', color: '#13c2c2', unit: 'percent' },
        { label: '内核态', metric: 'node_cpu_system_rate', color: '#597ef7', unit: 'percent' },
        { label: 'IO 等待', metric: 'node_cpu_iowait_rate', color: '#ff8a1f', unit: 'percent' }
      ]
    },
    {
      title: '内存构成',
      subtitle: '缓存/缓冲/共享/可用',
      guide: [{ label: '内存构成', detail: '节点内存在缓存、缓冲、共享与可用之间的分布。' }],
      centerMetric: 'node_memory_utilization',
      centerCaption: '内存使用率',
      centerUnit: 'percent',
      segments: [
        { label: '缓存', metric: 'node_memory_cached', color: '#36cfc9', unit: 'bytes' },
        { label: '缓冲', metric: 'node_memory_buffered', color: '#4096ff', unit: 'bytes' },
        { label: '共享', metric: 'node_memory_shared', color: '#9254de', unit: 'bytes' },
        { label: '可用', metric: 'node_memory_available', color: '#73d13d', unit: 'bytes' }
      ]
    }
  ],
  details: [
    {
      title: '磁盘 I/O 与压力',
      subtitle: '延迟 · 繁忙度 · inode · IOPS',
      rows: [
        { label: '读延迟', metric: 'node_disk_read_latency', unit: 'ms' },
        { label: '写延迟', metric: 'node_disk_write_latency', unit: 'ms' },
        { label: 'I/O 繁忙度', metric: 'node_diskio_io_util', unit: 'percent' },
        { label: 'inode 使用率', metric: 'node_disk_inodes_used_percent', unit: 'percent' },
        { label: '读 IOPS', metric: 'node_diskio_reads_rate', unit: 'counts' },
        { label: '写 IOPS', metric: 'node_diskio_writes_rate', unit: 'counts' }
      ]
    }
  ]
};
