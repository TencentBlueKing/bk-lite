export interface InstantPoint {
  labels: Record<string, string>;
  evalTime: number | null;
  sample: number | null;
}

export interface RangeLine {
  labels: Record<string, string>;
  points: Array<{ time: number; value: number }>;
}

export type InstantOutcome =
  | { kind: 'loading' }
  | { kind: 'error' }
  | { kind: 'ok'; series: InstantPoint[] };

export type RangeOutcome =
  | { kind: 'loading' }
  | { kind: 'error' }
  | { kind: 'ok'; series: RangeLine[] };

const isRecord = (value: unknown): value is Record<string, unknown> => (
  typeof value === 'object' && value !== null && !Array.isArray(value)
);

const finite = (value: unknown): number | null => {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return null;
};

const unixSeconds = (value: number): number => (value > 1e12 ? value / 1000 : value);

const readResultList = (raw: unknown): unknown[] => {
  if (!isRecord(raw)) return [];
  const data = raw.data;
  if (isRecord(data) && Array.isArray(data.result)) return data.result;
  if (isRecord(data) && isRecord(data.data) && Array.isArray(data.data.result)) return data.data.result;
  if (Array.isArray(raw.result)) return raw.result;
  return [];
};

const readLabels = (metric: unknown): Record<string, string> => {
  if (!isRecord(metric)) return {};
  const labels: Record<string, string> = {};
  Object.entries(metric).forEach(([key, value]) => {
    if (typeof value === 'string') labels[key] = value;
  });
  return labels;
};

const readPair = (pair: unknown): { left: number | null; right: number | null } => {
  if (!Array.isArray(pair) || pair.length < 2) return { left: null, right: null };
  return { left: finite(pair[0]), right: finite(pair[1]) };
};

/** 即时查询读 value[1]。value[0] 只作为求值时刻，不当成源时间。 */
export const parseInstantSeries = (raw: unknown): InstantPoint[] => (
  readResultList(raw).map((item) => {
    if (!isRecord(item)) return { labels: {}, evalTime: null, sample: null };
    const pair = readPair(item.value);
    return {
      labels: readLabels(item.metric),
      evalTime: pair.left == null ? null : unixSeconds(pair.left),
      sample: pair.right
    };
  })
);

/** 范围点的第一列是步长网格，数值在第二列。 */
export const parseRangeSeries = (raw: unknown): RangeLine[] => (
  readResultList(raw).flatMap((item) => {
    if (!isRecord(item) || !Array.isArray(item.values)) return [];
    const points: Array<{ time: number; value: number }> = [];
    item.values.forEach((pair) => {
      const read = readPair(pair);
      if (read.left == null || read.right == null) return;
      points.push({ time: unixSeconds(read.left), value: read.right });
    });
    return [{ labels: readLabels(item.metric), points }];
  })
);

export const newestEvalTime = (series: readonly InstantPoint[]): number | null => {
  let best: number | null = null;
  series.forEach((item) => {
    if (item.evalTime == null || !Number.isFinite(item.evalTime)) return;
    if (best == null || item.evalTime > best) best = item.evalTime;
  });
  return best;
};
