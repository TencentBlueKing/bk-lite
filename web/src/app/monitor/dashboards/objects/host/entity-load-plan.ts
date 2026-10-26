export type EntityLoadStatus = 'idle' | 'loading' | 'ready' | 'empty' | 'error';

/**
 * 同一时间窗里已经成功或本轮已失败、或仍在飞的 key 不再打。
 * 失败集由调用方在查询集变化时清空，这样进详情页会重试概览里失败的 key。
 */
export const entityQueryKeysToFetch = (
  wanted: readonly string[],
  settled: ReadonlySet<string>,
  failed: ReadonlySet<string>,
  inflight: ReadonlySet<string>
): string[] => wanted.filter((key) => !settled.has(key) && !failed.has(key) && !inflight.has(key));

/**
 * 把已成功的序列投影成面板状态。
 * 想要的 key 还没成功也没失败就是 loading，已有序列照样带上，不补 0。
 * 缩小查询集时，多出来的成功序列留在 byMetric，回切详情不用重拉。
 */
export const projectEntityLoad = <T>(
  wanted: readonly string[],
  settled: Readonly<Record<string, T[]>>,
  failed: ReadonlySet<string>,
  inflight: ReadonlySet<string>
): { status: EntityLoadStatus; byMetric: Record<string, T[]> } => {
  const byMetric: Record<string, T[]> = { ...settled };
  let pending = false;
  let failures = 0;
  wanted.forEach((key) => {
    if (failed.has(key)) {
      failures += 1;
      return;
    }
    if (inflight.has(key) || !Object.prototype.hasOwnProperty.call(settled, key)) {
      pending = true;
    }
  });
  if (pending) return { status: 'loading', byMetric };
  if (wanted.length > 0 && failures === wanted.length) return { status: 'error', byMetric };
  const anySeries = Object.values(byMetric).some((series) => series.length > 0);
  return { status: anySeries ? 'ready' : 'empty', byMetric };
};
