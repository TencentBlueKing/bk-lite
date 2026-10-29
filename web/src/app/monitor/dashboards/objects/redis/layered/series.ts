import type { ChartData } from '@/app/monitor/types';
import type { MetricUnit } from '../../../shared/types';
import type { MetricSeries } from '../../common/simple-dashboard-core';
import { getLatestChartValue, mergeChartSeries } from '../../../shared/utils/chart-data';
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
const HITS_RATE_METRIC = 'redis_keyspace_hits_rate';
const MISSES_RATE_METRIC = 'redis_keyspace_misses_rate';

/**
 * Telegraf 的 keyspace_hitrate 是 0–1 比例。展示和刻度都用百分数。
 * 已经大于 1.5 的读数视为百分数，不再乘。
 * 专业盘主路径不用这条累计值，只在窗口命中/未命中不成对时兜底。
 */
export const scaleRatioToPercent = (raw: number): number => {
  const scaled = raw <= 1.5 ? raw * 100 : raw;
  return Math.min(100, Math.max(0, scaled));
};

export const redisHitRatePercent = (metricMap: RedisMetricMap): number | null => {
  const raw = redisLatest(metricMap, HIT_RATE_METRIC);
  if (raw == null) return null;
  return scaleRatioToPercent(raw);
};

export const scaleHitRateChart = (data: ChartData[]): ChartData[] => data.map((point) => {
  const next: ChartData = { ...point };
  Object.keys(next).forEach((key) => {
    if (!/^value\d+$/.test(key)) return;
    const value = next[key];
    if (typeof value !== 'number' || !Number.isFinite(value)) return;
    next[key] = scaleRatioToPercent(value);
  });
  return next;
});

const roundPercent = (value: number) => Math.round(value * 10) / 10;

const ratioFromCounts = (hits: number, misses: number) => {
  const hit = Math.max(hits, 0);
  const miss = Math.max(misses, 0);
  const total = hit + miss;
  if (total <= 0) return null;
  const hitPercent = roundPercent((hit / total) * 100);
  const penetrationPercent = roundPercent(100 - hitPercent);
  return { hitPercent, penetrationPercent };
};

export interface RedisWindowKeyspace {
  /** 与穿透率同一对窗口命中/未命中。0/0 时为 null。 */
  hitPercent: number | null;
  penetrationPercent: number | null;
  /** 命中频率和未命中频率都有最新点，含两边都是 0。 */
  bothKnown: boolean;
  /** 已经是 0–100 的命中率折线，右端与 hitPercent 对齐。 */
  points: ChartData[];
}

/**
 * 命中率和穿透率共用当前窗口的 hits/misses 速率。
 * 展示值先四舍五入到 1 位，穿透率取 100 减命中率，两张卡相加是 100.0。
 */
export const redisWindowKeyspace = (
  metricMap: RedisMetricMap,
  chartWindow: ProChartWindow | null
): RedisWindowKeyspace => {
  const hitPoints = redisPoints(metricMap, HITS_RATE_METRIC);
  const missPoints = redisPoints(metricMap, MISSES_RATE_METRIC);
  const missAt = new Map<number, number>();
  missPoints.forEach((point) => {
    const time = Number(point.time);
    if (typeof point.value1 !== 'number' || !Number.isFinite(time)) return;
    missAt.set(time, point.value1);
  });
  const paired: ChartData[] = [];
  hitPoints.forEach((point) => {
    const time = Number(point.time);
    const hits = point.value1;
    const misses = missAt.get(time);
    if (typeof hits !== 'number' || misses == null || !Number.isFinite(time)) return;
    const ratio = ratioFromCounts(hits, misses);
    if (!ratio) return;
    paired.push({ time, value1: ratio.hitPercent });
  });
  const hitsLatest = redisLatest(metricMap, HITS_RATE_METRIC);
  const missesLatest = redisLatest(metricMap, MISSES_RATE_METRIC);
  const bothKnown = hitsLatest != null && missesLatest != null;
  const latestRatio = bothKnown ? ratioFromCounts(hitsLatest, missesLatest) : null;
  const points = clipChartDataToWindow(paired, chartWindow);
  if (latestRatio) {
    const last = points[points.length - 1];
    const hitTime = Number(hitPoints[hitPoints.length - 1]?.time);
    const missTime = Number(missPoints[missPoints.length - 1]?.time);
    const time = Math.max(hitTime, missTime);
    const inside = chartWindow == null
      || (Number.isFinite(time) && time >= chartWindow.startSec && time <= chartWindow.endSec);
    if (inside && Number.isFinite(time) && (!last || last.value1 !== latestRatio.hitPercent || Number(last.time) !== time)) {
      const index = points.findIndex((point) => Number(point.time) === time);
      const next = { time, value1: latestRatio.hitPercent };
      if (index >= 0) points[index] = next;
      else points.push(next);
      points.sort((left, right) => Number(left.time) - Number(right.time));
    }
  }
  if (!bothKnown || !latestRatio) {
    return {
      hitPercent: null,
      penetrationPercent: null,
      bothKnown,
      points: bothKnown ? [] : points
    };
  }
  return {
    hitPercent: latestRatio.hitPercent,
    penetrationPercent: latestRatio.penetrationPercent,
    bothKnown: true,
    points
  };
};

/** 窗口有成对采样时用窗口命中率。0/0 保持空。窗口确实没有采样时才回落到累计命中率。 */
export const redisShownHitPercent = (
  metricMap: RedisMetricMap,
  chartWindow: ProChartWindow | null,
  windowSettled: boolean
) => {
  const keyspace = redisWindowKeyspace(metricMap, chartWindow);
  if (keyspace.hitPercent != null || keyspace.bothKnown || !windowSettled) {
    return { percent: keyspace.hitPercent, fallback: false, keyspace };
  }
  const percent = redisHitRatePercent(metricMap);
  return { percent, fallback: percent != null, keyspace };
};

/** 传统盘 KPI 的原始序列仍是 0–1。主读数换成真实百分数，查询本身不动。 */
export const classicRedisHitRateDisplay = (
  trendData: ChartData[]
): { value: string; unit: string } | null => {
  if (!trendData.length) return null;
  const raw = getLatestChartValue(trendData);
  if (!Number.isFinite(raw)) return null;
  return { value: scaleRatioToPercent(raw).toFixed(1), unit: '%' };
};

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
