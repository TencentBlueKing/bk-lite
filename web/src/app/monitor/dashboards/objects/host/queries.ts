/** Host 磁盘挂载点 TopN */
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

export const HOST_TOP_QUERIES: HostTopQuery[] = [
  {
    key: 'disk',
    title: '磁盘使用率 Top',
    unit: 'percent',
    color: '#F59E0B',
    labelKeys: ['path', 'device'],
    query: `topk(${HOST_DISK_TOP_N}, max by (path, device) (disk_used_percent{instance_type="os", __$labels__} or host_disk_used_percent_gauge{instance_type="os", __$labels__} or disk_used_percent_gauge_value{instance_type="os", config_type="windows_wmi", __$labels__}))`,
    guide: [{ label: '磁盘排行', detail: '按挂载点/设备使用率最高排序，定位最满分区。' }]
  }
];
