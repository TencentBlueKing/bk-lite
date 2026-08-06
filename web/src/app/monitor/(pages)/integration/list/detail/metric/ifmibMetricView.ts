import { GroupInfo, MetricItem } from '@/app/monitor/types';
import { MetricListItem } from '@/app/monitor/types/integration';

export const isIfmibMetric = (metric: MetricItem) => metric.is_ifmib === true;

export const getDefaultMetricGroupOpenState = (groups: MetricListItem[]) => (
  new Map(groups.map((group) => [group.id, true]))
);

/**
 * 指标页只反映当前下发流程是否采集 IF-MIB。开启时保留模板原有分组，
 * 以单指标来源标签区分公共 IF-MIB；关闭时隐藏该来源及由此产生的空分组。
 */
export const buildIfmibMetricView = (
  groups: GroupInfo[],
  metrics: MetricItem[],
  enabled: boolean
): MetricListItem[] => {
  const visibleMetrics = enabled
    ? metrics
    : metrics.filter((metric) => !isIfmibMetric(metric));

  return groups
    .map((group) => {
      const child = visibleMetrics
        .filter((metric) => String(metric.metric_group) === String(group.id))
        .map((metric) => ({
          ...metric,
          show_ifmib_source_tag: isIfmibMetric(metric)
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
};
