/**
 * 缓存命中率。目录查询已经是百分数（含 ×100）。
 * 这里不再乘 100。分母（命中块速率 + 读盘块速率）为 0 时没有比率。
 */
export interface CacheHitReading {
  /** 已经是 0–100 的百分数。分母为 0 或尚未成对采样时为 null。 */
  percent: number | null;
  denominatorZero: boolean;
}

const finite = (value: number | null | undefined) => (
  value != null && Number.isFinite(value) ? value : null
);

export const cacheHitPercent = (
  ratio: number | null | undefined,
  hits: number | null | undefined,
  reads: number | null | undefined
): CacheHitReading => {
  const hit = finite(hits);
  const read = finite(reads);
  if (hit == null || read == null) {
    return { percent: null, denominatorZero: false };
  }
  const denominator = hit + read;
  if (!(denominator > 0)) {
    return { percent: null, denominatorZero: true };
  }
  const supplied = finite(ratio);
  const percent = supplied != null ? supplied : (100 * hit) / denominator;
  if (!Number.isFinite(percent)) {
    return { percent: null, denominatorZero: false };
  }
  return { percent, denominatorZero: false };
};

export const formatCacheHitPercent = (percent: number) => {
  const text = percent.toFixed(1).replace(/\.0$/, '');
  return `${text}%`;
};
