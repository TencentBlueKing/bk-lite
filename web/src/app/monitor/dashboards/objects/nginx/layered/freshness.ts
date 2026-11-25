/** 源样本时间。读 tlast_over_time 的 value[1]，按实例取最近一条有效时间。 */

export const MIN_SOURCE_UNIX_SECONDS = 1_000_000_000;
export const FRESH_FLOOR_SECONDS = 180;

export interface TimedSample {
  value: number;
}

export const freshLimitSeconds = (intervalSeconds?: number) => {
  const interval = intervalSeconds != null && Number.isFinite(intervalSeconds) && intervalSeconds > 0
    ? intervalSeconds
    : 0;
  return Math.max(FRESH_FLOOR_SECONDS, interval * 2);
};

/** 多条先丢掉缺失、非有限、未来和过小的数，再取 max。空则没有成功源时间。 */
export const mergeSourceTime = (
  samples: readonly TimedSample[],
  nowSeconds: number
): number | null => {
  let latest: number | null = null;
  samples.forEach((sample) => {
    const time = sample.value;
    if (!Number.isFinite(time) || time > nowSeconds || time < MIN_SOURCE_UNIX_SECONDS) return;
    if (latest == null || time > latest) latest = time;
  });
  return latest;
};

export const isStale = (
  sourceTime: number | null,
  nowSeconds: number,
  limitSeconds: number
) => sourceTime == null || nowSeconds - sourceTime > limitSeconds;

export type CollectionKind = 'not_onboarded' | 'success' | 'expired' | 'unknown';

export const collectionKind = (
  onboarded: boolean,
  sourceTime: number | null,
  nowSeconds: number,
  limitSeconds: number
): CollectionKind => {
  if (!onboarded) return 'not_onboarded';
  if (sourceTime == null) return 'unknown';
  if (nowSeconds - sourceTime <= limitSeconds) return 'success';
  return 'expired';
};

export const busyRatio = (
  active: number | null,
  reading: number | null,
  writing: number | null,
  stale: boolean
) => {
  if (stale || active == null || reading == null || writing == null) return null;
  if (active === 0) return null;
  return (reading + writing) / active;
};

export const waitingRatio = (
  active: number | null,
  waiting: number | null,
  stale: boolean
) => {
  if (stale || active == null || waiting == null) return null;
  if (active === 0) return null;
  return waiting / active;
};

export const handledRatio = (
  accepts: number | null,
  handled: number | null,
  stale: boolean
) => {
  if (stale || accepts == null || handled == null) return null;
  if (accepts === 0) return null;
  return handled / accepts;
};

/** 两条速率都在且都新鲜时才有数。差为 0 保留 0，负差只做展示钳制。 */
export const droppedRate = (
  accepts: number | null,
  handled: number | null,
  stale: boolean
) => {
  if (stale || accepts == null || handled == null) return null;
  return Math.max(accepts - handled, 0);
};
