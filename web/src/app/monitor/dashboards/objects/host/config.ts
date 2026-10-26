import type { SimpleDashboardConfig } from '../common/simple-dashboard-core';

/** 主机仪表盘色板：高对比、鲜活通透的现代监控色系，告别暗淡沉闷 */
export const HOST_PALETTE = {
  blue: '#2563EB',      // 活力皇家蓝 (CPU 使用率、网络入流量)
  indigo: '#6366F1',    // 现代紫靛 (系统 1 分钟负载、CPU 内核态、运行时长)
  cyan: '#06B6D4',      // 清亮青蓝 (系统 5 分钟负载、磁盘读吞吐、可用内存)
  emerald: '#10B981',   // 鲜亮翠绿 (内存使用率、网络出流量、15 分钟负载)
  amber: '#F59E0B',     // 暖金琥珀 (磁盘使用率、磁盘排行榜)
  orange: '#F97316',    // 活力暖橙 (I/O Wait 占比、磁盘写吞吐、阻塞进程)
  rose: '#EF4444',      // 鲜明珊瑚红 (僵尸进程、网络错误)
  neutral: '#94A3B8'    // 清爽中性灰 (CPU 环图其他)
} as const;

/**
 * 专业仪表盘跨页序列色。权威是性能页「本机趋势」：
 * 同一指标的 KPI 主值、曲线、图例、tooltip 都读这里。
 * 可用内存 GiB、运行时间没有这条身份色，主值保持正文色。
 * 丢包和错误不进这套序列，折线仍用分项色，图例和 tooltip 跟那条线。
 */
export const HOST_SERIES_COLOR = {
  cpu: '#00B42A',
  memUsed: '#165DFF',
  memAvailable: '#0FC6C2',
  load1: '#FF7D00',
  load5: '#3491FA',
  load15: '#14C9C9',
  diskUsed: '#722ED1',
  diskRead: '#3491FA',
  diskWrite: '#EB2F96',
  netIn: '#13C2C2',
  netOut: '#2F54EB'
} as const;

/** 专业仪表盘 CPU 主值与「CPU 使用率」曲线。概览与性能共用这一条。 */
export const HOST_CPU_SERIES_COLOR = HOST_SERIES_COLOR.cpu;

/** 用量危度。只染进程表百分比和挂载条，不染 KPI 主值，也不改折线。 */
export const HOST_THRESHOLD_COLOR = {
  ok: '#00B42A',
  warn: '#FAAD14',
  crit: '#F5222D'
} as const;

export const hostThresholdColor = (value: number) => {
  if (value >= 90) return HOST_THRESHOLD_COLOR.crit;
  if (value >= 80) return HOST_THRESHOLD_COLOR.warn;
  return HOST_THRESHOLD_COLOR.ok;
};

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
      // ①Telegraf host: 100-空闲；②HTTP Remote: host_cpu_usage_percent_gauge；③Windows WMI；④AIX/FreeBSD/HP-UX/Solaris Remote: cpu_usage_total_gauge。
      query: '(100 - cpu_usage_idle{cpu="cpu-total", instance_type="os", __$labels__}) or host_cpu_usage_percent_gauge{instance_type="os", __$labels__} or cpu_usage_total_gauge_value{instance_type="os", config_type="windows_wmi", __$labels__} or cpu_usage_total_gauge{instance_type="os", config_type=~"host_(aix|freebsd|hpux|solaris)_remote", __$labels__}',
      color: HOST_SERIES_COLOR.cpu
    },
    {
      name: 'cpu_usage_user_total',
      display_name: '用户态 CPU 占比',
      description: 'CPU 在用户态消耗的时间占比（Linux/部分远程采集；Windows WMI 可能无此分解）。',
      unit: 'percent',
      query: 'cpu_usage_user{cpu="cpu-total", instance_type="os", __$labels__} or cpu_usage_user_total_gauge{instance_type="os", __$labels__}',
      color: HOST_PALETTE.cyan
    },
    {
      name: 'cpu_usage_system_total',
      display_name: '内核态 CPU 占比',
      description: 'CPU 在内核态消耗的时间占比（Linux/部分远程采集；Windows WMI 可能无此分解）。',
      unit: 'percent',
      query: 'cpu_usage_system{cpu="cpu-total", instance_type="os", __$labels__} or cpu_usage_system_total_gauge{instance_type="os", __$labels__}',
      color: HOST_PALETTE.indigo
    },
    {
      name: 'cpu_usage_iowait_total',
      display_name: 'I/O Wait 占比',
      description: 'CPU 等待 I/O 的时间占比（主要适用于 Linux；Windows 通常无对等语义）。',
      unit: 'percent',
      query: 'cpu_usage_iowait{cpu="cpu-total", instance_type="os", __$labels__} or cpu_usage_iowait_total_gauge{instance_type="os", __$labels__}',
      color: HOST_PALETTE.orange,
      linuxOnly: true
    },
    {
      name: 'cpu_usage_irq_total',
      display_name: 'IRQ 占比',
      description: 'CPU 处理硬件中断的时间占比。没有序列时不画。',
      unit: 'percent',
      query: 'cpu_usage_irq{cpu="cpu-total", instance_type="os", __$labels__} or cpu_usage_irq_total_gauge{instance_type="os", __$labels__}',
      color: HOST_PALETTE.indigo
    },
    {
      name: 'cpu_usage_softirq_total',
      display_name: 'Softirq 占比',
      description: 'CPU 处理软中断的时间占比。没有序列时不画。',
      unit: 'percent',
      query: 'cpu_usage_softirq{cpu="cpu-total", instance_type="os", __$labels__} or cpu_usage_softirq_total_gauge{instance_type="os", __$labels__}',
      color: HOST_PALETTE.cyan,
      linuxOnly: true
    },
    {
      name: 'cpu_usage_steal_total',
      display_name: 'Steal 占比',
      description: '虚拟化环境中被宿主机抢占的 CPU 时间占比。没有序列时不画。',
      unit: 'percent',
      query: 'cpu_usage_steal{cpu="cpu-total", instance_type="os", __$labels__} or cpu_usage_steal_total_gauge{instance_type="os", __$labels__}',
      color: HOST_PALETTE.rose,
      linuxOnly: true
    },
    {
      name: 'cpu_usage_other_total',
      display_name: '其他 CPU 占比',
      description: '除用户态、内核态和 I/O Wait 以外的 CPU 占比。',
      unit: 'percent',
      query: 'clamp_min(100 - cpu_usage_idle{cpu="cpu-total", instance_type="os", __$labels__} - cpu_usage_user{cpu="cpu-total", instance_type="os", __$labels__} - cpu_usage_system{cpu="cpu-total", instance_type="os", __$labels__} - cpu_usage_iowait{cpu="cpu-total", instance_type="os", __$labels__}, 0) or clamp_min(host_cpu_usage_percent_gauge{instance_type="os", __$labels__} - cpu_usage_user_total_gauge{instance_type="os", __$labels__} - cpu_usage_system_total_gauge{instance_type="os", __$labels__} - cpu_usage_iowait_total_gauge{instance_type="os", __$labels__}, 0) or clamp_min(cpu_usage_total_gauge{instance_type="os", config_type=~"host_(aix|freebsd|hpux|solaris)_remote", __$labels__} - cpu_usage_user_total_gauge{instance_type="os", config_type=~"host_(aix|freebsd|hpux|solaris)_remote", __$labels__} - cpu_usage_system_total_gauge{instance_type="os", config_type=~"host_(aix|freebsd|hpux|solaris)_remote", __$labels__} - cpu_usage_iowait_total_gauge{instance_type="os", config_type=~"host_(aix|freebsd|hpux|solaris)_remote", __$labels__}, 0)',
      color: HOST_PALETTE.neutral
    },
    {
      name: 'system_load1',
      display_name: '1 分钟负载',
      description: '主机最近 1 分钟平均负载。',
      unit: 'none',
      query: 'system_load1{instance_type="os", __$labels__} or system_load1_gauge{instance_type="os", __$labels__} or host_cpu_load_1m_gauge{instance_type="os", __$labels__}',
      color: HOST_SERIES_COLOR.load1,
      linuxOnly: true
    },
    {
      name: 'system_load5',
      display_name: '5 分钟负载',
      description: '主机最近 5 分钟平均负载。',
      unit: 'none',
      query: 'system_load5{instance_type="os", __$labels__} or system_load5_gauge{instance_type="os", __$labels__} or host_cpu_load_5m_gauge{instance_type="os", __$labels__}',
      color: HOST_SERIES_COLOR.load5,
      linuxOnly: true
    },
    {
      name: 'system_load15',
      display_name: '15 分钟负载',
      description: '主机最近 15 分钟平均负载。',
      unit: 'none',
      query: 'system_load15{instance_type="os", __$labels__} or system_load15_gauge{instance_type="os", __$labels__} or host_cpu_load_15m_gauge{instance_type="os", __$labels__}',
      color: HOST_SERIES_COLOR.load15,
      linuxOnly: true
    },
    {
      name: 'cpu_n',
      display_name: 'CPU 核数',
      description: '按非 cpu-total 的 CPU 序列计数，供负载相对核数副标使用。',
      unit: 'counts',
      query: 'count by (instance_id) (cpu_usage_idle{cpu!="cpu-total", instance_type="os", __$labels__})',
      color: HOST_PALETTE.neutral
    },
    {
      name: 'system_uptime',
      display_name: '运行时长',
      description: '主机自上次启动以来的持续运行时间，反映主机稳定性。',
      unit: 's',
      // ①Telegraf host；②HTTP Remote；③Windows WMI。
      query: 'system_uptime{instance_type="os", __$labels__} or system_uptime_gauge{instance_type="os", __$labels__} or system_uptime_gauge_value{instance_type="os", config_type="windows_wmi", __$labels__}',
      color: '#1F2329'
    },
    {
      name: 'mem_used_percent',
      display_name: '内存使用率',
      description: '主机内存使用率。',
      unit: 'percent',
      query: 'mem_used_percent{instance_type="os", __$labels__} or host_mem_used_percent_gauge{instance_type="os", __$labels__} or mem_used_percent_gauge_value{instance_type="os", config_type="windows_wmi", __$labels__} or mem_used_percent_gauge{instance_type="os", config_type=~"host_(aix|freebsd|hpux|solaris)_remote", __$labels__}',
      color: HOST_SERIES_COLOR.memUsed
    },
    {
      name: 'disk_used_percent',
      display_name: '磁盘使用率',
      description: '主机各挂载点磁盘使用率中的最大值（最满分区）。',
      unit: 'percent',
      // ①Telegraf host 按挂载点；②HTTP Remote；③Windows WMI。取 max 作为主机级容量压力信号。
      query: 'max by (instance_id) (disk_used_percent{instance_type="os", __$labels__} or host_disk_used_percent_gauge{instance_type="os", __$labels__} or disk_used_percent_gauge_value{instance_type="os", config_type="windows_wmi", __$labels__} or disk_used_percent_gauge{instance_type="os", config_type=~"host_(aix|freebsd|hpux|solaris)_remote", __$labels__})',
      color: HOST_SERIES_COLOR.diskUsed
    },
    {
      name: 'mem_available',
      display_name: '可用内存',
      description: '主机当前可用内存。',
      unit: 'bytes',
      query: 'mem_available{instance_type="os", __$labels__} or host_mem_available_bytes_gauge{instance_type="os", __$labels__} or mem_available_gauge_value{instance_type="os", config_type="windows_wmi", __$labels__} or mem_available_gauge{instance_type="os", config_type=~"host_(aix|freebsd|solaris)_remote", __$labels__}',
      color: HOST_SERIES_COLOR.memAvailable
    },
    {
      name: 'mem_total',
      display_name: '内存总量',
      description: '主机物理内存总量，用于把可用内存换算成占比。',
      unit: 'bytes',
      query: 'mem_total{instance_type="os", __$labels__} or host_mem_total_bytes_gauge{instance_type="os", __$labels__} or mem_total_gauge_value{instance_type="os", config_type="windows_wmi", __$labels__} or mem_total_gauge{instance_type="os", config_type=~"host_(aix|freebsd|hpux|solaris)_remote", __$labels__}',
      color: HOST_PALETTE.neutral
    },
    {
      name: 'mem_used',
      display_name: '已用内存',
      description: '主机已用内存字节。性能页内存构成在缺少该序列时用总量减可用推算。',
      unit: 'bytes',
      query: 'mem_used{instance_type="os", __$labels__} or mem_used_gauge{instance_type="os", __$labels__}',
      color: HOST_SERIES_COLOR.memUsed,
      linuxOnly: true
    },
    {
      name: 'mem_cached',
      display_name: '页缓存',
      description: '用于文件缓存、可在内存紧张时回收的内存。',
      unit: 'bytes',
      query: 'mem_cached{instance_type="os", __$labels__} or mem_cached_gauge{instance_type="os", __$labels__}',
      color: HOST_PALETTE.cyan,
      linuxOnly: true
    },
    {
      name: 'mem_buffered',
      display_name: '缓冲',
      description: '块设备 I/O 缓冲占用的内存。',
      unit: 'bytes',
      query: 'mem_buffered{instance_type="os", __$labels__} or mem_buffered_gauge{instance_type="os", __$labels__}',
      color: HOST_PALETTE.amber,
      linuxOnly: true
    },
    {
      name: 'mem_shared',
      display_name: '共享内存',
      description: '多个进程共享的内存。',
      unit: 'bytes',
      query: 'mem_shared{instance_type="os", __$labels__} or mem_shared_gauge{instance_type="os", __$labels__}',
      color: HOST_PALETTE.indigo,
      linuxOnly: true
    },
    {
      name: 'nvidia_smi_utilization_gpu',
      display_name: 'GPU 利用率',
      description: 'GPU 计算单元使用率。多卡时取最高。没有采集时性能页不保留空的 GPU 分区。',
      unit: 'percent',
      query: 'max by (instance_id) (nvidia_smi_utilization_gpu{instance_type="os", __$labels__})',
      color: HOST_PALETTE.emerald
    },
    {
      name: 'nvidia_smi_utilization_memory',
      display_name: 'GPU 显存利用率',
      description: 'GPU 显存占用相对总量的百分比。多卡时取最高。',
      unit: 'percent',
      query: 'max by (instance_id) (100 * (nvidia_smi_memory_used{instance_type="os", __$labels__} / nvidia_smi_memory_total{instance_type="os", __$labels__}))',
      color: HOST_PALETTE.blue
    },
    {
      name: 'nvidia_smi_memory_used',
      display_name: 'GPU 显存已用',
      description: 'GPU 已用显存。采集单位是 MiB。多卡时取最高已用。',
      unit: 'mebibytes',
      query: 'max by (instance_id) (nvidia_smi_memory_used{instance_type="os", __$labels__})',
      color: HOST_PALETTE.blue
    },
    {
      name: 'nvidia_smi_memory_total',
      display_name: 'GPU 显存总量',
      description: 'GPU 显存总量。采集单位是 MiB。多卡时取最高总量。',
      unit: 'mebibytes',
      query: 'max by (instance_id) (nvidia_smi_memory_total{instance_type="os", __$labels__})',
      color: HOST_PALETTE.blue
    },
    {
      name: 'nvidia_smi_temperature_gpu',
      display_name: 'GPU 温度',
      description: 'GPU 核心温度。多卡时取最高。',
      unit: 'celsius',
      query: 'max by (instance_id) (nvidia_smi_temperature_gpu{instance_type="os", __$labels__})',
      color: HOST_PALETTE.orange
    },
    {
      name: 'host_mem_swap_used_bytes',
      display_name: '交换已用',
      description: '主机已用交换空间。',
      unit: 'bytes',
      query: 'host_mem_swap_used_bytes{instance_type="os", __$labels__} or host_mem_swap_used_bytes_gauge{instance_type="os", __$labels__}',
      color: HOST_PALETTE.neutral
    },
    {
      name: 'host_mem_swap_total_bytes',
      display_name: '交换总量',
      description: '主机交换空间总量，用于换算交换已用占比。',
      unit: 'bytes',
      query: 'host_mem_swap_total_bytes{instance_type="os", __$labels__} or host_mem_swap_total_bytes_gauge{instance_type="os", __$labels__} or mem_swap_total{instance_type="os", __$labels__} or mem_swap_total_gauge{instance_type="os", __$labels__}',
      color: HOST_PALETTE.neutral
    },
    {
      name: 'mem_swap_free',
      display_name: '交换空闲',
      description: '主机空闲交换空间。没有已用字节时，用总量减空闲推算交换已用占比。',
      unit: 'bytes',
      query: 'mem_swap_free{instance_type="os", __$labels__} or mem_swap_free_gauge{instance_type="os", __$labels__}',
      color: HOST_PALETTE.neutral
    },
    {
      name: 'processes_blocked',
      display_name: '阻塞进程数',
      description: '当前处于不可中断等待（常与慢 I/O 相关）的进程数量。',
      unit: 'counts',
      query: 'processes_blocked{instance_type="os", __$labels__} or processes_blocked_gauge{instance_type="os", __$labels__}',
      color: HOST_PALETTE.orange,
      linuxOnly: true
    },
    {
      name: 'processes_zombies',
      display_name: '僵尸进程数',
      description: '当前处于僵尸状态的进程数量。',
      unit: 'counts',
      query: 'processes_zombies{instance_type="os", __$labels__} or processes_zombies_gauge{instance_type="os", __$labels__}',
      color: HOST_PALETTE.rose,
      linuxOnly: true
    },
    {
      name: 'processes_running',
      display_name: '运行中进程数',
      description: '当前处于运行状态的进程数量（Linux Telegraf processes；Windows WMI 为进程总数近似）。',
      unit: 'counts',
      query: 'processes_running{instance_type="os", __$labels__} or processes_running_gauge{instance_type="os", __$labels__} or processes_running_gauge_value{instance_type="os", config_type="windows_wmi", __$labels__}',
      color: HOST_PALETTE.neutral
    },
    {
      name: 'processes_sleeping',
      display_name: '休眠进程数',
      description: '当前处于休眠或等待状态的进程数量。',
      unit: 'counts',
      query: 'processes_sleeping{instance_type="os", __$labels__} or processes_sleeping_gauge{instance_type="os", __$labels__}',
      color: HOST_PALETTE.neutral,
      linuxOnly: true
    },
    {
      name: 'net_bytes_recv_rate',
      display_name: '网络入流量',
      description: '主机所有网卡接收字节速率合计。计算窗口与时间选择器一致。',
      unit: 'byteps',
      query: 'sum by (instance_id) (rate(net_bytes_recv{instance_type="os", __$labels__}[__$window__]) or rate(net_bytes_recv_gauge{instance_type="os", __$labels__}[__$window__]) or rate(net_bytes_recv_gauge_value{instance_type="os", config_type="windows_wmi", __$labels__}[__$window__]))',
      color: HOST_SERIES_COLOR.netIn
    },
    {
      name: 'net_bytes_sent_rate',
      display_name: '网络出流量',
      description: '主机所有网卡发送字节速率合计。计算窗口与时间选择器一致。',
      unit: 'byteps',
      query: 'sum by (instance_id) (rate(net_bytes_sent{instance_type="os", __$labels__}[__$window__]) or rate(net_bytes_sent_gauge{instance_type="os", __$labels__}[__$window__]) or rate(net_bytes_sent_gauge_value{instance_type="os", config_type="windows_wmi", __$labels__}[__$window__]))',
      color: HOST_SERIES_COLOR.netOut
    },
    {
      name: 'net_err_in_rate',
      display_name: '网络接收错误速率',
      description: '主机所有网卡接收错误包速率合计。计算窗口与时间选择器一致。',
      unit: 'cps',
      query: 'sum by (instance_id) (rate(net_err_in{instance_type="os", __$labels__}[__$window__]) or rate(net_err_in_gauge{instance_type="os", __$labels__}[__$window__]) or rate(net_err_in_gauge_value{instance_type="os", config_type="windows_wmi", __$labels__}[__$window__]))',
      color: HOST_PALETTE.orange
    },
    {
      name: 'net_err_out_rate',
      display_name: '网络发送错误速率',
      description: '主机所有网卡发送错误包速率合计。计算窗口与时间选择器一致。',
      unit: 'cps',
      query: 'sum by (instance_id) (rate(net_err_out{instance_type="os", __$labels__}[__$window__]) or rate(net_err_out_gauge{instance_type="os", __$labels__}[__$window__]) or rate(net_err_out_gauge_value{instance_type="os", config_type="windows_wmi", __$labels__}[__$window__]))',
      color: HOST_PALETTE.rose
    },
    {
      name: 'diskio_read_bytes_rate',
      display_name: '磁盘读吞吐',
      description: '主机所有磁盘设备读取字节速率合计。计算窗口与时间选择器一致。',
      unit: 'byteps',
      query: 'sum by (instance_id) (rate(diskio_read_bytes{instance_type="os", __$labels__}[__$window__]) or rate(diskio_read_bytes_total_gauge{instance_type="os", config_type!~"host_(aix|freebsd|hpux|solaris)_remote", __$labels__}[__$window__]) or rate(diskio_read_bytes_gauge_value{instance_type="os", config_type="windows_wmi", __$labels__}[__$window__]) or diskio_read_bytes_gauge{instance_type="os", config_type=~"host_(aix|freebsd|hpux|solaris)_remote", __$labels__})',
      color: HOST_SERIES_COLOR.diskRead
    },
    {
      name: 'diskio_write_bytes_rate',
      display_name: '磁盘写吞吐',
      description: '主机所有磁盘设备写入字节速率合计。计算窗口与时间选择器一致。',
      unit: 'byteps',
      query: 'sum by (instance_id) (rate(diskio_write_bytes{instance_type="os", __$labels__}[__$window__]) or rate(diskio_write_bytes_total_gauge{instance_type="os", config_type!~"host_(aix|freebsd|hpux|solaris)_remote", __$labels__}[__$window__]) or rate(diskio_write_bytes_gauge_value{instance_type="os", config_type="windows_wmi", __$labels__}[__$window__]) or diskio_write_bytes_gauge{instance_type="os", config_type=~"host_(aix|freebsd|hpux|solaris)_remote", __$labels__})',
      color: HOST_SERIES_COLOR.diskWrite
    }
  ],
  summaryCards: [
    {
      title: '运行时长',
      metric: 'system_uptime',
      unit: 's',
      formatter: 'duration',
      isUptimeCard: true,
      icon: 'clock',
      color: '#1F2329',
      guide: [{ label: '运行时长', detail: '主机自上次启动后的持续运行时间；期间发生重启会重新计时。' }],
      footer: [{ label: '启动', metric: 'system_uptime', formatter: 'startedAt' }]
    },
    {
      title: 'CPU 使用率',
      metric: 'cpu_usage_total',
      color: HOST_SERIES_COLOR.cpu,
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
      color: HOST_SERIES_COLOR.memUsed,
      icon: 'database',
      guide: [{ label: '内存使用率', detail: '已用内存占总内存的百分比;越高表示可用内存越少。' }],
      footer: [{ label: '可用内存', metric: 'mem_available', unit: 'bytes' }]
    },
    {
      title: '磁盘使用率',
      metric: 'disk_used_percent',
      color: HOST_SERIES_COLOR.diskUsed,
      icon: 'database',
      guide: [{
        label: '磁盘使用率',
        detail: '取各挂载点中最高的使用率，反映主机最满分区。持续偏高时先清理该分区或扩容，并对照下方磁盘吞吐是否伴随写入压力。'
      }]
    },
    {
      title: '1 分钟负载',
      metric: 'system_load1',
      color: HOST_SERIES_COLOR.load1,
      icon: 'node',
      linuxOnly: true,
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
        { metric: 'cpu_usage_total', label: 'CPU 使用率', color: HOST_SERIES_COLOR.cpu, unit: 'percent' },
        { metric: 'mem_used_percent', label: '内存使用率', color: HOST_SERIES_COLOR.memUsed, unit: 'percent' },
        { metric: 'disk_used_percent', label: '磁盘使用率', color: HOST_SERIES_COLOR.diskUsed, unit: 'percent' },
        { metric: 'cpu_usage_iowait_total', label: 'I/O Wait 占比', color: HOST_PALETTE.orange, unit: 'percent', linuxOnly: true }
      ]
    },
    {
      title: '系统负载趋势',
      subtitle: '1 / 5 / 15 分钟',
      metric: 'system_load1',
      linuxOnly: true,
      guide: [{ label: '系统负载', detail: '1 / 5 / 15 分钟平均负载（运行 + 等待的进程数）。持续偏高时结合 CPU 使用率与 I/O Wait 判断是算力不足还是等待 I/O。' }],
      series: [
        { metric: 'system_load1', label: '1 分钟', color: HOST_SERIES_COLOR.load1, unit: 'none' },
        { metric: 'system_load5', label: '5 分钟', color: HOST_SERIES_COLOR.load5, unit: 'none' },
        { metric: 'system_load15', label: '15 分钟', color: HOST_SERIES_COLOR.load15, unit: 'none' }
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
        { metric: 'net_bytes_recv_rate', label: '入流量', color: HOST_SERIES_COLOR.netIn, unit: 'byteps' },
        { metric: 'net_bytes_sent_rate', label: '出流量', color: HOST_SERIES_COLOR.netOut, unit: 'byteps' }
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
        { metric: 'net_err_in_rate', label: '接收错误', color: HOST_PALETTE.orange, unit: 'cps' },
        { metric: 'net_err_out_rate', label: '发送错误', color: HOST_PALETTE.rose, unit: 'cps' }
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
        { metric: 'diskio_read_bytes_rate', label: '读吞吐', color: HOST_SERIES_COLOR.diskRead, unit: 'byteps' },
        { metric: 'diskio_write_bytes_rate', label: '写吞吐', color: HOST_SERIES_COLOR.diskWrite, unit: 'byteps' }
      ]
    },
    {
      title: '进程异常趋势',
      subtitle: '阻塞与僵尸进程',
      metric: 'processes_blocked',
      linuxOnly: true,
      guide: [{
        label: '进程异常',
        detail: '阻塞进程持续非零多与慢 I/O / 不可中断等待相关；僵尸进程非零查父进程未回收。I/O Wait 见上方 KPI 与资源趋势（Linux）。'
      }],
      series: [
        { metric: 'processes_blocked', label: '阻塞进程', color: HOST_PALETTE.orange, unit: 'counts' },
        { metric: 'processes_zombies', label: '僵尸进程', color: HOST_PALETTE.rose, unit: 'counts' }
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
        { label: '用户态', metric: 'cpu_usage_user_total', color: HOST_PALETTE.blue, unit: 'percent' },
        { label: '内核态', metric: 'cpu_usage_system_total', color: HOST_PALETTE.indigo, unit: 'percent' },
        { label: 'I/O Wait 占比', metric: 'cpu_usage_iowait_total', color: HOST_PALETTE.orange, unit: 'percent', linuxOnly: true },
        { label: '其他', metric: 'cpu_usage_other_total', color: HOST_PALETTE.neutral, unit: 'percent' }
      ]
    }
  ],
  barPanels: [],
  details: []
};
