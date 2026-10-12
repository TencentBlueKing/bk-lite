/** Host 磁盘挂载点 TopN（单机旧排行；舰队 Top N 不复用这条，见 fleet-overview）。 */
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
  unit: 'percent' | 'byteps' | 'cps' | 'celsius' | 'watts' | 'mebibytes';
  /** 行身份与展示优先使用的标签，不发明 inventory 之外的指标名。 */
  labelKeys: string[];
  query: string;
}

/** 磁盘表：保留 path/device/name，禁止 sum 成一条主机合计。 */
export const HOST_DISK_ENTITY_QUERIES: HostEntityMetricQuery[] = [
  {
    key: 'disk_used_percent',
    unit: 'percent',
    labelKeys: ['path', 'mount', 'device', 'fstype'],
    query: `disk_used_percent{instance_type="os", __$labels__} or host_disk_used_percent_gauge{instance_type="os", __$labels__} or disk_used_percent_gauge_value{instance_type="os", config_type="windows_wmi", __$labels__} or disk_used_percent_gauge{instance_type="os", ${UNIX_REMOTE}, __$labels__}`
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
    query: `diskio_io_util{instance_type="os", __$labels__} or diskio_io_util_gauge{instance_type="os", __$labels__} or (rate(diskio_io_time_ms_gauge{instance_type="os", __$labels__}[__$window__]) / 10) or diskio_io_util_gauge_value{instance_type="os", config_type="windows_wmi", __$labels__} or disk_tm_act_gauge{instance_type="os", ${UNIX_REMOTE}, __$labels__}`
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
  }
];

/** GPU 仅使用 inventory 已定义的 nvidia_smi_*；无 utilization_gpu 指标，不另造。 */
export const HOST_GPU_ENTITY_QUERIES: HostEntityMetricQuery[] = [
  {
    key: 'nvidia_smi_utilization_memory',
    unit: 'percent',
    labelKeys: ['index'],
    query: '100 * (nvidia_smi_memory_used{instance_type="os", __$labels__} / nvidia_smi_memory_total{instance_type="os", __$labels__})'
  },
  {
    key: 'nvidia_smi_temperature_gpu',
    unit: 'celsius',
    labelKeys: ['index'],
    query: 'nvidia_smi_temperature_gpu{instance_type="os", __$labels__}'
  },
  {
    key: 'nvidia_smi_power_draw',
    unit: 'watts',
    labelKeys: ['index'],
    query: 'nvidia_smi_power_draw{instance_type="os", __$labels__}'
  },
  {
    key: 'nvidia_smi_fan_speed_avg',
    unit: 'percent',
    labelKeys: ['index'],
    query: 'avg without(pstate) (nvidia_smi_fan_speed{instance_type="os", __$labels__})'
  }
];

/**
 * 舰队网卡错误：各实例 interface 合计后的 cps（收+发）。
 * 单位是速率，不是百分比。get_host_resource_top 不含此项，由列表页客户端排序。
 */
export const HOST_FLEET_NIC_ERROR_QUERY = '(sum by (instance_id) (rate(net_err_in{instance_type="os", __$labels__}[__$window__]) or rate(net_err_in_gauge{instance_type="os", __$labels__}[__$window__]) or rate(net_err_in_gauge_value{instance_type="os", config_type="windows_wmi", __$labels__}[__$window__]))) + (sum by (instance_id) (rate(net_err_out{instance_type="os", __$labels__}[__$window__]) or rate(net_err_out_gauge{instance_type="os", __$labels__}[__$window__]) or rate(net_err_out_gauge_value{instance_type="os", config_type="windows_wmi", __$labels__}[__$window__])))';
