/** Host 磁盘挂载点 TopN，单机盘「磁盘与进程」区沿用。 */
export const HOST_DISK_TOP_N = 8;

interface GuideItem {
  label: string;
  detail: string;
}

export interface HostTopQuery {
  key: string;
  title: string;
  unit: string;
  color: string;
  query: string;
  labelKeys: string[];
  guide: GuideItem[];
}

const UNIX_REMOTE = 'config_type=~"host_(aix|freebsd|hpux|solaris)_remote"';

export const HOST_TOP_QUERIES: HostTopQuery[] = [
  {
    key: 'disk',
    title: '磁盘使用率 Top',
    unit: 'percent',
    color: '#F59E0B',
    labelKeys: ['path', 'device'],
    query: `topk(${HOST_DISK_TOP_N}, max by (path, device) (disk_used_percent{instance_type="os", __$labels__} or host_disk_used_percent_gauge{instance_type="os", __$labels__} or disk_used_percent_gauge_value{instance_type="os", config_type="windows_wmi", __$labels__} or disk_used_percent_gauge{instance_type="os", ${UNIX_REMOTE}, __$labels__}))`,
    guide: [{ label: '磁盘排行', detail: '按挂载点/设备使用率最高排序，定位最满分区。' }]
  }
];

export interface HostEntityMetricQuery {
  key: string;
  unit: 'percent' | 'byteps' | 'cps' | 'ms' | 'celsius' | 'watts' | 'mebibytes' | 'bytes' | 'counts' | 'none';
  /** 行身份与展示优先使用的标签，不发明 inventory 之外的指标名。 */
  labelKeys: string[];
  query: string;
}

const WIN_LOGICAL_DISK = 'instance=~"[A-Z]:"';

/**
 * 磁盘繁忙度。对齐 Telegraf host/os：Linux 用 rate(diskio_io_time)/10，
 * Windows 空闲时间优先，并用 unless 丢掉 io_time 零值。
 * 队列长度（avgqu-sz / iops_in_progress）采集侧未登记，专业盘不造假序列。
 */
const diskIoUtilEntityQuery = () => {
  const windowsIdle = `win_logicaldisk_idle_percent{instance_type="os", ${WIN_LOGICAL_DISK}, __$labels__}`;
  const windows = `label_replace(clamp_max(clamp_min(100 - ${windowsIdle}, 0), 100), "name", "$1", "instance", "(.*)")`;
  const idleNamed = `label_replace(${windowsIdle}, "name", "$1", "instance", "(.*)")`;
  const telegraf = `(rate(diskio_io_time{instance_type="os", __$labels__}[__$window__]) / 10)`;
  return [
    windows,
    `(${telegraf} unless on(instance_id, name) ${idleNamed})`,
    `(rate(diskio_io_time_ms_gauge{instance_type="os", __$labels__}[__$window__]) / 10)`,
    `diskio_io_util{instance_type="os", __$labels__}`,
    `diskio_io_util_gauge{instance_type="os", __$labels__}`,
    `diskio_io_util_gauge_value{instance_type="os", config_type="windows_wmi", __$labels__}`,
    `disk_tm_act_gauge{instance_type="os", ${UNIX_REMOTE}, __$labels__}`
  ].join(' or ');
};

/** 读/写 IOPS：Telegraf 计数、远程累计和 Windows 计数都折成每秒，不造 0。 */
const diskIopsEntityQuery = (kind: 'reads' | 'writes') => [
  `rate(diskio_${kind}{instance_type="os", __$labels__}[__$window__])`,
  `rate(diskio_${kind}_total_gauge{instance_type="os", __$labels__}[__$window__])`,
  `rate(diskio_${kind}_gauge_value{instance_type="os", config_type="windows_wmi", __$labels__}[__$window__])`
].join(' or ');

/** 已是毫秒的直出值优先；没有时再用 Telegraf / 远程累计时间除以次数。 */
const diskLatencyEntityQuery = (kind: 'read' | 'write') => {
  const windows = `label_replace(win_logicaldisk_${kind}_latency_ms{instance_type="os", ${WIN_LOGICAL_DISK}, __$labels__}, "name", "$1", "instance", "(.*)")`;
  const telegraf = `(rate(diskio_${kind}_time{instance_type="os", __$labels__}[__$window__]) / rate(diskio_${kind}s{instance_type="os", __$labels__}[__$window__]))`;
  const remote = `(rate(diskio_${kind}_time_ms_gauge{instance_type="os", __$labels__}[__$window__]) / rate(diskio_${kind}s_total_gauge{instance_type="os", __$labels__}[__$window__]))`;
  return [
    `disk_${kind}_latency{instance_type="os", __$labels__}`,
    `disk_${kind}_latency_gauge{instance_type="os", __$labels__}`,
    `disk_${kind}_latency_gauge_value{instance_type="os", config_type="windows_wmi", __$labels__}`,
    windows,
    `(${telegraf} unless on(instance_id, name) ${windows})`,
    remote
  ].join(' or ');
};

const netPacketRateQuery = (direction: 'recv' | 'sent') => (
  `rate(net_packets_${direction}{instance_type="os", __$labels__}[__$window__])`
  + ` or rate(net_packets_${direction}_gauge{instance_type="os", __$labels__}[__$window__])`
  + ` or rate(net_packets_${direction}_gauge_value{instance_type="os", config_type="windows_wmi", __$labels__}[__$window__])`
);

/** 磁盘表：保留 path/device/name，禁止 sum 成一条主机合计。 */
export const HOST_DISK_ENTITY_QUERIES: HostEntityMetricQuery[] = [
  {
    key: 'disk_used_percent',
    unit: 'percent',
    labelKeys: ['path', 'mount', 'device', 'fstype'],
    query: `disk_used_percent{instance_type="os", __$labels__} or host_disk_used_percent_gauge{instance_type="os", __$labels__} or disk_used_percent_gauge_value{instance_type="os", config_type="windows_wmi", __$labels__} or disk_used_percent_gauge{instance_type="os", ${UNIX_REMOTE}, __$labels__}`
  },
  {
    key: 'disk_total',
    unit: 'bytes',
    labelKeys: ['path', 'mount', 'device', 'fstype'],
    query: `disk_total{instance_type="os", __$labels__} or host_disk_total_bytes{instance_type="os", __$labels__} or disk_total_gauge_value{instance_type="os", config_type="windows_wmi", __$labels__} or disk_total_gauge{instance_type="os", ${UNIX_REMOTE}, __$labels__}`
  },
  {
    key: 'disk_free',
    unit: 'bytes',
    labelKeys: ['path', 'mount', 'device', 'fstype'],
    query: `disk_free{instance_type="os", __$labels__} or host_disk_free_bytes{instance_type="os", __$labels__} or disk_free_gauge_value{instance_type="os", config_type="windows_wmi", __$labels__} or disk_free_gauge{instance_type="os", ${UNIX_REMOTE}, __$labels__}`
  },
  {
    key: 'disk_inodes_used_percent',
    unit: 'percent',
    labelKeys: ['path', 'mount', 'device', 'fstype'],
    query: 'disk_inodes_used_percent{instance_type="os", __$labels__} or disk_inodes_used_percent_gauge{instance_type="os", __$labels__}'
  },
  {
    key: 'diskio_io_util',
    unit: 'percent',
    labelKeys: ['name', 'device'],
    query: diskIoUtilEntityQuery()
  },
  {
    key: 'diskio_read_bytes_rate',
    unit: 'byteps',
    labelKeys: ['name', 'device'],
    query: `rate(diskio_read_bytes{instance_type="os", __$labels__}[__$window__]) or rate(diskio_read_bytes_total_gauge{instance_type="os", config_type!~"host_(aix|freebsd|hpux|solaris)_remote", __$labels__}[__$window__]) or rate(diskio_read_bytes_gauge_value{instance_type="os", config_type="windows_wmi", __$labels__}[__$window__]) or diskio_read_bytes_gauge{instance_type="os", ${UNIX_REMOTE}, __$labels__}`
  },
  {
    key: 'diskio_write_bytes_rate',
    unit: 'byteps',
    labelKeys: ['name', 'device'],
    query: `rate(diskio_write_bytes{instance_type="os", __$labels__}[__$window__]) or rate(diskio_write_bytes_total_gauge{instance_type="os", config_type!~"host_(aix|freebsd|hpux|solaris)_remote", __$labels__}[__$window__]) or rate(diskio_write_bytes_gauge_value{instance_type="os", config_type="windows_wmi", __$labels__}[__$window__]) or diskio_write_bytes_gauge{instance_type="os", ${UNIX_REMOTE}, __$labels__}`
  },
  {
    key: 'diskio_reads_rate',
    unit: 'cps',
    labelKeys: ['name', 'device'],
    query: diskIopsEntityQuery('reads')
  },
  {
    key: 'diskio_writes_rate',
    unit: 'cps',
    labelKeys: ['name', 'device'],
    query: diskIopsEntityQuery('writes')
  },
  {
    key: 'disk_read_latency',
    unit: 'ms',
    labelKeys: ['name', 'device'],
    query: diskLatencyEntityQuery('read')
  },
  {
    key: 'disk_write_latency',
    unit: 'ms',
    labelKeys: ['name', 'device'],
    query: diskLatencyEntityQuery('write')
  }
];

/** 网卡表：按 interface 保留明细。调用方不得把无 interface 的合计序列画成单网卡。 */
export const HOST_NET_ENTITY_QUERIES: HostEntityMetricQuery[] = [
  {
    key: 'net_bytes_recv_rate',
    unit: 'byteps',
    labelKeys: ['interface'],
    query: 'rate(net_bytes_recv{instance_type="os", __$labels__}[__$window__]) or rate(net_bytes_recv_gauge{instance_type="os", __$labels__}[__$window__]) or rate(net_bytes_recv_gauge_value{instance_type="os", config_type="windows_wmi", __$labels__}[__$window__])'
  },
  {
    key: 'net_bytes_sent_rate',
    unit: 'byteps',
    labelKeys: ['interface'],
    query: 'rate(net_bytes_sent{instance_type="os", __$labels__}[__$window__]) or rate(net_bytes_sent_gauge{instance_type="os", __$labels__}[__$window__]) or rate(net_bytes_sent_gauge_value{instance_type="os", config_type="windows_wmi", __$labels__}[__$window__])'
  },
  {
    key: 'net_err_in_rate',
    unit: 'cps',
    labelKeys: ['interface'],
    query: 'rate(net_err_in{instance_type="os", __$labels__}[__$window__]) or rate(net_err_in_gauge{instance_type="os", __$labels__}[__$window__]) or rate(net_err_in_gauge_value{instance_type="os", config_type="windows_wmi", __$labels__}[__$window__])'
  },
  {
    key: 'net_err_out_rate',
    unit: 'cps',
    labelKeys: ['interface'],
    query: 'rate(net_err_out{instance_type="os", __$labels__}[__$window__]) or rate(net_err_out_gauge{instance_type="os", __$labels__}[__$window__]) or rate(net_err_out_gauge_value{instance_type="os", config_type="windows_wmi", __$labels__}[__$window__])'
  },
  {
    key: 'net_drop_in_rate',
    unit: 'cps',
    labelKeys: ['interface'],
    query: 'rate(net_drop_in{instance_type="os", __$labels__}[__$window__]) or rate(net_drop_in_gauge{instance_type="os", __$labels__}[__$window__]) or rate(net_drop_in_gauge_value{instance_type="os", config_type="windows_wmi", __$labels__}[__$window__])'
  },
  {
    key: 'net_drop_out_rate',
    unit: 'cps',
    labelKeys: ['interface'],
    query: 'rate(net_drop_out{instance_type="os", __$labels__}[__$window__]) or rate(net_drop_out_gauge{instance_type="os", __$labels__}[__$window__]) or rate(net_drop_out_gauge_value{instance_type="os", config_type="windows_wmi", __$labels__}[__$window__])'
  },
  {
    key: 'net_packets_recv_rate',
    unit: 'cps',
    labelKeys: ['interface'],
    query: netPacketRateQuery('recv')
  },
  {
    key: 'net_packets_sent_rate',
    unit: 'cps',
    labelKeys: ['interface'],
    query: netPacketRateQuery('sent')
  }
];

/** GPU：按 index 保留多卡，禁止 max 折成一台。 */
export const HOST_GPU_ENTITY_QUERIES: HostEntityMetricQuery[] = [
  {
    key: 'nvidia_smi_utilization_gpu',
    unit: 'percent',
    labelKeys: ['index', 'name', 'uuid'],
    query: 'nvidia_smi_utilization_gpu{instance_type="os", __$labels__}'
  },
  {
    key: 'nvidia_smi_memory_used',
    unit: 'mebibytes',
    labelKeys: ['index', 'name', 'uuid'],
    query: 'nvidia_smi_memory_used{instance_type="os", __$labels__}'
  },
  {
    key: 'nvidia_smi_memory_total',
    unit: 'mebibytes',
    labelKeys: ['index', 'name', 'uuid'],
    query: 'nvidia_smi_memory_total{instance_type="os", __$labels__}'
  },
  {
    key: 'nvidia_smi_temperature_gpu',
    unit: 'celsius',
    labelKeys: ['index', 'name', 'uuid'],
    query: 'nvidia_smi_temperature_gpu{instance_type="os", __$labels__}'
  }
];

/** 主机专业仪表盘进程层：按 process_name 聚合，并保留 procstat 的 pattern 标签供选中行展示匹配规则。 */
export const HOST_PROCESS_ENTITY_QUERIES: HostEntityMetricQuery[] = [
  {
    key: 'process_cpu_usage',
    unit: 'percent',
    labelKeys: ['process_name', 'pattern'],
    query: 'sum(procstat_cpu_usage{instance_type="process", __$labels__}) by (instance_id, process_name, pattern)'
  },
  {
    key: 'process_mem_usage',
    unit: 'percent',
    labelKeys: ['process_name', 'pattern'],
    query: 'sum(procstat_memory_usage{instance_type="process", __$labels__}) by (instance_id, process_name, pattern)'
  },
  {
    key: 'process_memory_rss',
    unit: 'bytes',
    labelKeys: ['process_name', 'pattern'],
    query: 'sum(procstat_memory_rss{instance_type="process", __$labels__}) by (instance_id, process_name, pattern)'
  },
  {
    key: 'process_num_threads',
    unit: 'counts',
    labelKeys: ['process_name', 'pattern'],
    query: 'sum(procstat_num_threads{instance_type="process", __$labels__}) by (instance_id, process_name, pattern)'
  },
  {
    key: 'process_num_fds',
    unit: 'counts',
    labelKeys: ['process_name', 'pattern'],
    query: 'sum(procstat_num_fds{instance_type="process", __$labels__}) by (instance_id, process_name, pattern)'
  },
  {
    key: 'process_alive',
    unit: 'none',
    labelKeys: ['process_name', 'pattern'],
    query: 'clamp_max(count(procstat_cpu_usage{instance_type="process", __$labels__}) by (instance_id, process_name, pattern), 1)'
  }
];

const pickEntityQueries = (
  queries: readonly HostEntityMetricQuery[],
  keys: readonly string[]
): HostEntityMetricQuery[] => {
  const wanted = new Set(keys);
  return queries.filter((query) => wanted.has(query.key));
};

/** 概览快捷卡 + 磁盘总使用率趋势。IO / inode / 延迟进磁盘页再拉。 */
export const HOST_DISK_OVERVIEW_ENTITY_KEYS = [
  'disk_used_percent',
  'disk_total',
  'disk_free'
] as const;

/** 概览最忙网卡与吞吐捷径。错误、丢包、包量进网络页再拉。 */
export const HOST_NET_OVERVIEW_ENTITY_KEYS = [
  'net_bytes_recv_rate',
  'net_bytes_sent_rate'
] as const;

/**
 * 概览 CPU 最高进程捷径，加上进程页签危度要用的内存。
 * RSS、线程、句柄、存活进进程页再拉。
 */
export const HOST_PROCESS_OVERVIEW_ENTITY_KEYS = [
  'process_cpu_usage',
  'process_mem_usage'
] as const;

export const HOST_DISK_OVERVIEW_ENTITY_QUERIES = pickEntityQueries(
  HOST_DISK_ENTITY_QUERIES,
  HOST_DISK_OVERVIEW_ENTITY_KEYS
);

export const HOST_NET_OVERVIEW_ENTITY_QUERIES = pickEntityQueries(
  HOST_NET_ENTITY_QUERIES,
  HOST_NET_OVERVIEW_ENTITY_KEYS
);

export const HOST_PROCESS_OVERVIEW_ENTITY_QUERIES = pickEntityQueries(
  HOST_PROCESS_ENTITY_QUERIES,
  HOST_PROCESS_OVERVIEW_ENTITY_KEYS
);
