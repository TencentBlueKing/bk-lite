import type { ChartData } from '@/app/monitor/types';
import { formatMetricValue } from '../../../shared/utils/format';
import type { MetricUnit } from '../../../shared/types';
import type { MetricSeries } from '../../common/simple-dashboard-core';
import { HOST_PALETTE } from '../config';

export const ROW_ACCENTS = [
  HOST_PALETTE.orange,
  HOST_PALETTE.emerald,
  HOST_PALETTE.blue,
  HOST_PALETTE.cyan,
  HOST_PALETTE.indigo
];

/**
 * 一个点上的读数。同一指标的 `or` 回退可能落成 value1/value2 两条序列，
 * 百分比和字节都不能相加，否则会双计。只取序号最小的那条。
 */
export const numericValue = (point: ChartData | undefined): number | null => {
  if (!point) return null;
  let bestKey = '';
  let best: number | null = null;
  Object.entries(point).forEach(([key, value]) => {
    if (!/^value\d+$/.test(key) || typeof value !== 'number' || !Number.isFinite(value)) return;
    const index = Number(key.slice(5));
    const bestIndex = bestKey ? Number(bestKey.slice(5)) : Number.POSITIVE_INFINITY;
    if (best == null || index < bestIndex) {
      bestKey = key;
      best = value;
    }
  });
  return best;
};

export const latestNumber = (
  series: Pick<MetricSeries, 'loadState' | 'viewData'> | undefined
): number | null => {
  if (!series || series.loadState !== 'success' || !series.viewData?.length) return null;
  for (let index = series.viewData.length - 1; index >= 0; index -= 1) {
    const value = numericValue(series.viewData[index]);
    if (value != null) return value;
  }
  return null;
};

export const metricHasPoints = (
  series: Pick<MetricSeries, 'loadState' | 'viewData'> | undefined
) => latestNumber(series) != null;

/**
 * 进程状态等计数卡：末点为 0 且窗内有非 0 时取末个非 0（抗 scrape 末段掉零）；
 * 全程为 0 仍显示 0；无读数返回 null。
 */
export const latestPreferCount = (
  series: Pick<MetricSeries, 'loadState' | 'viewData'> | undefined
): number | null => {
  if (!series || series.loadState !== 'success' || !series.viewData?.length) return null;
  const latest = latestNumber(series);
  if (latest == null) return null;
  if (latest !== 0) return latest;
  for (let index = series.viewData.length - 1; index >= 0; index -= 1) {
    const value = numericValue(series.viewData[index]);
    if (value != null && value !== 0) return value;
  }
  return latest;
};

/** 指标序列是否已进入 metricMap（成功或失败），用于状态卡等待 trend 批次。 */
export const metricSettled = (
  series: Pick<MetricSeries, 'loadState'> | undefined
) => series != null && (series.loadState === 'success' || series.loadState === 'error');

export const formatPercent = (value: number | null) => (
  value == null ? '--' : `${value.toFixed(1)}%`
);

export const formatPlain = (value: number | null, digits = 2) => {
  if (value == null) return '--';
  return Number(value.toFixed(digits)).toString();
};

export const formatUnit = (value: number | null, unit: MetricUnit) => {
  if (value == null) return '--';
  if (unit === 'percent') return formatPercent(value);
  if (unit === 'none') return formatPlain(value);
  const formatted = formatMetricValue(value, unit);
  return `${formatted.value}${formatted.unit || ''}`;
};

export const formatBytesPair = (used: number | null | undefined, total: number | null | undefined) => {
  const left = used != null && Number.isFinite(used) ? formatUnit(used, 'bytes') : null;
  const right = total != null && Number.isFinite(total) ? formatUnit(total, 'bytes') : null;
  if (left && right) return `${left} / ${right}`;
  if (right) return `— / ${right}`;
  if (left) return `${left} / —`;
  return '—';
};

const SHARED_BYTE_LABELS = ['Bytes', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB'] as const;

/** 已用/总量共用一个二进制单位，两侧都带单位，例如 `1.2 GiB / 4.0 GiB`。 */
export const formatSharedBytePair = (used: number, total: number | null) => {
  if (!Number.isFinite(used)) return '--';
  if (total == null || !Number.isFinite(total)) return formatUnit(used, 'bytes');
  const basis = Math.max(Math.abs(used), Math.abs(total), 1);
  let index = 0;
  let scaled = basis;
  while (scaled >= 1024 && index < SHARED_BYTE_LABELS.length - 1) {
    scaled /= 1024;
    index += 1;
  }
  const divisor = 1024 ** index;
  const side = (value: number) => (value / divisor).toFixed(1);
  const unit = SHARED_BYTE_LABELS[index];
  return `${side(used)} ${unit} / ${side(total)} ${unit}`;
};

/** 序列里时间最晚的一个数值。无点或全空返回 null。 */
export const latestChartNumber = (points: ChartData[] | undefined): number | null => {
  if (!points?.length) return null;
  let bestTime = Number.NEGATIVE_INFINITY;
  let best: number | null = null;
  points.forEach((point) => {
    const time = Number(point.time);
    const value = numericValue(point);
    if (!Number.isFinite(time) || value == null || time < bestTime) return;
    bestTime = time;
    best = value;
  });
  return best;
};

/** 合并进多线图之前先收成 value1，避免 or 回退的第二条被加进同一条线。 */
export const primaryChartSeries = (points: ChartData[] | undefined): ChartData[] => {
  if (!points?.length) return [];
  const result: ChartData[] = [];
  points.forEach((point) => {
    const time = Number(point.time);
    const value = numericValue(point);
    if (!Number.isFinite(time) || value == null) return;
    result.push({ time, value1: value });
  });
  return result;
};

/** 可用内存占比：同一时间点 available / total。对不齐的点丢掉，不补假序列。 */
export const deriveRatioPercent = (
  part: ChartData[] | undefined,
  total: ChartData[] | undefined
): ChartData[] => {
  if (!part?.length || !total?.length) return [];
  const totals = new Map<number, number>();
  total.forEach((point) => {
    const time = Number(point.time);
    const value = numericValue(point);
    if (Number.isFinite(time) && value != null && value > 0) totals.set(time, value);
  });
  const result: ChartData[] = [];
  part.forEach((point) => {
    const time = Number(point.time);
    const base = totals.get(time);
    const value = numericValue(point);
    if (!Number.isFinite(time) || base == null || value == null) return;
    const ratio = (100 * value) / base;
    result.push({ time, value1: Math.min(100, Math.max(0, ratio)) });
  });
  return result;
};

/**
 * 已用占比 = 100 - available/total。
 * mem_used_percent 与 MemAvailable 不是同一口径：前者常把可回收缓存算进已用，
 * 后者又把这段算进可用，两条百分比并列会超过 100。
 * 有总量时图表改用这一对互补占比，与采集侧 used = total - available 一致。
 */
export const deriveMemoryUsageShares = (
  available: ChartData[] | undefined,
  total: ChartData[] | undefined
): { used: ChartData[]; available: ChartData[] } => {
  const availableShare = deriveRatioPercent(available, total);
  const used = availableShare.flatMap((point) => {
    const ratio = numericValue(point);
    if (ratio == null) return [];
    return [{ time: point.time, value1: Math.min(100, Math.max(0, 100 - ratio)) }];
  });
  return { used, available: availableShare };
};

/**
 * 概览、性能和页签色点共用的内存读数。
 * 有 available/total 时已用 = 100 − 可用占比，可用是同一对比值；
 * 缺总量时已用回退采集 mem_used_percent，可用留空，不另造百分比。
 */
export const resolveMemoryUsage = (
  available: ChartData[] | undefined,
  total: ChartData[] | undefined,
  collectedUsed?: Pick<MetricSeries, 'loadState' | 'viewData'>
) => {
  const shares = deriveMemoryUsageShares(available, total);
  if (shares.used.length) {
    return {
      used: shares.used,
      available: shares.available,
      usedNow: latestChartNumber(shares.used),
      availableNow: latestChartNumber(shares.available),
      complementary: true
    };
  }
  return {
    used: primaryChartSeries(collectedUsed?.viewData),
    available: [] as ChartData[],
    usedNow: latestNumber(collectedUsed),
    availableNow: null as number | null,
    complementary: false
  };
};

/** 折线、图例、tooltip 色点共用的序列色。按系列名取，避免 tooltip 落到默认色板。 */
export const seriesMarkerColor = (
  legends: Array<{ label: string; color: string; title?: string }>,
  seriesName: string | undefined,
  seriesIndex: number | undefined,
  fallback: unknown
) => {
  if (seriesName) {
    const match = legends.find((item) => item.label === seriesName || item.title === seriesName);
    if (match?.color) return match.color;
  }
  if (typeof seriesIndex === 'number' && legends[seriesIndex]?.color) {
    return legends[seriesIndex].color;
  }
  return typeof fallback === 'string' && fallback ? fallback : 'var(--color-text-3)';
};
