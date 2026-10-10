import type { ChartData } from '@/app/monitor/types';

export interface RangePoint {
  time: number;
  value: number;
}

export interface LabeledSeries {
  labels: Record<string, string>;
  points: RangePoint[];
}

export interface EntityTableRow {
  key: string;
  labels: Record<string, string>;
  values: Record<string, number | null>;
  series: Record<string, RangePoint[]>;
}

const SKIP_LABELS = new Set([
  '__name__',
  'instance_id',
  'instance_type',
  'collect_type',
  'config_type',
  'job',
  'host',
  'agent_id'
]);

const labelText = (labels: Record<string, string>, key: string) =>
  String(labels?.[key] || '').trim();

export const latestFinite = (points: RangePoint[] | undefined): number | null => {
  if (!points?.length) return null;
  for (let index = points.length - 1; index >= 0; index -= 1) {
    const value = points[index]?.value;
    if (Number.isFinite(value)) return value;
  }
  return null;
};

const preferPoints = (current: RangePoint[] | undefined, next: RangePoint[]) => {
  if (!current?.length) return next;
  return next.length > current.length ? next : current;
};

export const parseRangeSeries = (raw: unknown): LabeledSeries[] => {
  const result = (raw as { data?: { result?: unknown[] } })?.data?.result;
  if (!Array.isArray(result)) return [];
  return result
    .map((item) => {
      const series = item as {
        metric?: Record<string, string>;
        values?: Array<[number, string | number | null]>;
      };
      const points = (series.values || [])
        .map(([time, value]) => ({ time: Number(time), value: Number(value) }))
        .filter((point) => Number.isFinite(point.time) && Number.isFinite(point.value));
      return {
        labels: series.metric || {},
        points
      };
    })
    .filter((series) => series.points.length > 0);
};

export const seriesHasAnyLabel = (series: LabeledSeries[], keys: string[]) =>
  series.some((item) => keys.some((key) => labelText(item.labels, key)));

const ensureRow = (
  rows: Map<string, EntityTableRow>,
  key: string,
  labels: Record<string, string>,
  keepKeys: string[]
) => {
  const existing = rows.get(key);
  if (existing) {
    keepKeys.forEach((name) => {
      const value = labelText(labels, name);
      if (value && !existing.labels[name]) existing.labels[name] = value;
    });
    return existing;
  }
  const row: EntityTableRow = { key, labels: {}, values: {}, series: {} };
  keepKeys.forEach((name) => {
    const value = labelText(labels, name);
    if (value) row.labels[name] = value;
  });
  rows.set(key, row);
  return row;
};

const writeMetric = (row: EntityTableRow, metricKey: string, points: RangePoint[]) => {
  row.series[metricKey] = preferPoints(row.series[metricKey], points);
  row.values[metricKey] = latestFinite(row.series[metricKey]);
};

/** 磁盘：用量按 path/mount，IO 按 name/device 对齐到同一行。 */
export const buildDiskRows = (byMetric: Record<string, LabeledSeries[]>): EntityTableRow[] => {
  const rows = new Map<string, EntityTableRow>();
  const usageKeys = ['disk_used_percent', 'disk_inodes_used_percent'];
  const ioKeys = ['diskio_io_util', 'diskio_read_bytes_rate', 'diskio_write_bytes_rate'];
  const keep = ['path', 'mount', 'device', 'name', 'fstype'];

  usageKeys.forEach((metricKey) => {
    (byMetric[metricKey] || []).forEach((series) => {
      const path = labelText(series.labels, 'path') || labelText(series.labels, 'mount');
      const device = labelText(series.labels, 'device') || labelText(series.labels, 'name');
      const key = path ? `path:${path}` : device ? `dev:${device}` : '';
      if (!key) return;
      writeMetric(ensureRow(rows, key, series.labels, keep), metricKey, series.points);
    });
  });

  const matchIoRow = (labels: Record<string, string>) => {
    const device = labelText(labels, 'name') || labelText(labels, 'device');
    if (!device) return null;
    for (const row of rows.values()) {
      if (row.labels.device === device || row.labels.name === device) return row;
    }
    return null;
  };

  ioKeys.forEach((metricKey) => {
    (byMetric[metricKey] || []).forEach((series) => {
      const matched = matchIoRow(series.labels);
      const device = labelText(series.labels, 'name') || labelText(series.labels, 'device');
      const row = matched || (device ? ensureRow(rows, `dev:${device}`, series.labels, keep) : null);
      if (!row) return;
      writeMetric(row, metricKey, series.points);
    });
  });

  rows.forEach((row) => {
    if (!row.labels.path && row.labels.mount) row.labels.path = row.labels.mount;
    if (!row.labels.device && row.labels.name) row.labels.device = row.labels.name;
  });

  return Array.from(rows.values()).sort((left, right) => {
    const leftValue = left.values.disk_used_percent ?? left.values.diskio_io_util ?? -1;
    const rightValue = right.values.disk_used_percent ?? right.values.diskio_io_util ?? -1;
    return rightValue - leftValue;
  });
};

export const buildLabelRows = (
  byMetric: Record<string, LabeledSeries[]>,
  identityKey: string,
  sortKey: string
): EntityTableRow[] => {
  const rows = new Map<string, EntityTableRow>();
  Object.entries(byMetric).forEach(([metricKey, seriesList]) => {
    seriesList.forEach((series) => {
      const identity = labelText(series.labels, identityKey);
      if (!identity) return;
      const row = ensureRow(rows, `${identityKey}:${identity}`, series.labels, [identityKey]);
      writeMetric(row, metricKey, series.points);
    });
  });
  return Array.from(rows.values()).sort((left, right) => {
    const leftNumber = Number(left.labels[identityKey]);
    const rightNumber = Number(right.labels[identityKey]);
    if (identityKey === 'index' && Number.isFinite(leftNumber) && Number.isFinite(rightNumber)) {
      return leftNumber - rightNumber;
    }
    return (right.values[sortKey] ?? -1) - (left.values[sortKey] ?? -1);
  });
};

export const pointsToChartData = (
  seriesList: Array<{ points: RangePoint[] }>
): ChartData[] => {
  const byTime = new Map<number, ChartData>();
  seriesList.forEach((series, index) => {
    const valueKey = `value${index + 1}`;
    series.points.forEach((point) => {
      const row = byTime.get(point.time) || { time: point.time };
      row[valueKey] = point.value;
      byTime.set(point.time, row);
    });
  });
  return Array.from(byTime.values()).sort((left, right) => Number(left.time) - Number(right.time));
};

export const meaningfulLabels = (labels: Record<string, string>) =>
  Object.entries(labels).filter(([key, value]) => value && !SKIP_LABELS.has(key));
