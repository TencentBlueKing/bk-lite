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

/**
 * 概览快捷卡读数：末点为 0 且窗内存在更高值时取窗内末个非 0（抗 scrape 末段掉零），
 * 否则与 latestFinite 相同。真实长期为 0 的序列仍显示 0。
 */
export const latestPreferSignal = (points: RangePoint[] | undefined): number | null => {
  const latest = latestFinite(points);
  if (latest == null) return null;
  if (latest !== 0) return latest;
  for (let index = (points?.length || 0) - 1; index >= 0; index -= 1) {
    const value = points![index]?.value;
    if (Number.isFinite(value) && value !== 0) return value;
  }
  return latest;
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
      const points = (series.values || []).flatMap(([time, value]) => {
        // fill_missing_points 的 null/'' 与真点交替。Number(null)===0 会画成密齿。与 renderChart 一样丢掉。
        if (value == null || value === '') return [];
        const parsedTime = Number(time);
        const parsedValue = typeof value === 'number' ? value : Number.parseFloat(value);
        if (!Number.isFinite(parsedTime) || !Number.isFinite(parsedValue)) return [];
        return [{ time: parsedTime, value: parsedValue }];
      });
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

const IO_METRIC_KEYS = [
  'diskio_read_bytes_rate',
  'diskio_write_bytes_rate',
  'diskio_io_util',
  'disk_read_latency',
  'disk_write_latency'
];

/** 只进设备行。挂载表不抄 IOPS。 */
const DEVICE_IOPS_KEYS = [
  'diskio_reads_rate',
  'diskio_writes_rate'
];

/** diskio 身份：优先 name，没有 name 才用 device。不做去分区号或补 /dev。 */
const diskIoIdentity = (labels: Record<string, string>) =>
  labelText(labels, 'name') || labelText(labels, 'device');

/**
 * 挂载的 device，其次 name，与设备名集合全等才返回。
 * 对不上返回空串，调用方不得据此估造吞吐。
 */
export const matchMountIoDevice = (
  labels: Record<string, string>,
  deviceNames: ReadonlySet<string>
) => {
  const candidates = [labelText(labels, 'device'), labelText(labels, 'name')].filter(Boolean);
  return candidates.find((name) => deviceNames.has(name)) || '';
};

/** 磁盘：用量按 path/mount，IO 按 name/device 对齐到同一行。 */
export const buildDiskRows = (byMetric: Record<string, LabeledSeries[]>): EntityTableRow[] => {
  const rows = new Map<string, EntityTableRow>();
  const usageKeys = ['disk_used_percent', 'disk_inodes_used_percent', 'disk_total', 'disk_free'];
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

  IO_METRIC_KEYS.forEach((metricKey) => {
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
    const total = row.values.disk_total;
    const free = row.values.disk_free;
    if (total != null && free != null && Number.isFinite(total) && Number.isFinite(free)) {
      row.values.disk_used = Math.max(0, total - free);
    }
  });

  return Array.from(rows.values()).sort((left, right) => {
    const leftValue = left.values.disk_used_percent ?? left.values.diskio_io_util ?? -1;
    const rightValue = right.values.disk_used_percent ?? right.values.diskio_io_util ?? -1;
    return rightValue - leftValue;
  });
};

/**
 * 挂载表：一行一个 path，只保留容量。
 * 关联设备只在 diskio 身份与该挂载的 device/name 完全一致时记到 labels.io_device。
 * 不把读/写、util、延迟抄进挂载行；对不上就不填关联名，也不另造无挂载行。
 */
export const buildMountDiskRows = (byMetric: Record<string, LabeledSeries[]>): EntityTableRow[] => {
  const rows = new Map<string, EntityTableRow>();
  const usageKeys = ['disk_used_percent', 'disk_inodes_used_percent', 'disk_total', 'disk_free'];
  const keep = ['path', 'mount', 'device', 'name', 'fstype'];

  usageKeys.forEach((metricKey) => {
    (byMetric[metricKey] || []).forEach((series) => {
      const path = labelText(series.labels, 'path') || labelText(series.labels, 'mount');
      if (!path) return;
      const row = ensureRow(rows, `path:${path}`, series.labels, keep);
      if (!row.labels.path) row.labels.path = path;
      writeMetric(row, metricKey, series.points);
    });
  });

  const deviceNames = new Set<string>();
  [...IO_METRIC_KEYS, ...DEVICE_IOPS_KEYS].forEach((metricKey) => {
    (byMetric[metricKey] || []).forEach((series) => {
      const name = diskIoIdentity(series.labels);
      if (name) deviceNames.add(name);
    });
  });

  rows.forEach((row) => {
    const matched = matchMountIoDevice(row.labels, deviceNames);
    if (matched) row.labels.io_device = matched;
  });

  rows.forEach((row) => {
    const total = row.values.disk_total;
    const free = row.values.disk_free;
    const percent = row.values.disk_used_percent;
    if (total != null && free != null && Number.isFinite(total) && Number.isFinite(free)) {
      row.values.disk_used = Math.max(0, total - free);
    } else if (
      row.values.disk_used == null
      && total != null
      && percent != null
      && Number.isFinite(total)
      && Number.isFinite(percent)
    ) {
      row.values.disk_used = Math.max(0, total * percent / 100);
    }
  });

  rows.forEach((row) => {
    const peakOrLatest = latestPreferSignal(row.series.disk_used_percent);
    if (peakOrLatest != null) row.values.disk_used_percent = peakOrLatest;
    const total = latestPreferSignal(row.series.disk_total);
    if (total != null) row.values.disk_total = total;
    const free = latestPreferSignal(row.series.disk_free);
    if (free != null) row.values.disk_free = free;
    if (row.values.disk_total != null && row.values.disk_free != null) {
      row.values.disk_used = Math.max(0, row.values.disk_total - row.values.disk_free);
    } else if (
      row.values.disk_used == null
      && row.values.disk_total != null
      && row.values.disk_used_percent != null
    ) {
      row.values.disk_used = Math.max(0, row.values.disk_total * row.values.disk_used_percent / 100);
    }
  });

  return Array.from(rows.values()).sort((left, right) => (
    (right.values.disk_used_percent ?? -1) - (left.values.disk_used_percent ?? -1)
  ));
};

const deviceThroughput = (row: EntityTableRow) => {
  const read = row.values.diskio_read_bytes_rate;
  const write = row.values.diskio_write_bytes_rate;
  const hasRead = read != null && Number.isFinite(read);
  const hasWrite = write != null && Number.isFinite(write);
  if (!hasRead && !hasWrite) return Number.NEGATIVE_INFINITY;
  return (hasRead ? read : 0) + (hasWrite ? write : 0);
};

/**
 * 设备表：一个 diskio 身份一行。收读/写吞吐、IOPS、util、延迟。
 * 表值用 latestPreferSignal（与挂载用量、网卡行相同），末点掉零时保留窗内信号。
 * 折线点列仍是原序列。读+写合计高的在前；没有吞吐的排在后面。IOPS 不写入挂载行。
 */
export const buildDiskDeviceRows = (byMetric: Record<string, LabeledSeries[]>): EntityTableRow[] => {
  const rows = new Map<string, EntityTableRow>();
  [...IO_METRIC_KEYS, ...DEVICE_IOPS_KEYS].forEach((metricKey) => {
    (byMetric[metricKey] || []).forEach((series) => {
      const name = diskIoIdentity(series.labels);
      if (!name) return;
      const row = ensureRow(rows, `dev:${name}`, series.labels, ['name', 'device']);
      row.labels.name = name;
      row.labels.device = name;
      writeMetric(row, metricKey, series.points);
    });
  });

  rows.forEach((row) => {
    Object.keys(row.series).forEach((metricKey) => {
      const preferred = latestPreferSignal(row.series[metricKey]);
      if (preferred != null) row.values[metricKey] = preferred;
    });
  });

  return Array.from(rows.values()).sort((left, right) => {
    const delta = deviceThroughput(right) - deviceThroughput(left);
    if (delta !== 0) return delta;
    return (left.labels.name || '').localeCompare(right.labels.name || '', undefined, { numeric: true });
  });
};

/** 设备默认：当前挂载的关联设备；没有或对不上时用读+写最忙的设备。 */
export const pickDefaultDiskDeviceKey = (
  mountRows: EntityTableRow[],
  deviceRows: EntityTableRow[],
  mountKey: string
) => {
  if (!deviceRows.length) return '';
  const mount = mountRows.find((row) => row.key === mountKey) || mountRows[0];
  const related = mount?.labels.io_device || '';
  if (related) {
    const match = deviceRows.find((row) => row.labels.name === related || row.labels.device === related);
    if (match) return match.key;
  }
  return deviceRows[0].key;
};

export const rowHasSeries = (row: EntityTableRow | undefined, keys: readonly string[]) => (
  Boolean(row && keys.some((key) => (row.series[key] || []).length > 0))
);

/** inode 列：没有任何读数就藏；Windows 即使采到了也不展示。 */
export const showDiskInodeColumn = (rows: EntityTableRow[], windowsHost: boolean) => {
  if (windowsHost) return false;
  return rows.some((row) => {
    const value = row.values.disk_inodes_used_percent;
    return value != null && Number.isFinite(value);
  });
};

export const showDiskFsTypeColumn = (rows: EntityTableRow[]) => (
  rows.some((row) => Boolean(row.labels.fstype))
);

export const entitySeriesIndicatesWindows = (byMetric: Record<string, LabeledSeries[]>) => (
  Object.values(byMetric).some((seriesList) => (
    seriesList.some((series) => /windows/i.test(labelText(series.labels, 'config_type')))
  ))
);

export const sumPoints = (left: RangePoint[] = [], right: RangePoint[] = []): RangePoint[] => {
  if (!left.length) return right.slice();
  if (!right.length) return left.slice();
  const map = new Map<number, number>();
  left.forEach((point) => {
    map.set(point.time, (map.get(point.time) || 0) + point.value);
  });
  right.forEach((point) => {
    map.set(point.time, (map.get(point.time) || 0) + point.value);
  });
  return Array.from(map.entries())
    .sort((a, b) => a[0] - b[0])
    .map(([time, value]) => ({ time, value }));
};

export const buildLabelRows = (
  byMetric: Record<string, LabeledSeries[]>,
  identityKey: string,
  sortKey: string,
  extraLabelKeys: string[] = []
): EntityTableRow[] => {
  const keepKeys = [identityKey, ...extraLabelKeys];
  const rows = new Map<string, EntityTableRow>();
  Object.entries(byMetric).forEach(([metricKey, seriesList]) => {
    seriesList.forEach((series) => {
      const identity = labelText(series.labels, identityKey);
      if (!identity) return;
      const row = ensureRow(rows, `${identityKey}:${identity}`, series.labels, keepKeys);
      writeMetric(row, metricKey, series.points);
    });
  });
  rows.forEach((row) => {
    Object.keys(row.series).forEach((metricKey) => {
      const preferred = latestPreferSignal(row.series[metricKey]);
      if (preferred != null) row.values[metricKey] = preferred;
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
