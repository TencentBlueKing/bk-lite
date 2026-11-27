export interface InstantSample {
  labels: Readonly<Record<string, string>>;
  evalSec: number;
  sample: number;
}

export interface NamedPoint {
  time: number;
  value: number;
}

export interface NamedSeries {
  name: string;
  points: NamedPoint[];
}

const isRecord = (value: unknown): value is Record<string, unknown> => (
  typeof value === 'object' && value !== null && !Array.isArray(value)
);

const finiteNumber = (value: unknown): number | null => {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
};

const resultRows = (payload: unknown): unknown[] => {
  if (!isRecord(payload)) return [];
  const data = isRecord(payload.data) ? payload.data : payload;
  if (Array.isArray(data.result)) return data.result;
  if (isRecord(data.data) && Array.isArray(data.data.result)) return data.data.result;
  return [];
};

const labelMap = (metric: unknown): Record<string, string> => {
  if (!isRecord(metric)) return {};
  const labels: Record<string, string> = {};
  Object.entries(metric).forEach(([key, value]) => {
    if (typeof value === 'string') {
      labels[key] = value;
      return;
    }
    const numeric = finiteNumber(value);
    if (numeric != null) labels[key] = String(numeric);
  });
  return labels;
};

const pair = (raw: unknown): { evalSec: number; sample: number } | null => {
  if (!Array.isArray(raw) || raw.length < 2) return null;
  const evalSec = finiteNumber(raw[0]);
  const sample = finiteNumber(raw[1]);
  if (evalSec == null || sample == null) return null;
  return { evalSec, sample };
};

/** 即时查询的 value[0] 是求值时刻，value[1] 是样本。源时间查询的样本本身就是 Unix 秒。 */
export const readInstantSamples = (payload: unknown): InstantSample[] => {
  const samples: InstantSample[] = [];
  resultRows(payload).forEach((row) => {
    if (!isRecord(row)) return;
    const parsed = pair(row.value);
    if (!parsed) return;
    samples.push({
      labels: labelMap(row.metric),
      evalSec: parsed.evalSec,
      sample: parsed.sample
    });
  });
  return samples;
};

export const readNamedSeries = (payload: unknown, label: string): NamedSeries[] => {
  const byName = new Map<string, Map<number, number>>();
  resultRows(payload).forEach((row) => {
    if (!isRecord(row)) return;
    const name = labelMap(row.metric)[label]?.trim();
    if (!name) return;
    const values = Array.isArray(row.values) ? row.values : (row.value != null ? [row.value] : []);
    const points = byName.get(name) ?? new Map<number, number>();
    values.forEach((item) => {
      const parsed = pair(item);
      if (!parsed) return;
      const previous = points.get(parsed.evalSec);
      points.set(
        parsed.evalSec,
        previous == null ? parsed.sample : Math.max(previous, parsed.sample)
      );
    });
    byName.set(name, points);
  });
  return Array.from(byName, ([name, points]) => ({
    name,
    points: Array.from(points, ([time, value]) => ({ time, value })).sort((left, right) => left.time - right.time)
  }));
};

export const batchNow = (groups: readonly (readonly InstantSample[])[]): number | null => {
  let now: number | null = null;
  for (const group of groups) {
    for (const sample of group) {
      if (!Number.isFinite(sample.evalSec)) continue;
      now = now == null ? sample.evalSec : Math.max(now, sample.evalSec);
    }
  }
  return now;
};
