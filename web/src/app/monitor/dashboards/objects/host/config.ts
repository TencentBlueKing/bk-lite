import type { SimpleDashboardConfig } from '../common/simple-dashboard-core';

export const HOST_DASHBOARD_CONFIG: SimpleDashboardConfig = {
  routeKey: 'host',
  pageTitle: '主机监控仪表盘',
  objectFallbackName: '主机',
  instanceType: 'os',
  collectionStatusQuery: "count({instance_type='os', collect_type='host', __$labels__}) by (instance_id)",
  metaItems: ['Telegraf', 'host'],
  metrics: [
    {
      name: 'cpu_usage_total',
      display_name: 'CPU 使用率',
      description: '主机 CPU 总体使用率。',
      unit: 'percent',
      query: 'cpu_usage_total{__$labels__}',
      color: '#2f6bff'
    },
    {
      name: 'cpu_usage_user_total',
      display_name: '用户态 CPU 占比',
      description: 'CPU 在用户态消耗的时间占比。',
      unit: 'percent',
      query: 'cpu_usage_user_total{__$labels__}',
      color: '#13c2c2'
    },
    {
      name: 'cpu_usage_system_total',
      display_name: '内核态 CPU 占比',
      description: 'CPU 在内核态消耗的时间占比。',
      unit: 'percent',
      query: 'cpu_usage_system_total{__$labels__}',
      color: '#597ef7'
    },
    {
      name: 'cpu_usage_iowait_total',
      display_name: 'I/O Wait 占比',
      description: 'CPU 等待 I/O 的时间占比。',
      unit: 'percent',
      query: 'cpu_usage_iowait_total{__$labels__}',
      color: '#ff8a1f'
    },
    {
      name: 'cpu_usage_other_total',
      display_name: '其他 CPU 占比',
      description: '除用户态、内核态和 I/O Wait 以外的 CPU 占比。',
      unit: 'percent',
      query: 'clamp_min(cpu_usage_total{__$labels__} - cpu_usage_user_total{__$labels__} - cpu_usage_system_total{__$labels__} - cpu_usage_iowait_total{__$labels__}, 0)',
      color: '#9aa9bf'
    },
    {
      name: 'system_load1',
      display_name: '1 分钟负载',
      description: '主机最近 1 分钟平均负载。',
      unit: 'none',
      query: 'system_load1{__$labels__}',
      color: '#27c274'
    },
    {
      name: 'system_load5',
      display_name: '5 分钟负载',
      description: '主机最近 5 分钟平均负载。',
      unit: 'none',
      query: 'system_load5{__$labels__}',
      color: '#13c2c2'
    },
    {
      name: 'system_load15',
      display_name: '15 分钟负载',
      description: '主机最近 15 分钟平均负载。',
      unit: 'none',
      query: 'system_load15{__$labels__}',
      color: '#597ef7'
    },
    {
      name: 'mem_used_percent',
      display_name: '内存使用率',
      description: '主机内存使用率。',
      unit: 'percent',
      query: 'mem_used_percent{__$labels__}',
      color: '#27c274'
    },
    {
      name: 'mem_total',
      display_name: '总内存',
      description: '主机总内存容量。',
      unit: 'bytes',
      query: 'mem_total{__$labels__}',
      color: '#2f6bff'
    },
    {
      name: 'mem_available',
      display_name: '可用内存',
      description: '主机当前可用内存。',
      unit: 'bytes',
      query: 'mem_available{__$labels__}',
      color: '#13c2c2'
    },
    {
      name: 'mem_cached',
      display_name: '缓存内存',
      description: '主机页缓存占用的内存。',
      unit: 'bytes',
      query: 'mem_cached{__$labels__}',
      color: '#597ef7'
    },
    {
      name: 'mem_buffered',
      display_name: '缓冲内存',
      description: '主机缓冲区占用的内存。',
      unit: 'bytes',
      query: 'mem_buffered{__$labels__}',
      color: '#ff8a1f'
    },
    {
      name: 'mem_used_bytes',
      display_name: '已用内存',
      description: '主机当前已使用的内存。',
      unit: 'bytes',
      query: 'clamp_min(mem_total{__$labels__} - mem_available{__$labels__}, 0)',
      color: '#27c274'
    },
    {
      name: 'processes_running',
      display_name: '运行进程数',
      description: '当前正在运行的进程数量。',
      unit: 'counts',
      query: 'processes_running{__$labels__}',
      color: '#2f6bff'
    },
    {
      name: 'processes_blocked',
      display_name: '阻塞进程数',
      description: '当前处于阻塞状态的进程数量。',
      unit: 'counts',
      query: 'processes_blocked{__$labels__}',
      color: '#ff8a1f'
    },
    {
      name: 'processes_sleeping',
      display_name: '休眠进程数',
      description: '当前处于休眠状态的进程数量。',
      unit: 'counts',
      query: 'processes_sleeping{__$labels__}',
      color: '#13c2c2'
    },
    {
      name: 'processes_zombies',
      display_name: '僵尸进程数',
      description: '当前处于僵尸状态的进程数量。',
      unit: 'counts',
      query: 'processes_zombies{__$labels__}',
      color: '#9aa9bf'
    },
    {
      name: 'processes_total',
      display_name: '总进程数',
      description: '当前主机进程总量。',
      unit: 'counts',
      query: 'processes_running{__$labels__} + processes_sleeping{__$labels__} + processes_blocked{__$labels__} + processes_zombies{__$labels__}',
      color: '#13c2c2'
    },
    {
      name: 'net_bytes_recv_rate',
      display_name: '网络入流量',
      description: '各网卡接收字节速率。',
      unit: 'byteps',
      query: 'net_bytes_recv_rate{__$labels__}',
      color: '#2f6bff'
    },
    {
      name: 'net_bytes_sent_rate',
      display_name: '网络出流量',
      description: '各网卡发送字节速率。',
      unit: 'byteps',
      query: 'net_bytes_sent_rate{__$labels__}',
      color: '#27c274'
    },
    {
      name: 'diskio_read_bytes_rate',
      display_name: '磁盘读吞吐',
      description: '各磁盘设备读取字节速率。',
      unit: 'byteps',
      query: 'diskio_read_bytes_rate{__$labels__}',
      color: '#13c2c2'
    },
    {
      name: 'diskio_write_bytes_rate',
      display_name: '磁盘写吞吐',
      description: '各磁盘设备写入字节速率。',
      unit: 'byteps',
      query: 'diskio_write_bytes_rate{__$labels__}',
      color: '#ff8a1f'
    }
  ],
  summaryCards: [
    {
      title: 'CPU 使用率',
      metric: 'cpu_usage_total',
      color: '#2f6bff',
      icon: 'thunder',
      guide: [{ label: 'CPU 使用率', detail: '主机整体 CPU 已用时间百分比;持续接近 100% 表示 CPU 紧张。' }],
      footer: [
        { label: '用户态', metric: 'cpu_usage_user_total', unit: 'percent' },
        { label: '内核态', metric: 'cpu_usage_system_total', unit: 'percent' }
      ]
    },
    {
      title: '内存使用率',
      metric: 'mem_used_percent',
      color: '#27c274',
      icon: 'database',
      guide: [{ label: '内存使用率', detail: '已用内存占总内存的百分比;越高表示可用内存越少。' }],
      footer: [{ label: '可用内存', metric: 'mem_available', unit: 'bytes' }]
    },
    {
      title: 'I/O Wait',
      metric: 'cpu_usage_iowait_total',
      color: '#ff8a1f',
      icon: 'thunder',
      compare: true,
      guide: [{ label: 'I/O Wait', detail: 'CPU 等待磁盘或网络 I/O 的占比。' }]
    },
    {
      title: '1 分钟负载',
      metric: 'system_load1',
      color: '#13c2c2',
      icon: 'node',
      guide: [{ label: '系统负载', detail: '主机最近 1 分钟平均负载。' }],
      footer: [{ label: '5 分钟负载', metric: 'system_load5', unit: 'none' }]
    }
  ],
  charts: [
    {
      title: '资源使用趋势',
      subtitle: 'CPU、内存、I/O',
      metric: 'cpu_usage_total',
      guide: [{ label: '资源使用', detail: '对比 CPU 使用率、内存使用率和 I/O Wait 变化。' }],
      series: [
        { metric: 'cpu_usage_total', label: 'CPU 使用率', color: '#2f6bff', unit: 'percent' },
        { metric: 'mem_used_percent', label: '内存使用率', color: '#27c274', unit: 'percent' },
        { metric: 'cpu_usage_iowait_total', label: 'I/O Wait', color: '#ff8a1f', unit: 'percent' }
      ]
    },
    {
      title: '系统负载趋势',
      subtitle: '多时段负载',
      metric: 'system_load1',
      guide: [{ label: '系统负载', detail: '1 / 5 / 15 分钟平均负载(运行 + 等待 CPU 的进程数);持续超过 CPU 核数即偏高。' }],
      series: [
        { metric: 'system_load1', label: '1 分钟', color: '#27c274', unit: 'none' },
        { metric: 'system_load5', label: '5 分钟', color: '#13c2c2', unit: 'none' },
        { metric: 'system_load15', label: '15 分钟', color: '#597ef7', unit: 'none' }
      ]
    },
    {
      title: '网络吞吐趋势',
      subtitle: '入流量与出流量',
      metric: 'net_bytes_recv_rate',
      guide: [{ label: '网络吞吐', detail: '聚合主机所有网卡的入流量与出流量。' }],
      series: [
        { metric: 'net_bytes_recv_rate', label: '入流量', color: '#2f6bff', unit: 'byteps' },
        { metric: 'net_bytes_sent_rate', label: '出流量', color: '#27c274', unit: 'byteps' }
      ]
    },
    {
      title: '磁盘吞吐趋势',
      subtitle: '读吞吐与写吞吐',
      metric: 'diskio_read_bytes_rate',
      guide: [{ label: '磁盘吞吐', detail: '聚合主机所有磁盘设备的读写吞吐变化。' }],
      series: [
        { metric: 'diskio_read_bytes_rate', label: '读吞吐', color: '#13c2c2', unit: 'byteps' },
        { metric: 'diskio_write_bytes_rate', label: '写吞吐', color: '#ff8a1f', unit: 'byteps' }
      ]
    },
    {
      title: '进程状态趋势',
      subtitle: '运行、阻塞与僵尸',
      metric: 'processes_running',
      guide: [{ label: '进程状态', detail: '对比运行、阻塞和僵尸进程数量变化。' }],
      series: [
        { metric: 'processes_running', label: '运行进程', color: '#2f6bff', unit: 'counts' },
        { metric: 'processes_blocked', label: '阻塞进程', color: '#ff8a1f', unit: 'counts' },
        { metric: 'processes_zombies', label: '僵尸进程', color: '#9aa9bf', unit: 'counts' }
      ]
    }
  ],
  ringPanels: [
    {
      title: 'CPU 时间分布',
      subtitle: '用户、内核与等待',
      centerMetric: 'cpu_usage_total',
      centerCaption: 'CPU 使用率',
      centerUnit: 'percent',
      guide: [{ label: 'CPU 结构', detail: '拆分当前 CPU 使用率中的用户态、内核态和 I/O Wait。' }],
      segments: [
        { label: '用户态', metric: 'cpu_usage_user_total', color: '#13c2c2', unit: 'percent' },
        { label: '内核态', metric: 'cpu_usage_system_total', color: '#597ef7', unit: 'percent' },
        { label: 'I/O Wait', metric: 'cpu_usage_iowait_total', color: '#ff8a1f', unit: 'percent' },
        { label: '其他', metric: 'cpu_usage_other_total', color: '#e8f0fe', unit: 'percent' }
      ]
    },
    {
      title: '内存占用分布',
      subtitle: '已用与可用内存',
      centerMetric: 'mem_used_percent',
      centerCaption: '内存使用率',
      centerUnit: 'percent',
      guide: [{ label: '内存结构', detail: '对比当前已用内存与可用内存容量。' }],
      segments: [
        { label: '已用内存', metric: 'mem_used_bytes', color: '#27c274', unit: 'bytes' },
        { label: '可用内存', metric: 'mem_available', color: '#e8f0fe', unit: 'bytes' }
      ]
    },
    {
      title: '进程状态分布',
      subtitle: '运行、休眠、阻塞、僵尸',
      centerMetric: 'processes_total',
      centerCaption: '总进程数',
      centerUnit: 'counts',
      guide: [{ label: '进程结构', detail: '对比主机当前运行、休眠、阻塞和僵尸进程的数量分布。' }],
      segments: [
        { label: '运行中', metric: 'processes_running', color: '#2f6bff', unit: 'counts' },
        { label: '休眠中', metric: 'processes_sleeping', color: '#27c274', unit: 'counts' },
        { label: '阻塞中', metric: 'processes_blocked', color: '#ff8a1f', unit: 'counts' },
        { label: '僵尸', metric: 'processes_zombies', color: '#e8f0fe', unit: 'counts' }
      ]
    }
  ],
  barPanels: [
    {
      title: '主机压力信号',
      subtitle: 'I/O Wait、阻塞/僵尸进程、负载',
      showTrend: true,
      guide: [{ label: '主机压力信号', detail: '汇总 I/O Wait、阻塞进程、僵尸进程与 1 分钟负载。阻塞/僵尸进程非零或 I/O Wait 偏高即需排查。' }],
      items: [
        { label: 'I/O Wait', metric: 'cpu_usage_iowait_total', color: '#ff8a1f', unit: 'percent' },
        { label: '阻塞进程', metric: 'processes_blocked', color: '#ff4d4f', unit: 'counts' },
        { label: '僵尸进程', metric: 'processes_zombies', color: '#faad14', unit: 'counts' },
        { label: '1 分钟负载', metric: 'system_load1', color: '#2f6bff', unit: 'none' }
      ]
    }
  ],
  details: []
};
