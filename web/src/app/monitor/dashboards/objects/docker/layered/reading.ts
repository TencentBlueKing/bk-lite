import type { InstantSample } from './samples';

export const DOCKER_BLANK = '—';
export const DOCKER_FRESH_FLOOR_SEC = 3 * 60;

export type GaugeReading =
  | { kind: 'missing' }
  | { kind: 'stale'; value: number; sourceSec: number }
  | { kind: 'fresh'; value: number; sourceSec: number };

export type ShareReading =
  | { kind: 'blank' }
  | { kind: 'ratio'; percent: number };

export type CollectionKind = 'not-connected' | 'unknown' | 'expired' | 'failed' | 'success';

export type Capability = boolean | 'unknown';

export interface Probe {
  kind: 'ok' | 'error';
  samples: readonly InstantSample[];
}

const IDENTITY_SKIP = new Set(['__name__']);

export const freshWindowSec = (intervalSec: number | null | undefined): number => {
  const interval = typeof intervalSec === 'number' && Number.isFinite(intervalSec) && intervalSec > 0
    ? intervalSec
    : 0;
  return Math.max(DOCKER_FRESH_FLOOR_SEC, interval * 2);
};

export const validSourceTime = (sourceSec: number, now: number): boolean => (
  Number.isFinite(sourceSec) && Number.isFinite(now) && sourceSec <= now
);

export const seriesIdentity = (labels: Readonly<Record<string, string>>): string => (
  Object.keys(labels)
    .filter((key) => !IDENTITY_SKIP.has(key))
    .sort()
    .map((key) => `${key}=${labels[key]}`)
    .join('\n')
);

const groupSamples = (rows: readonly InstantSample[]): Map<string, InstantSample[]> => {
  const grouped = new Map<string, InstantSample[]>();
  rows.forEach((row) => {
    const key = seriesIdentity(row.labels);
    const current = grouped.get(key);
    if (current) current.push(row);
    else grouped.set(key, [row]);
  });
  return grouped;
};

const unanimous = (rows: readonly InstantSample[]): InstantSample | null => {
  if (!rows.length) return null;
  const first = rows[0];
  const same = rows.every((row) => row.sample === first.sample);
  return same ? first : null;
};

/**
 * 同一标签集的数值和源时间配成一对。多条里只留源时间最晚、且时间校验通过的那一对。
 * 对不上标签的值和时间不拼在一起。
 */
export const currentOf = (
  values: readonly InstantSample[],
  times: readonly InstantSample[],
  now: number
): { value: number; sourceSec: number } | null => {
  const valueGroups = groupSamples(values);
  const timeGroups = groupSamples(times);
  let best: { value: number; sourceSec: number } | null = null;
  for (const [key, valueRows] of valueGroups) {
    const timeRows = timeGroups.get(key);
    if (!timeRows) continue;
    const valueRow = unanimous(valueRows);
    const timeRow = unanimous(timeRows);
    if (!valueRow || !timeRow) continue;
    if (!Number.isFinite(valueRow.sample) || !validSourceTime(timeRow.sample, now)) continue;
    if (!best || timeRow.sample > best.sourceSec) {
      best = { value: valueRow.sample, sourceSec: timeRow.sample };
    }
  }
  return best;
};

export const gaugeReading = (
  values: readonly InstantSample[],
  times: readonly InstantSample[],
  now: number | null,
  freshSec: number
): GaugeReading => {
  if (now == null) return { kind: 'missing' };
  const current = currentOf(values, times, now);
  if (!current) return { kind: 'missing' };
  if (now - current.sourceSec > freshSec) {
    return { kind: 'stale', value: current.value, sourceSec: current.sourceSec };
  }
  return { kind: 'fresh', value: current.value, sourceSec: current.sourceSec };
};

export const stoppedShare = (total: GaugeReading, stopped: GaugeReading): ShareReading => {
  if (total.kind !== 'fresh' || stopped.kind !== 'fresh') return { kind: 'blank' };
  if (total.value <= 0 || stopped.value < 0) return { kind: 'blank' };
  const percent = (100 * stopped.value) / total.value;
  if (!Number.isFinite(percent)) return { kind: 'blank' };
  return { kind: 'ratio', percent };
};

export const probeCapability = (probe: Probe): Capability => {
  if (probe.kind === 'error') return 'unknown';
  return probe.samples.length > 0;
};

export interface CollectionInput {
  hasInstance: boolean;
  successTimes: readonly number[];
  failTimes: readonly number[];
  now: number | null;
  freshSec: number;
}

/** 同一实例上多条源时间先校验，再取最晚的一条。成功值为 0 仍然算成功。 */
export const collectionStatus = (input: CollectionInput): CollectionKind => {
  if (!input.hasInstance) return 'not-connected';
  if (input.now == null) return 'unknown';
  const now = input.now;
  const events: { sec: number; kind: 'success' | 'fail' }[] = [];
  const success = input.successTimes.filter((sec) => validSourceTime(sec, now));
  const fail = input.failTimes.filter((sec) => validSourceTime(sec, now));
  if (success.length) events.push({ sec: Math.max(...success), kind: 'success' });
  if (fail.length) events.push({ sec: Math.max(...fail), kind: 'fail' });
  if (!events.length) return 'unknown';
  events.sort((left, right) => {
    if (left.sec !== right.sec) return right.sec - left.sec;
    if (left.kind === right.kind) return 0;
    return left.kind === 'fail' ? -1 : 1;
  });
  const latest = events[0];
  if (now - latest.sec > input.freshSec) return 'expired';
  if (latest.kind === 'fail') return 'failed';
  return 'success';
};

export const plottedDimensionNames = (
  names: readonly string[],
  selected: ReadonlySet<string>
): string[] => {
  if (selected.size === 0) return [...names];
  return names.filter((name) => selected.has(name));
};

export const dimensionUsesSideReadout = (count: number): boolean => count > 3;

export const containerNames = (groups: readonly (readonly InstantSample[])[]): string[] => {
  const names = new Set<string>();
  groups.forEach((group) => {
    group.forEach((sample) => {
      const name = sample.labels.container_name?.trim();
      if (name) names.add(name);
    });
  });
  return Array.from(names);
};

export const samplesForContainer = (
  samples: readonly InstantSample[],
  name: string
): InstantSample[] => samples.filter((sample) => sample.labels.container_name?.trim() === name);
