import type { ChartData } from '@/app/monitor/types';
import { formatMetricValue } from '../../../shared/utils/format';
import { mergeChartSeries } from '../../../shared/utils/chart-data';
import type { MetricUnit } from '../../../shared/types';
import { formatDuration, type MetricSeries } from '../../common/simple-dashboard-core';
import { deriveRatioPercent, latestNumber, numericValue, primaryChartSeries } from '../../host/layered/readings';
import { MSSQL_PRO_PALETTE, MSSQL_PRO_NAMES } from './queries';

export type MssqlMetricMap = Record<string, MetricSeries | undefined>;

const PLACEHOLDERS = new Set(['', '--', '-']);

const timeSeconds = (time: number) => (time > 1e11 ? time / 1000 : time);

const hasAsciiToken = (text: string, token: string) => (
  new RegExp(`(?:^|[^a-z0-9])${token}(?:[^a-z0-9]|$)`, 'i').test(text)
);

/** 展示名和标识拼在一起。占位符不当成名字。 */
export const mssqlIdentityText = (
  ...parts: Array<string | number | null | undefined>
) => parts
  .map((part) => String(part ?? '').trim())
  .filter((part) => !PLACEHOLDERS.has(part))
  .join(' ');

/**
 * 只认对象名里的明确形态词。cluster / ha → 集群；standalone / single → 单机。
 * 短词按边界匹配，避免把无关词看成形态。没有这些词就不渲染。
 */
export const mssqlFormFromName = (text: string): '集群' | '单机' | null => {
  if (hasAsciiToken(text, 'cluster') || hasAsciiToken(text, 'ha')) return '集群';
  if (hasAsciiToken(text, 'standalone') || hasAsciiToken(text, 'single')) return '单机';
  return null;
};

/**
 * 采集点的数值是分钟。先按分钟理解，再换成可读时长。
 * 目录单位不在这里改。
 */
export const formatMssqlUptime = (minutes: number | null | undefined): string | null => {
  if (minutes == null || !Number.isFinite(minutes) || minutes < 0) return null;
  if (minutes === 0) return '0m';
  return formatDuration(minutes * 60);
};

export const mssqlPoints = (metricMap: MssqlMetricMap, name: string): ChartData[] => (
  primaryChartSeries(metricMap[name]?.loadState === 'success' ? metricMap[name]?.viewData : [])
    .map((point) => ({ time: timeSeconds(Number(point.time)), value1: point.value1 }))
);

export const mssqlLatest = (metricMap: MssqlMetricMap, name: string) => (
  latestNumber(metricMap[name])
);

/** 各时间桶次数相加，得到当前窗口内的次数。没有点返回 null，不造 0。 */
export const mssqlWindowCount = (metricMap: MssqlMetricMap, name: string): number | null => {
  const points = mssqlPoints(metricMap, name);
  if (!points.length) return null;
  return points.reduce((sum, point) => {
    const value = point.value1;
    return typeof value === 'number' && Number.isFinite(value) ? sum + Math.max(0, value) : sum;
  }, 0);
};

export const mssqlMerged = (
  metricMap: MssqlMetricMap,
  items: ReadonlyArray<{ name: string; label: string }>
) => mergeChartSeries(items.map((item) => ({
  key: item.name,
  label: item.label,
  data: mssqlPoints(metricMap, item.name)
})));

/** 次数桶。负的外推按 0。没有采样不补零线。 */
export const mssqlCountMerged = (
  metricMap: MssqlMetricMap,
  items: ReadonlyArray<{ name: string; label: string }>
) => mergeChartSeries(items.map((item) => ({
  key: item.name,
  label: item.label,
  data: mssqlPoints(metricMap, item.name).map((point) => ({
    ...point,
    value1: typeof point.value1 === 'number' ? Math.max(0, point.value1) : 0
  }))
})));

/** 全 0 的计数软顶，刻度落在 0、2、4。有起伏或没有点时不锁轴。 */
export const mssqlCountAxisBounds = (
  samples: readonly number[]
): { min: number; max: number } | null => {
  if (!samples.length) return null;
  let lo = samples[0];
  let hi = samples[0];
  samples.forEach((value) => {
    if (value < lo) lo = value;
    if (value > hi) hi = value;
  });
  if (lo === 0 && hi === 0) return { min: 0, max: 4 };
  return null;
};

export const formatCount = (value: number, unit: '个' | '次') => (
  `${Math.round(Math.max(0, value)).toLocaleString()} ${unit}`
);

/** 源端已是 0–100 的百分数。不再乘 100。 */
export const formatPercentPoint = (value: number) => `${value.toFixed(1)}%`;

/** 读数最多两位小数。整数不补 `.00`。 */
const tightenReading = (text: string) => text
  .replace(/(\.\d*?[1-9])0+(?=\D|$)/g, '$1')
  .replace(/\.0+(?=\D|$)/g, '');

export const joinMetric = (value: number, unit: MetricUnit) => {
  const formatted = formatMetricValue(value, unit);
  return `${tightenReading(formatted.value)}${formatted.unit || ''}`;
};

const finiteOrNull = (value: number | null | undefined) => (
  value != null && Number.isFinite(value) ? value : null
);

export interface VolumeUsage {
  /** empty：两侧都没有点。blank：有容量但分母为 0，或对不齐。ready：有使用率。 */
  state: 'empty' | 'blank' | 'ready';
  percent: number | null;
  used: number | null;
  total: number | null;
}

/** 已用 ÷ 总量。分母为 0 或没有总量时不给出 0%。 */
export const readVolumeUsage = (metricMap: MssqlMetricMap): VolumeUsage => {
  const used = finiteOrNull(mssqlLatest(metricMap, MSSQL_PRO_NAMES.volumeUsed));
  const total = finiteOrNull(mssqlLatest(metricMap, MSSQL_PRO_NAMES.volumeTotal));
  const usedPoints = mssqlPoints(metricMap, MSSQL_PRO_NAMES.volumeUsed);
  const totalPoints = mssqlPoints(metricMap, MSSQL_PRO_NAMES.volumeTotal);
  const hasSample = used != null || total != null || usedPoints.length > 0 || totalPoints.length > 0;
  if (!hasSample) return { state: 'empty', percent: null, used, total };
  const aligned = deriveRatioPercent(usedPoints, totalPoints);
  const last = aligned[aligned.length - 1];
  const alignedPercent = last ? numericValue(last) : null;
  if (alignedPercent != null) {
    return { state: 'ready', percent: alignedPercent, used, total };
  }
  if (used != null && total != null && total > 0) {
    return {
      state: 'ready',
      percent: Math.min(100, Math.max(0, (100 * used) / total)),
      used,
      total
    };
  }
  return { state: 'blank', percent: null, used, total };
};

export const volumeUsagePoints = (metricMap: MssqlMetricMap) => (
  deriveRatioPercent(
    mssqlPoints(metricMap, MSSQL_PRO_NAMES.volumeUsed),
    mssqlPoints(metricMap, MSSQL_PRO_NAMES.volumeTotal)
  )
);

const CLERK_COLORS = [
  MSSQL_PRO_PALETTE.blue,
  MSSQL_PRO_PALETTE.indigo,
  MSSQL_PRO_PALETTE.cyan,
  MSSQL_PRO_PALETTE.emerald,
  MSSQL_PRO_PALETTE.amber,
  MSSQL_PRO_PALETTE.orange,
  MSSQL_PRO_PALETTE.rose,
  MSSQL_PRO_PALETTE.neutral
];

/** 按 clerk_type 拆开。不把各类办事员加总成一条「实例内存」。 */
export const splitByDimension = (points: ChartData[], dimension: string) => {
  const buckets = new Map<string, ChartData[]>();
  points.forEach((point) => {
    const metrics = point.seriesMetrics as Record<string, Record<string, string>> | undefined;
    if (!metrics) return;
    Object.entries(metrics).forEach(([valueKey, labels]) => {
      const label = String(labels?.[dimension] || '').trim();
      if (!label) return;
      const raw = point[valueKey];
      if (typeof raw !== 'number' || !Number.isFinite(raw)) return;
      const time = timeSeconds(Number(point.time));
      if (!Number.isFinite(time)) return;
      const list = buckets.get(label) || [];
      list.push({ time, value1: raw });
      buckets.set(label, list);
    });
  });
  return Array.from(buckets, ([label, data]) => ({ label, data }));
};

const lineLatest = (data: ChartData[]) => {
  for (let index = data.length - 1; index >= 0; index -= 1) {
    const value = data[index]?.value1;
    if (typeof value === 'number' && Number.isFinite(value)) return value;
  }
  return Number.NEGATIVE_INFINITY;
};

export const clerkChart = (metricMap: MssqlMetricMap) => {
  const series = metricMap[MSSQL_PRO_NAMES.clerks];
  const points = series?.loadState === 'success' ? series.viewData : [];
  const ranked = splitByDimension(points, 'clerk_type')
    .map((item) => ({ ...item, latest: lineLatest(item.data) }))
    .sort((left, right) => right.latest - left.latest)
    .slice(0, 8);
  return {
    data: mergeChartSeries(ranked.map((item) => ({
      key: item.label,
      label: item.label,
      data: item.data
    }))),
    legends: ranked.map((item, index) => ({
      label: item.label,
      color: CLERK_COLORS[index % CLERK_COLORS.length],
      reading: Number.isFinite(item.latest) ? joinMetric(item.latest, 'kibibytes') : undefined
    }))
  };
};
