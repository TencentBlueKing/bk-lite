export const SPARKLINE_MAX_POINTS = 24;

export type SparklinePoint = number | null;

export interface MetricSparkline {
  name: string;
  group?: string;
  metric?: string;
  unit?: string;
  time?: string;
  range?: string;
  latest?: number | null;
  min?: number | null;
  max?: number | null;
  value?: SparklinePoint[];
}

export const formatSparklineNumber = (value: number): number => {
  if (!Number.isFinite(value)) return value;
  if (Number.isInteger(value) || Math.abs(value) >= 100) return Math.round(value);
  return Number(value.toFixed(1));
};

const formatClock = (unixSec: number): string => {
  const date = new Date(unixSec * 1000);
  if (Number.isNaN(date.getTime())) return '';
  const hh = String(date.getHours()).padStart(2, '0');
  const mm = String(date.getMinutes()).padStart(2, '0');
  return `${hh}:${mm}`;
};

const asUnixSeconds = (time: number): number => (time > 1_000_000_000_000 ? time / 1000 : time);

export const downsampleValues = (
  values: SparklinePoint[],
  maxPoints = SPARKLINE_MAX_POINTS,
): SparklinePoint[] => {
  if (!values.length) return [];
  const normalize = (value: SparklinePoint): SparklinePoint => {
    if (value == null || !Number.isFinite(value)) return null;
    return formatSparklineNumber(value);
  };
  if (values.length <= maxPoints) return values.map(normalize);
  const last = values.length - 1;
  return Array.from({ length: maxPoints }, (_, index) => {
    const sourceIndex = index === maxPoints - 1 ? last : Math.round((index * last) / (maxPoints - 1));
    return normalize(values[sourceIndex]);
  });
};

const finiteNumbers = (values: SparklinePoint[]): number[] =>
  values.filter((value): value is number => typeof value === 'number' && Number.isFinite(value));

const formatRange = (startSec: number, endSec: number): string => {
  const duration = Math.max(0, endSec - startSec);
  if (duration <= 0) return '';
  if (duration < 90 * 60) return `${Math.max(1, Math.round(duration / 60))}min`;
  if (duration < 48 * 3600) return `${Math.max(1, Math.round(duration / 3600))}h`;
  return `${Math.max(1, Math.round(duration / 86400))}d`;
};

export const sparklineFromValueSeries = (
  times: number[],
  values: SparklinePoint[],
  meta: Pick<MetricSparkline, 'name' | 'group' | 'metric' | 'unit'>,
  maxPoints = SPARKLINE_MAX_POINTS,
): MetricSparkline => {
  const sampled = downsampleValues(values, maxPoints);
  const numbers = finiteNumbers(sampled);
  const latest = numbers.length ? numbers[numbers.length - 1] : null;
  const min = numbers.length ? Math.min(...numbers) : null;
  const max = numbers.length ? Math.max(...numbers) : null;
  const start = times.length ? asUnixSeconds(times[0]) : NaN;
  const end = times.length ? asUnixSeconds(times[times.length - 1]) : NaN;
  const startClock = Number.isFinite(start) ? formatClock(start) : '';
  const endClock = Number.isFinite(end) ? formatClock(end) : '';
  const time =
    startClock && endClock ? (startClock === endClock ? startClock : `${startClock}~${endClock}`) : '';
  return {
    ...meta,
    time: time || undefined,
    range: Number.isFinite(start) && Number.isFinite(end) ? formatRange(start, end) || undefined : undefined,
    latest,
    min,
    max,
    value: sampled,
  };
};

const valueKeysFromRow = (row: Record<string, unknown>): string[] =>
  Object.keys(row)
    .filter((key) => /^value\d+$/.test(key))
    .sort((left, right) => Number(left.slice(5)) - Number(right.slice(5)));

/** 从监控折线 `ChartData[]` 抽第一条数值序列做成短 sparkline。 */
export const sparklineFromChartRows = (
  rows: Array<Record<string, unknown>>,
  meta: Pick<MetricSparkline, 'name' | 'group' | 'metric' | 'unit'>,
  maxPoints = SPARKLINE_MAX_POINTS,
): MetricSparkline | null => {
  if (!rows.length) return null;
  const keys = valueKeysFromRow(rows[0] || {});
  const valueKey = keys[0] || 'value1';
  const times: number[] = [];
  const values: SparklinePoint[] = [];
  for (const row of rows) {
    const time = Number(row.time);
    if (!Number.isFinite(time)) continue;
    times.push(time);
    const raw = row[valueKey];
    const numeric = typeof raw === 'number' ? raw : Number(raw);
    values.push(Number.isFinite(numeric) ? numeric : null);
  }
  if (!times.length) return null;
  return sparklineFromValueSeries(times, values, meta, maxPoints);
};
