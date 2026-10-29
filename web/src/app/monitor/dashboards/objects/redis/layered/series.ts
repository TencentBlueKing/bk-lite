import type { ChartData } from '@/app/monitor/types';
import type { MetricUnit } from '../../../shared/types';
import type { MetricSeries } from '../../common/simple-dashboard-core';
import { mergeChartSeries } from '../../../shared/utils/chart-data';
import { formatMetricValue } from '../../../shared/utils/format';
import { latestChartNumber, primaryChartSeries } from '../../host/layered/readings';

export type RedisMetricMap = Record<string, MetricSeries>;

export const redisPoints = (metricMap: RedisMetricMap, name: string): ChartData[] => {
  const series = metricMap[name];
  return series?.loadState === 'success' ? primaryChartSeries(series.viewData) : [];
};

/** maxmemory 最新值为 0：未配置上限。没有点时不判断，避免把加载中当成未配置。 */
export const redisMemoryLimitUnset = (metricMap: RedisMetricMap) => (
  latestChartNumber(redisPoints(metricMap, 'redis_maxmemory')) === 0
);

export const redisMerged = (
  metricMap: RedisMetricMap,
  items: ReadonlyArray<{ name: string; label: string }>
) => mergeChartSeries(items.flatMap((item) => {
  const data = redisPoints(metricMap, item.name);
  return data.length ? [{ key: item.name, label: item.label, data }] : [];
}));

export const redisLatest = (metricMap: RedisMetricMap, name: string) => (
  latestChartNumber(redisPoints(metricMap, name))
);

export const redisDisplay = (metricMap: RedisMetricMap, name: string, unit: MetricUnit) => {
  const value = redisLatest(metricMap, name);
  if (value == null) return { value: null, text: '--', unit: '' };
  const formatted = formatMetricValue(value, unit);
  return { value, text: formatted.value, unit: formatted.unit };
};
