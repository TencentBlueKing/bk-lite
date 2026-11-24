/** 源样本时间。只在通过有限、非未来、秒级校验后得到。 */
export type EsSourceTime = number & { readonly __brand: 'EsSourceTime' };

export type HealthCode = 1 | 2 | 3;

export type HeapBand = '充足' | '接近' | '高压';

export type EsFormat = 'percent' | 'counts' | 'bytes' | 'byteps' | 'cps' | 'msps';

export interface AlignedSample {
  labels: Record<string, string>;
  value: number | null;
  sourceTime: number | null;
}

export interface FreshNumber {
  value: number;
  sourceTime: EsSourceTime;
  label?: string;
}

export type HealthFace =
  | { kind: 'value'; code: HealthCode; sourceTime: EsSourceTime }
  | { kind: 'missing' };

export type CollectionKind = 'not-attached' | 'unknown' | 'expired' | 'failed' | 'success';

export type CollectionFace =
  | { kind: 'not-attached' }
  | { kind: 'unknown' }
  | { kind: 'expired'; sourceTime: EsSourceTime }
  | { kind: 'failed'; sourceTime: EsSourceTime }
  | { kind: 'success'; sourceTime: EsSourceTime };

export const LOOKBACK_SECONDS = 20 * 60;
export const CAPABILITY_SECONDS = 24 * 60 * 60;
export const DEFAULT_FRESH_SECONDS = 3 * 60;
const SOURCE_TIME_FLOOR = 1e9;

export const freshWindowSeconds = (intervalSeconds: number | null | undefined): number => {
  const interval = typeof intervalSeconds === 'number' && Number.isFinite(intervalSeconds) && intervalSeconds > 0
    ? intervalSeconds
    : 0;
  return Math.max(DEFAULT_FRESH_SECONDS, interval * 2);
};

export const isHealthCode = (value: number): value is HealthCode => (
  value === 1 || value === 2 || value === 3
);

/** 拒绝缺失、非有限、明显未来，以及小到不可能是 Unix 秒的数。 */
export const isEsSourceTime = (
  value: number,
  nowSeconds: number,
  skewSeconds = 5
): value is EsSourceTime => (
  Number.isFinite(value)
  && Number.isFinite(nowSeconds)
  && value >= SOURCE_TIME_FLOOR
  && value <= nowSeconds + skewSeconds
);

export const labelIdentity = (labels: Record<string, string>): string => (
  Object.keys(labels)
    .filter((key) => key !== '__name__')
    .sort()
    .map((key) => `${key}=${labels[key]}`)
    .join('\n')
);

/** 同一标签键才配成一对。缺值或缺源时间留空，不拿另一条序列补。 */
export const alignSamples = (
  values: readonly { labels: Record<string, string>; sample: number | null }[],
  times: readonly { labels: Record<string, string>; sample: number | null }[]
): AlignedSample[] => {
  const valueBy = new Map<string, { labels: Record<string, string>; sample: number | null }>();
  const timeBy = new Map<string, { labels: Record<string, string>; sample: number | null }>();
  values.forEach((row) => valueBy.set(labelIdentity(row.labels), row));
  times.forEach((row) => timeBy.set(labelIdentity(row.labels), row));
  const keys = new Set([...valueBy.keys(), ...timeBy.keys()]);
  return [...keys].map((key) => {
    const valueRow = valueBy.get(key);
    const timeRow = timeBy.get(key);
    return {
      labels: valueRow?.labels ?? timeRow?.labels ?? {},
      value: valueRow?.sample ?? null,
      sourceTime: timeRow?.sample ?? null
    };
  });
};

const freshRows = (
  rows: readonly AlignedSample[],
  nowSeconds: number,
  freshSeconds: number,
  skewSeconds: number
): FreshNumber[] => {
  const fresh: FreshNumber[] = [];
  rows.forEach((row) => {
    const source = row.sourceTime;
    const value = row.value;
    if (source == null || value == null) return;
    if (!isEsSourceTime(source, nowSeconds, skewSeconds)) return;
    if (nowSeconds - source > freshSeconds) return;
    const node = row.labels.node_name;
    fresh.push({
      value,
      sourceTime: source,
      label: node || undefined
    });
  });
  return fresh;
};

export const freshNumbers = (
  rows: readonly AlignedSample[],
  nowSeconds: number,
  freshSeconds: number,
  skewSeconds = 5
): FreshNumber[] => freshRows(rows, nowSeconds, freshSeconds, skewSeconds);

export const aggregateClusterHealth = (
  rows: readonly AlignedSample[],
  nowSeconds: number,
  freshSeconds: number,
  skewSeconds = 5
): HealthFace => {
  const fresh: Array<{ code: HealthCode; sourceTime: EsSourceTime }> = [];
  rows.forEach((row) => {
    const source = row.sourceTime;
    const value = row.value;
    if (source == null || value == null) return;
    if (!isEsSourceTime(source, nowSeconds, skewSeconds)) return;
    if (nowSeconds - source > freshSeconds) return;
    if (!isHealthCode(value)) return;
    fresh.push({ code: value, sourceTime: source });
  });
  if (!fresh.length) return { kind: 'missing' };
  const worstValue = Math.max(...fresh.map((row) => row.code));
  if (!isHealthCode(worstValue)) return { kind: 'missing' };
  const winners = fresh.filter((row) => row.code === worstValue);
  const latest = winners.reduce((best, row) => (row.sourceTime > best.sourceTime ? row : best));
  return { kind: 'value', code: worstValue, sourceTime: latest.sourceTime };
};

const newestValid = (
  times: readonly (number | null)[],
  nowSeconds: number,
  skewSeconds: number
): EsSourceTime | null => {
  let best: EsSourceTime | null = null;
  times.forEach((time) => {
    if (time == null || !isEsSourceTime(time, nowSeconds, skewSeconds)) return;
    if (best == null || time > best) best = time;
  });
  return best;
};

/**
 * 成功证据取有效源时间的最大值。没有失败序列时不编造失败。
 * 相等时成功优先，旧失败压不住更新的成功。
 */
export const collectionFace = ({
  hasInstance,
  successTimes,
  failTimes,
  nowSeconds,
  freshSeconds,
  skewSeconds = 5
}: {
  hasInstance: boolean;
  successTimes: readonly (number | null)[];
  failTimes: readonly (number | null)[];
  nowSeconds: number;
  freshSeconds: number;
  skewSeconds?: number;
}): CollectionFace => {
  if (!hasInstance) return { kind: 'not-attached' };
  const success = newestValid(successTimes, nowSeconds, skewSeconds);
  const fail = newestValid(failTimes, nowSeconds, skewSeconds);
  const events: Array<{ time: EsSourceTime; kind: 'success' | 'fail' }> = [];
  if (success) events.push({ time: success, kind: 'success' });
  if (fail) events.push({ time: fail, kind: 'fail' });
  if (!events.length) return { kind: 'unknown' };
  const latest = events.reduce((best, event) => {
    if (event.time > best.time) return event;
    if (event.time === best.time && event.kind === 'success') return event;
    return best;
  });
  if (nowSeconds - latest.time > freshSeconds) return { kind: 'expired', sourceTime: latest.time };
  if (latest.kind === 'fail') return { kind: 'failed', sourceTime: latest.time };
  return { kind: 'success', sourceTime: latest.time };
};

export const collectionLabel = (face: CollectionFace): string => {
  switch (face.kind) {
    case 'not-attached':
      return '尚未接入采集';
    case 'unknown':
      return '未知';
    case 'expired':
      return '已过期';
    case 'failed':
      return '采集失败';
    case 'success':
      return '采集成功';
    default: {
      const exhaustive: never = face;
      return exhaustive;
    }
  }
};

export const healthLabel = (code: HealthCode | null): string => {
  if (code === 1) return '绿色';
  if (code === 2) return '黄色';
  if (code === 3) return '红色';
  return '—';
};

export const healthTone = (code: HealthCode | null): 'green' | 'yellow' | 'red' | 'unknown' => {
  if (code === 1) return 'green';
  if (code === 2) return 'yellow';
  if (code === 3) return 'red';
  return 'unknown';
};

/** 75% 与 85% 都算接近。高于 85% 才是高压。 */
export const heapBand = (percent: number): HeapBand => {
  if (percent < 75) return '充足';
  if (percent <= 85) return '接近';
  return '高压';
};

const pick = (rows: readonly FreshNumber[], better: (row: FreshNumber, best: FreshNumber) => boolean): FreshNumber | null => {
  if (!rows.length) return null;
  return rows.reduce((best, row) => (better(row, best) ? row : best));
};

export const maxFresh = (rows: readonly FreshNumber[]): FreshNumber | null => (
  pick(rows, (row, best) => row.value > best.value || (row.value === best.value && row.sourceTime > best.sourceTime))
);

export const minFresh = (rows: readonly FreshNumber[]): FreshNumber | null => (
  pick(rows, (row, best) => row.value < best.value || (row.value === best.value && row.sourceTime > best.sourceTime))
);

export const sumFresh = (rows: readonly FreshNumber[]): FreshNumber | null => {
  if (!rows.length) return null;
  const value = rows.reduce((total, row) => total + row.value, 0);
  const sourceTime = rows.reduce(
    (latest, row) => (row.sourceTime > latest ? row.sourceTime : latest),
    rows[0].sourceTime
  );
  return { value, sourceTime };
};

export const latestFresh = (rows: readonly FreshNumber[]): FreshNumber | null => (
  pick(rows, (row, best) => row.sourceTime >= best.sourceTime)
);

/**
 * skip：缺项或过期项不补 0，其余项继续算；一项都不剩则缺数。
 * block：只要有一项缺或过期，整次运算缺数。
 */
export const foldNumbers = (
  rows: readonly (FreshNumber | null)[],
  how: 'sum' | 'max' | 'min',
  missing: 'skip' | 'block'
): FreshNumber | null => {
  if (missing === 'block' && rows.some((row) => row == null)) return null;
  const present = rows.filter((row): row is FreshNumber => row != null);
  if (!present.length) return null;
  if (how === 'sum') return sumFresh(present);
  if (how === 'max') return maxFresh(present);
  return minFresh(present);
};

/** 有数值样本才算能力存在。空结果是无能力。0 值的源时间仍然算有系列。 */
export const capabilityFromSamples = (
  samples: readonly (number | null)[],
  nowSeconds: number
): 'absent' | 'present' => {
  let sawSample = false;
  for (const sample of samples) {
    if (sample == null || !Number.isFinite(sample)) continue;
    sawSample = true;
    if (isEsSourceTime(sample, nowSeconds)) return 'present';
  }
  return sawSample ? 'present' : 'absent';
};

export type DimensionChrome = 'plain' | 'legend' | 'rail';

/** 2–3 条走图内图例。超过 3 条才出右栏。 */
export const dimensionChrome = (count: number): DimensionChrome => {
  if (count > 3) return 'rail';
  if (count > 1) return 'legend';
  return 'plain';
};

/** 未选或清空后左图用全部候选项。有选中时只留选中项。 */
export const selectedLineIds = (ids: readonly string[], selected: ReadonlySet<string>): string[] => {
  if (selected.size === 0) return [...ids];
  return ids.filter((id) => selected.has(id));
};
