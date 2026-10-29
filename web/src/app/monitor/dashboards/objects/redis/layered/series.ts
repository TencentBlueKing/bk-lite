import type { ChartData } from '@/app/monitor/types';
import type { MetricUnit } from '../../../shared/types';
import type { MetricSeries } from '../../common/simple-dashboard-core';
import { mergeChartSeries } from '../../../shared/utils/chart-data';
import { formatMetricValue } from '../../../shared/utils/format';
import { clipChartDataToWindow, type ProChartWindow } from '../../../shared/utils/pro-chart-window';
import { latestChartNumber } from '../../host/layered/readings';

export type RedisMetricMap = Record<string, MetricSeries>;

const INSTANT_OPS = 'redis_instantaneous_ops_per_sec';

const finiteNumber = (value: unknown): number | null => {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return null;
};

/** 采集时间偶发是毫秒。专业盘窗口按秒比较，不换算会把整段点裁成空。 */
const timeSeconds = (time: unknown): number | null => {
  const value = finiteNumber(time);
  if (value == null) return null;
  return value > 1e11 ? value / 1000 : value;
};

/** 0 是有效瞬时速率。只跳过非数字，不把 0 当成没采样。 */
const seriesNumber = (point: ChartData): number | null => {
  let bestKey = '';
  let best: number | null = null;
  Object.entries(point).forEach(([key, value]) => {
    if (!/^value\d+$/.test(key)) return;
    const numeric = finiteNumber(value);
    if (numeric == null) return;
    const index = Number(key.slice(5));
    const bestIndex = bestKey ? Number(bestKey.slice(5)) : Number.POSITIVE_INFINITY;
    if (bestKey === '' || index < bestIndex) {
      bestKey = key;
      best = numeric;
    }
  });
  return best;
};

export const redisPoints = (metricMap: RedisMetricMap, name: string): ChartData[] => {
  const series = metricMap[name];
  if (series?.loadState !== 'success' || !series.viewData?.length) return [];
  const result: ChartData[] = [];
  series.viewData.forEach((point) => {
    const time = timeSeconds(point.time);
    const value = seriesNumber(point);
    if (time == null || value == null) return;
    result.push({ time, value1: value });
  });
  return result;
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

const HIT_RATE_METRIC = 'redis_keyspace_hitrate';

/**
 * Telegraf 的 keyspace_hitrate 是 0–1 比例。展示和刻度都用百分数。
 * 已经大于 1.5 的读数视为百分数，不再乘。
 */
export const redisHitRatePercent = (metricMap: RedisMetricMap): number | null => {
  const raw = redisLatest(metricMap, HIT_RATE_METRIC);
  if (raw == null) return null;
  const scaled = raw <= 1.5 ? raw * 100 : raw;
  return Math.min(100, Math.max(0, scaled));
};

export const scaleHitRateChart = (data: ChartData[]): ChartData[] => data.map((point) => {
  const next: ChartData = { ...point };
  Object.keys(next).forEach((key) => {
    if (!/^value\d+$/.test(key)) return;
    const value = next[key];
    if (typeof value !== 'number' || !Number.isFinite(value)) return;
    const scaled = value <= 1.5 ? value * 100 : value;
    next[key] = Math.min(100, Math.max(0, scaled));
  });
  return next;
});

/** 各序列最新一点上的复制角色标签。没有标签时返回空。 */
export const redisReplicationLabels = (
  metricMap: RedisMetricMap
): Array<Record<string, string> | undefined> => {
  const labels: Array<Record<string, string> | undefined> = [];
  Object.values(metricMap).forEach((series) => {
    if (!series || series.loadState !== 'success') return;
    const points = series.viewData || [];
    for (let index = points.length - 1; index >= 0; index -= 1) {
      const metrics = points[index]?.seriesMetrics;
      if (!metrics) continue;
      const found = Object.values(metrics).filter((item) => item?.replication_role);
      if (!found.length) continue;
      labels.push(...found);
      break;
    }
  });
  return labels;
};

/**
 * 同一时刻的主偏移减去副本偏移。
 * 没有成对采样时返回 null。调用方写空态，不要把缺副本写成 0。
 */
export const replicationOffsetLag = (metricMap: RedisMetricMap): number | null => {
  const masterAt = new Map<number, number>();
  redisPoints(metricMap, 'redis_master_repl_offset').forEach((point) => {
    const time = Number(point.time);
    const value = point.value1;
    if (typeof value !== 'number' || !Number.isFinite(time)) return;
    masterAt.set(time, value);
  });
  let lag: number | null = null;
  redisPoints(metricMap, 'redis_slave_repl_offset').forEach((point) => {
    const time = Number(point.time);
    const slave = point.value1;
    if (typeof slave !== 'number' || !Number.isFinite(time)) return;
    const master = masterAt.get(time);
    if (master == null) return;
    lag = master - slave;
  });
  return lag;
};

/**
 * 折线先按专业盘窗口裁。瞬时命令速率若窗口裁完但序列里仍有点（时间单位或步长对不齐），
 * 仍把这些点画出来，避免接口有点、卡片空白。
 */
export const redisChartPoints = (
  metricMap: RedisMetricMap,
  items: ReadonlyArray<{ name: string; label: string }>,
  chartWindow: ProChartWindow | null,
  keepSeriesWhenWindowEmpty = false
) => {
  const all = redisMerged(metricMap, items);
  const clipped = clipChartDataToWindow(all, chartWindow);
  if (clipped.length > 0 || !keepSeriesWhenWindowEmpty) return clipped;
  return all;
};

export const redisInstantOps = INSTANT_OPS;

export const redisDisplay = (metricMap: RedisMetricMap, name: string, unit: MetricUnit) => {
  const value = redisLatest(metricMap, name);
  if (value == null) return { value: null, text: '--', unit: '' };
  const formatted = formatMetricValue(value, unit);
  return { value, text: formatted.value, unit: formatted.unit };
};

/** 图例/大数旁的产品读数。没有点时返回 null，调用方写空态，不把空写成 0。 */
export const redisProductText = (
  metricMap: RedisMetricMap,
  name: string,
  unit: MetricUnit,
  unitLabel?: string
) => {
  const shown = redisDisplay(metricMap, name, unit);
  if (shown.value == null) return null;
  if (unit === 'none') return shown.value.toFixed(2);
  const scaled = `${shown.text}${shown.unit && shown.unit !== '/s' ? shown.unit : ''}`;
  if (unitLabel) return `${scaled} ${unitLabel}`;
  return shown.unit ? `${shown.text}${shown.unit}` : shown.text;
};
