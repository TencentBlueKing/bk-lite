import { GroupInfo, MetricItem } from '@/app/monitor/types';
import { MetricListItem } from '@/app/monitor/types/integration';

const IFMIB_DEVICE_TOTAL_METRICS = new Set([
  'device_total_incoming_traffic',
  'device_total_outgoing_traffic'
]);

export const isIfmibMetric = (metric: MetricItem) => metric.is_ifmib === true;

/** 默认只展开第一个可见分组，避免 IF-MIB 归并后首屏过长。 */
export const getDefaultMetricGroupOpenState = (groups: MetricListItem[]) => (
  new Map(groups.map((group, index) => [group.id, index === 0]))
);

const IFMIB_METRIC_GROUPS = [
  {
    id: '__ifmib_status_and_speed__',
    nameKey: 'monitor.integrations.ifmibMetricGroups.overview',
    metrics: new Set([
      'interface_ifAdminStatus',
      'interface_ifOperStatus',
      'interface_ifSpeed'
    ])
  },
  {
    id: '__ifmib_traffic__',
    nameKey: 'monitor.integrations.ifmibMetricGroups.traffic',
    metrics: new Set([
      'interface_ifInOctets',
      'interface_ifOutOctets',
      'interface_ifHCInOctets',
      'interface_ifHCOutOctets',
      ...IFMIB_DEVICE_TOTAL_METRICS
    ])
  },
  {
    id: '__ifmib_quality_and_packets__',
    nameKey: 'monitor.integrations.ifmibMetricGroups.packetsAndExceptions',
    metrics: new Set([
      'interface_ifInUcastPkts',
      'interface_ifOutUcastPkts',
      'interface_ifInErrors',
      'interface_ifOutErrors',
      'interface_ifInDiscards',
      'interface_ifOutDiscards'
    ])
  }
] as const;

const getIfmibMetricGroup = (metric: MetricItem) => (
  IFMIB_METRIC_GROUPS.find((group) => group.metrics.has(metric.name))
  // 通用表新增字段时，目录可能尚未声明展示分组；落入报文与异常组以免丢指标。
  || IFMIB_METRIC_GROUPS[2]
);

/**
 * 指标页只反映当前下发流程是否采集 IF-MIB。
 * 开启时：厂商/模板指标保持原分组并置顶；公共 IF-MIB 归并为少量业务组并置底，
 * 以来源组标签标识。关闭时隐藏 IF-MIB 指标及由此产生的空分组。
 */
export const buildIfmibMetricView = (
  groups: GroupInfo[],
  metrics: MetricItem[],
  enabled: boolean,
  translate?: (key: string) => string
): MetricListItem[] => {
  const nonIfmibMetrics = metrics.filter((metric) => !isIfmibMetric(metric));
  const grouped = groups
    .map((group) => {
      const child = nonIfmibMetrics
        .filter((metric) => String(metric.metric_group) === String(group.id))
        .map((metric) => ({
          ...metric,
          show_ifmib_source_tag: false
        }));

      return {
        ...group,
        id: String(group.id),
        name: group.name || '',
        display_name: (group as MetricListItem).display_name || group.name || '',
        is_pre: (group as MetricListItem).is_pre,
        is_ifmib_group: false,
        child
      };
    })
    .filter((group) => group.child.length > 0) as MetricListItem[];

  if (!enabled) {
    return grouped;
  }

  const ifmibGroups = IFMIB_METRIC_GROUPS.map((group) => {
    const label = translate?.(group.nameKey) || group.nameKey;
    const child = metrics
      .filter((metric) => (
        isIfmibMetric(metric) && getIfmibMetricGroup(metric).id === group.id
      ))
      .map((metric) => ({
        ...metric,
        show_ifmib_source_tag: false
      }));

    return {
      id: group.id,
      name: label,
      display_name: label,
      is_pre: true,
      is_ifmib_group: true,
      child
    };
  }).filter((group) => group.child.length > 0) as MetricListItem[];

  return [...grouped, ...ifmibGroups];
};
