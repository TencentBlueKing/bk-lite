import type { SimpleDashboardConfig } from '../common/simple-dashboard-core';

export const HOST_DASHBOARD_CONFIG: SimpleDashboardConfig = {
  routeKey: 'host',
  pageTitle: '主机监控仪表盘',
  objectFallbackName: '主机',
  instanceType: 'os',
  // 覆盖 Telegraf host / HTTP 远程 / Windows WMI（均为 instance_type=os）
  collectionStatusQuery: "count({instance_type='os', __$labels__}) by (instance_id)",
  metaItems: ['OS', 'host'],
  metrics: [
    {
      name: 'cpu_usage_total',
      display_name: 'CPU 使用率',
      description: '主机 CPU 总体使用率。',
      unit: 'percent',
      // ①Telegraf host: 100-空闲；②HTTP Remote: host_cpu_usage_percent_gauge；③Windows WMI。
      query: '(100 - cpu_usage_idle{cpu="cpu-total", instance_type="os", __$labels__}) or host_cpu_usage_percent_gauge{instance_type="os", __$labels__} or cpu_usage_total_gauge_value{instance_type="os", config_type="windows_wmi", __$labels__}',
      color: '#2f6bff'
    },
    {
      name: 'cpu_usage_user_total',
      display_name: '用户态 CPU 占比',
      description: 'CPU 在用户态消耗的时间占比（Linux/部分远程采集；Windows WMI 可能无此分解）。',
      unit: 'percent',
      query: 'cpu_usage_user{cpu="cpu-total", instance_type="os", __$labels__} or cpu_usage_user_total_gauge{instance_type="os", __$labels__}',
      color: '#13c2c2'
    },
    {
      name: 'cpu_usage_system_total',
      display_name: '内核态 CPU 占比',
      description: 'CPU 在内核态消耗的时间占比（Linux/部分远程采集；Windows WMI 可能无此分解）。',
      unit: 'percent',
      query: 'cpu_usage_system{cpu="cpu-total", instance_type="os", __$labels__} or cpu_usage_system_total_gauge{instance_type="os", __$labels__}',
      color: '#597ef7'
    },
    {
      name: 'cpu_usage_iowait_total',
      display_name: 'I/O Wait 占比',
      description: 'CPU 等待 I/O 的时间占比（主要适用于 Linux；Windows 通常无对等语义）。',
      unit: 'percent',
      query: 'cpu_usage_iowait{cpu="cpu-total", instance_type="os", __$labels__} or cpu_usage_iowait_total_gauge{instance_type="os", __$labels__}',
      color: '#ff8a1f'
    },
    {
      name: 'cpu_usage_other_total',
      display_name: '其他 CPU 占比',
      description: '除用户态、内核态和 I/O Wait 以外的 CPU 占比。',
      unit: 'percent',
      query: 'clamp_min(100 - cpu_usage_idle{cpu="cpu-total", instance_type="os", __$labels__} - cpu_usage_user{cpu="cpu-total", instance_type="os", __$labels__} - cpu_usage_system{cpu="cpu-total", instance_type="os", __$labels__} - cpu_usage_iowait{cpu="cpu-total", instance_type="os", __$labels__}, 0) or clamp_min(host_cpu_usage_percent_gauge{instance_type="os", __$labels__} - cpu_usage_user_total_gauge{instance_type="os", __$labels__} - cpu_usage_system_total_gauge{instance_type="os", __$labels__} - cpu_usage_iowait_total_gauge{instance_type="os", __$labels__}, 0)',
      color: '#9aa9bf'
    },
    {
      name: 'system_load1',
      display_name: '1 分钟负载',
      description: '主机最近 1 分钟平均负载。',
      unit: 'none',
      query: 'system_load1{instance_type="os", __$labels__} or system_load1_gauge{instance_type="os", __$labels__} or host_cpu_load_1m_gauge{instance_type="os", __$labels__} or system_load1_gauge_value{instance_type="os", config_type="windows_wmi", __$labels__}',
      color: '#27c274'
    },
    {
      name: 'system_load5',
      display_name: '5 分钟负载',
      description: '主机最近 5 分钟平均负载。',
      unit: 'none',
      query: 'system_load5{instance_type="os", __$labels__} or system_load5_gauge{instance_type="os", __$labels__} or host_cpu_load_5m_gauge{instance_type="os", __$labels__} or system_load5_gauge_value{instance_type="os", config_type="windows_wmi", __$labels__}',
      color: '#13c2c2'
    },
    {
      name: 'system_load15',
      display_name: '15 分钟负载',
      description: '主机最近 15 分钟平均负载。',
      unit: 'none',
      query: 'system_load15{instance_type="os", __$labels__} or system_load15_gauge{instance_type="os", __$labels__} or host_cpu_load_15m_gauge{instance_type="os", __$labels__} or system_load15_gauge_value{instance_type="os", config_type="windows_wmi", __$labels__}',
      color: '#597ef7'
    },
    {
      name: 'mem_used_percent',
      display_name: '内存使用率',
      description: '主机内存使用率。',
      unit: 'percent',
      query: 'mem_used_percent{instance_type="os", __$labels__} or host_mem_used_percent_gauge{instance_type="os", __$labels__} or mem_used_percent_gauge_value{instance_type="os", config_type="windows_wmi", __$labels__}',
      color: '#27c274'
    },
    {
      name: 'disk_used_percent',
      display_name: '磁盘使用率',
      description: '主机各挂载点磁盘使用率中的最大值（最满分区）。',
      unit: 'percent',
      // ①Telegraf host 按挂载点；②HTTP Remote；③Windows WMI。取 max 作为主机级容量压力信号。
      query: 'max by (instance_id) (disk_used_percent{instance_type="os", __$labels__} or host_disk_used_percent_gauge{instance_type="os", __$labels__} or disk_used_percent_gauge_value{instance_type="os", config_type="windows_wmi", __$labels__})',
      color: '#faad14'
    },
    {
      name: 'mem_available',
      display_name: '可用内存',
      description: '主机当前可用内存。',
      unit: 'bytes',
      query: 'mem_available{instance_type="os", __$labels__} or host_mem_available_bytes_gauge{instance_type="os", __$labels__} or mem_available_gauge_value{instance_type="os", config_type="windows_wmi", __$labels__}',
      color: '#13c2c2'
    },
    {
      name: 'processes_blocked',
      display_name: '阻塞进程数',
      description: '当前处于不可中断等待（常与慢 I/O 相关）的进程数量。',
      unit: 'counts',
      query: 'processes_blocked{instance_type="os", __$labels__} or processes_blocked_gauge{instance_type="os", __$labels__} or processes_blocked_gauge_value{instance_type="os", config_type="windows_wmi", __$labels__}',
      color: '#ff8a1f'
    },
    {
      name: 'processes_zombies',
      display_name: '僵尸进程数',
      description: '当前处于僵尸状态的进程数量。',
      unit: 'counts',
      query: 'processes_zombies{instance_type="os", __$labels__} or processes_zombies_gauge{instance_type="os", __$labels__} or processes_zombies_gauge_value{instance_type="os", config_type="windows_wmi", __$labels__}',
      color: '#8a5cff'
    },
    {
      name: 'net_bytes_recv_rate',
      display_name: '网络入流量',
      description: '主机所有网卡接收字节速率合计。计算窗口与时间选择器一致。',
      unit: 'byteps',
      query: 'sum by (instance_id) (rate(net_bytes_recv{instance_type="os", __$labels__}[__$window__]) or rate(net_bytes_recv_gauge{instance_type="os", __$labels__}[__$window__]) or rate(net_bytes_recv_gauge_value{instance_type="os", config_type="windows_wmi", __$labels__}[__$window__]))',
      color: '#2f6bff'
    },
    {
      name: 'net_bytes_sent_rate',
      display_name: '网络出流量',
      description: '主机所有网卡发送字节速率合计。计算窗口与时间选择器一致。',
      unit: 'byteps',
      query: 'sum by (instance_id) (rate(net_bytes_sent{instance_type="os", __$labels__}[__$window__]) or rate(net_bytes_sent_gauge{instance_type="os", __$labels__}[__$window__]) or rate(net_bytes_sent_gauge_value{instance_type="os", config_type="windows_wmi", __$labels__}[__$window__]))',
      color: '#27c274'
    },
    {
      name: 'net_err_in_rate',
      display_name: '网络接收错误速率',
      description: '主机所有网卡接收错误包速率合计。计算窗口与时间选择器一致。',
      unit: 'cps',
      query: 'sum by (instance_id) (rate(net_err_in{instance_type="os", __$labels__}[__$window__]) or rate(net_err_in_gauge{instance_type="os", __$labels__}[__$window__]) or rate(net_err_in_gauge_value{instance_type="os", config_type="windows_wmi", __$labels__}[__$window__]))',
      color: '#ff8a1f'
    },
    {
      name: 'net_err_out_rate',
      display_name: '网络发送错误速率',
      description: '主机所有网卡发送错误包速率合计。计算窗口与时间选择器一致。',
      unit: 'cps',
      query: 'sum by (instance_id) (rate(net_err_out{instance_type="os", __$labels__}[__$window__]) or rate(net_err_out_gauge{instance_type="os", __$labels__}[__$window__]) or rate(net_err_out_gauge_value{instance_type="os", config_type="windows_wmi", __$labels__}[__$window__]))',
      color: '#8a5cff'
    },
    {
      name: 'diskio_read_bytes_rate',
      display_name: '磁盘读吞吐',
      description: '主机所有磁盘设备读取字节速率合计。计算窗口与时间选择器一致。',
      unit: 'byteps',
      query: 'sum by (instance_id) (rate(diskio_read_bytes{instance_type="os", __$labels__}[__$window__]) or rate(diskio_read_bytes_total_gauge{instance_type="os", __$labels__}[__$window__]) or rate(diskio_read_bytes_gauge_value{instance_type="os", config_type="windows_wmi", __$labels__}[__$window__]))',
      color: '#13c2c2'
    },
    {
      name: 'diskio_write_bytes_rate',
      display_name: '磁盘写吞吐',
      description: '主机所有磁盘设备写入字节速率合计。计算窗口与时间选择器一致。',
      unit: 'byteps',
      query: 'sum by (instance_id) (rate(diskio_write_bytes{instance_type="os", __$labels__}[__$window__]) or rate(diskio_write_bytes_total_gauge{instance_type="os", __$labels__}[__$window__]) or rate(diskio_write_bytes_gauge_value{instance_type="os", config_type="windows_wmi", __$labels__}[__$window__]))',
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
      title: '磁盘使用率',
      metric: 'disk_used_percent',
      color: '#faad14',
      icon: 'database',
      guide: [{
        label: '磁盘使用率',
        detail: '取各挂载点中最高的使用率，反映主机最满分区。持续偏高时先清理该分区或扩容，并对照下方磁盘吞吐是否伴随写入压力。'
      }]
    },
    {
      title: 'I/O Wait 占比',
      metric: 'cpu_usage_iowait_total',
      color: '#ff8a1f',
      icon: 'thunder',
      compare: true,
      guide: [{
        label: 'I/O Wait 占比',
        detail: 'CPU 等待 I/O 的时间占比（主要适用于 Linux）。持续偏高时对照下方磁盘吞吐与阻塞进程，优先排查慢盘或网络阻塞。Windows 主机通常无对等指标。'
      }]
    },
    {
      title: '1 分钟负载',
      metric: 'system_load1',
      color: '#13c2c2',
      icon: 'node',
      guide: [{
        label: '系统负载',
        detail: '主机最近 1 分钟平均负载（可运行 + 不可中断等待的进程数）。结合 CPU 使用率与 I/O Wait 区分算力打满还是卡在 I/O。'
      }],
      footer: [
        { label: '5 分钟负载', metric: 'system_load5', unit: 'none' }
      ]
    }
  ],
  charts: [
    {
      title: '资源使用趋势',
      subtitle: 'CPU、内存、磁盘、I/O Wait',
      metric: 'cpu_usage_total',
      guide: [{ label: '资源使用', detail: '对比 CPU、内存、最满分区磁盘使用率与 I/O Wait 变化。' }],
      series: [
        { metric: 'cpu_usage_total', label: 'CPU 使用率', color: '#2f6bff', unit: 'percent' },
        { metric: 'mem_used_percent', label: '内存使用率', color: '#27c274', unit: 'percent' },
        { metric: 'disk_used_percent', label: '磁盘使用率', color: '#faad14', unit: 'percent' },
        { metric: 'cpu_usage_iowait_total', label: 'I/O Wait 占比', color: '#ff8a1f', unit: 'percent' }
      ]
    },
    {
      title: '系统负载趋势',
      subtitle: '1 / 5 / 15 分钟',
      metric: 'system_load1',
      guide: [{ label: '系统负载', detail: '1 / 5 / 15 分钟平均负载（运行 + 等待的进程数）。持续偏高时结合 CPU 使用率与 I/O Wait 判断是算力不足还是等待 I/O。' }],
      series: [
        { metric: 'system_load1', label: '1 分钟', color: '#27c274', unit: 'none' },
        { metric: 'system_load5', label: '5 分钟', color: '#13c2c2', unit: 'none' },
        { metric: 'system_load15', label: '15 分钟', color: '#597ef7', unit: 'none' }
      ]
    },
    {
      title: '网络吞吐趋势',
      subtitle: '入流量与出流量合计',
      metric: 'net_bytes_recv_rate',
      guide: [{
        label: '网络吞吐',
        detail: '主机所有网卡入/出流量合计。速率计算窗口与时间选择器一致（长窗会更平滑）。与右侧错误对照：吞吐正常但错误持续非零，优先查网卡/驱动/对端；两者同时抬升，再看是否流量冲击。'
      }],
      series: [
        { metric: 'net_bytes_recv_rate', label: '入流量', color: '#2f6bff', unit: 'byteps' },
        { metric: 'net_bytes_sent_rate', label: '出流量', color: '#27c274', unit: 'byteps' }
      ]
    },
    {
      title: '网络错误速率',
      subtitle: '接收、发送错误合计',
      metric: 'net_err_in_rate',
      guide: [{
        label: '网络错误速率',
        detail: '主机所有网卡收/发错误包速率合计。健康基线通常接近 0：持续非零先查网卡、驱动与对端连通性；若左侧吞吐同时异常，再区分拥塞与链路故障。计算窗口与时间选择器一致。'
      }],
      series: [
        { metric: 'net_err_in_rate', label: '接收错误', color: '#ff8a1f', unit: 'cps' },
        { metric: 'net_err_out_rate', label: '发送错误', color: '#8a5cff', unit: 'cps' }
      ]
    },
    {
      title: '磁盘吞吐趋势',
      subtitle: '读吞吐与写吞吐合计',
      metric: 'diskio_read_bytes_rate',
      guide: [{
        label: '磁盘吞吐',
        detail: '主机所有磁盘设备读写吞吐合计。可与 I/O Wait、阻塞进程对照判断是否卡在磁盘。速率计算窗口与时间选择器一致。'
      }],
      series: [
        { metric: 'diskio_read_bytes_rate', label: '读吞吐', color: '#13c2c2', unit: 'byteps' },
        { metric: 'diskio_write_bytes_rate', label: '写吞吐', color: '#ff8a1f', unit: 'byteps' }
      ]
    },
    {
      title: '进程异常趋势',
      subtitle: '阻塞与僵尸进程',
      metric: 'processes_blocked',
      guide: [{
        label: '进程异常',
        detail: '阻塞进程持续非零多与慢 I/O / 不可中断等待相关；僵尸进程非零查父进程未回收。I/O Wait 见上方 KPI 与资源趋势（Linux）。'
      }],
      series: [
        { metric: 'processes_blocked', label: '阻塞进程', color: '#ff8a1f', unit: 'counts' },
        { metric: 'processes_zombies', label: '僵尸进程', color: '#8a5cff', unit: 'counts' }
      ]
    }
  ],
  // 内存占用环与进程状态环已砍：前者与内存 KPI 镜像，后者常态被休眠进程淹没；
  // 进程异常看「进程异常趋势」，内存看 KPI 与资源使用趋势。
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
        { label: 'I/O Wait 占比', metric: 'cpu_usage_iowait_total', color: '#ff8a1f', unit: 'percent' },
        { label: '其他', metric: 'cpu_usage_other_total', color: '#e8f0fe', unit: 'percent' }
      ]
    }
  ],
  barPanels: [],
  details: []
};
