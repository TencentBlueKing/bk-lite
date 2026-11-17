import type { ChartData } from '@/app/monitor/types';
import { formatMetricValue } from '../../../shared/utils/format';
import { mergeChartSeries } from '../../../shared/utils/chart-data';
import type { MetricUnit } from '../../../shared/types';
import { formatDuration, type MetricSeries } from '../../common/simple-dashboard-core';
import { deriveRatioPercent, numericValue } from '../../host/layered/readings';
import { mssqlLockedReading } from './display-units';
import { MSSQL_PRO_PALETTE, MSSQL_PRO_NAMES } from './queries';

export type MssqlMetricMap = Record<string, MetricSeries | undefined>;

const PLACEHOLDERS = new Set(['', '--', '-']);

const timeSeconds = (time: number) => (time > 1e11 ? time / 1000 : time);

/** 0 也是读数。字符串数字同样留下，避免把 "0" 当成没有点。 */
const asFinite = (raw: unknown): number | null => {
  if (typeof raw === 'number' && Number.isFinite(raw)) return raw;
  if (typeof raw === 'string' && raw.trim() !== '') {
    const parsed = Number(raw);
    if (Number.isFinite(parsed)) return parsed;
  }
  return null;
};

const pointNumber = (point: ChartData | undefined): number | null => {
  if (!point) return null;
  let bestKey = '';
  let best: number | null = null;
  Object.entries(point).forEach(([key, value]) => {
    if (!/^value\d+$/.test(key)) return;
    const numeric = asFinite(value);
    if (numeric == null) return;
    const index = Number(key.slice(5));
    const bestIndex = bestKey ? Number(bestKey.slice(5)) : Number.POSITIVE_INFINITY;
    if (best == null || index < bestIndex) {
      bestKey = key;
      best = numeric;
    }
  });
  return best;
};

const chartPoints = (points: ChartData[] | undefined): ChartData[] => {
  if (!points?.length) return [];
  const result: ChartData[] = [];
  points.forEach((point) => {
    const time = timeSeconds(Number(point.time));
    const value = pointNumber(point);
    if (!Number.isFinite(time) || value == null) return;
    result.push({ time, value1: value });
  });
  return result;
};

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
  chartPoints(metricMap[name]?.loadState === 'success' ? metricMap[name]?.viewData : [])
);

export const mssqlLatest = (metricMap: MssqlMetricMap, name: string): number | null => {
  const series = metricMap[name];
  if (!series || series.loadState !== 'success' || !series.viewData?.length) return null;
  for (let index = series.viewData.length - 1; index >= 0; index -= 1) {
    const value = pointNumber(series.viewData[index]);
    if (value != null) return value;
  }
  return null;
};

/** 有采样且全是 0。没有点不是 0。 */
export const mssqlSamplesAreFlatZero = (samples: readonly number[]) => (
  samples.length > 0 && samples.every((value) => value === 0)
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

/** 源端已是 0–100 的百分数。不再乘 100。正好为 0 时写成 0%，不写成 —。 */
export const formatPercentPoint = (value: number) => (
  value === 0 ? '0%' : `${value.toFixed(1)}%`
);

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

const dimensionLabel = (
  labels: Record<string, string> | undefined,
  dimension: string
) => {
  const named = String(labels?.[dimension] || '').trim();
  if (named) return named;
  if (!labels) return '';
  const extra = Object.entries(labels)
    .filter(([key]) => !['instance_id', 'instance_type', 'job', '__name__'].includes(key))
    .map(([, value]) => String(value || '').trim())
    .find(Boolean);
  return extra || '';
};

/** 按维度拆开。不把各类办事员加总成一条「实例内存」。 */
export const splitByDimension = (points: ChartData[], dimension: string) => {
  const buckets = new Map<string, ChartData[]>();
  points.forEach((point) => {
    const metrics = point.seriesMetrics as Record<string, Record<string, string>> | undefined;
    Object.entries(point).forEach(([valueKey, raw]) => {
      if (!/^value\d+$/.test(valueKey)) return;
      const value = asFinite(raw);
      if (value == null) return;
      const label = dimensionLabel(metrics?.[valueKey], dimension);
      if (!label) return;
      const time = timeSeconds(Number(point.time));
      if (!Number.isFinite(time)) return;
      const list = buckets.get(label) || [];
      list.push({ time, value1: value });
      buckets.set(label, list);
    });
  });
  return Array.from(buckets, ([label, data]) => ({ label, data }));
};

/** 维度名没落到标签上时，仍按数值列把线画出来，不把有数结果收成空壳。 */
const splitUnlabeled = (points: ChartData[]) => {
  const buckets = new Map<string, ChartData[]>();
  points.forEach((point) => {
    Object.entries(point).forEach(([valueKey, raw]) => {
      if (!/^value\d+$/.test(valueKey)) return;
      const value = asFinite(raw);
      if (value == null) return;
      const time = timeSeconds(Number(point.time));
      if (!Number.isFinite(time)) return;
      const list = buckets.get(valueKey) || [];
      list.push({ time, value1: value });
      buckets.set(valueKey, list);
    });
  });
  const rows = Array.from(buckets.values());
  if (rows.length <= 1) return rows.map((data) => ({ label: '内存占用', data }));
  return rows.map((data, index) => ({ label: `占用 ${index + 1}`, data }));
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
  const split = splitByDimension(points, 'clerk_type');
  const ranked = (split.length ? split : splitUnlabeled(points))
    .map((item) => ({ ...item, latest: lineLatest(item.data) }))
    .sort((left, right) => right.latest - left.latest)
    .slice(0, 8);
  const peak = ranked.reduce((max, item) => {
    item.data.forEach((point) => {
      const value = point.value1;
      if (typeof value === 'number' && Number.isFinite(value)) max = Math.max(max, Math.abs(value));
    });
    return max;
  }, 0);
  const formatReading = mssqlLockedReading('kibibytes', peak) ?? undefined;
  return {
    data: mergeChartSeries(ranked.map((item) => ({
      key: item.label,
      label: item.label,
      data: item.data
    }))),
    legends: ranked.map((item, index) => ({
      label: item.label,
      color: CLERK_COLORS[index % CLERK_COLORS.length],
      reading: formatReading && Number.isFinite(item.latest) ? formatReading(item.latest) : undefined
    })),
    formatReading
  };
};
