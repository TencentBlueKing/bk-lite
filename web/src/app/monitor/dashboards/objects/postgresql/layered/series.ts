import type { ChartData } from '@/app/monitor/types';
import type { MetricSeries } from '../../common/simple-dashboard-core';
import { mergeChartSeries } from '../../../shared/utils/chart-data';
import { latestNumber, primaryChartSeries } from '../../host/layered/readings';
import { cacheHitPercent, type CacheHitReading } from './cache-hit';

export type PostgresMetricMap = Record<string, MetricSeries | undefined>;

const timeSeconds = (time: number) => (time > 1e11 ? time / 1000 : time);

export const postgresPoints = (metricMap: PostgresMetricMap, name: string): ChartData[] => (
  primaryChartSeries(metricMap[name]?.loadState === 'success' ? metricMap[name]?.viewData : [])
    .map((point) => ({ time: timeSeconds(Number(point.time)), value1: point.value1 }))
);

export const postgresLatest = (metricMap: PostgresMetricMap, name: string) => (
  latestNumber(metricMap[name])
);

export const postgresMerged = (
  metricMap: PostgresMetricMap,
  items: ReadonlyArray<{ name: string; label: string }>
) => mergeChartSeries(items.flatMap((item) => {
  const data = postgresPoints(metricMap, item.name);
  return data.length ? [{ key: item.name, label: item.label, data }] : [];
}));

const byTime = (points: ChartData[]) => {
  const map = new Map<number, number>();
  points.forEach((point) => {
    const time = Number(point.time);
    const value = point.value1;
    if (!Number.isFinite(time) || typeof value !== 'number' || !Number.isFinite(value)) return;
    map.set(time, value);
  });
  return map;
};

/** 命中率折线。分母为 0 的时刻留空，不把 clamp 后的 0% 画进去。数值已是百分数。 */
export const cacheHitChartPoints = (metricMap: PostgresMetricMap): ChartData[] => {
  const hits = byTime(postgresPoints(metricMap, 'postgresql_blks_hit_rate'));
  const reads = byTime(postgresPoints(metricMap, 'postgresql_blks_read_rate'));
  const ratios = byTime(postgresPoints(metricMap, 'postgresql_cache_hit_ratio'));
  const times = Array.from(new Set([...hits.keys(), ...reads.keys()])).sort((left, right) => left - right);
  return times.flatMap((time) => {
    const hit = hits.get(time);
    const read = reads.get(time);
    if (hit == null || read == null) return [];
    const reading = cacheHitPercent(ratios.get(time), hit, read);
    if (reading.percent == null) return [];
    return [{ time, value1: reading.percent }];
  });
};

/** 卡面与折线右端用同一套成对采样。对不齐时才退回各序列最新值，分母仍须大于 0。 */
export const cacheHitReading = (metricMap: PostgresMetricMap): CacheHitReading => {
  const points = cacheHitChartPoints(metricMap);
  const last = points[points.length - 1];
  if (last && typeof last.value1 === 'number' && Number.isFinite(last.value1)) {
    return { percent: last.value1, denominatorZero: false };
  }
  return cacheHitPercent(
    postgresLatest(metricMap, 'postgresql_cache_hit_ratio'),
    postgresLatest(metricMap, 'postgresql_blks_hit_rate'),
    postgresLatest(metricMap, 'postgresql_blks_read_rate')
  );
};
