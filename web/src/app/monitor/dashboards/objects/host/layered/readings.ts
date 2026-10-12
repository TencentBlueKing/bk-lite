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

export const numericValue = (point: ChartData | undefined): number | null => {
  if (!point) return null;
  const values = Object.entries(point)
    .filter(([key, value]) => /^value\d+$/.test(key) && typeof value === 'number' && Number.isFinite(value))
    .map(([, value]) => value as number);
  if (!values.length) return null;
  return values.reduce((sum, value) => sum + value, 0);
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

export const percentTone = (value: number | null) => {
  if (value == null) return undefined;
  if (value >= 90) return 'var(--color-fail)';
  if (value >= 80) return 'var(--color-warning)';
  return 'var(--color-success)';
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
    result.push({ time, value1: (100 * value) / base });
  });
  return result;
};
