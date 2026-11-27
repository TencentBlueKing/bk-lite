/** 全 0 折线彩色笔画中心离开底轴的距离。调用方必须显式传入这个数。 */
export const FLAT_ZERO_STROKE_LIFT_PX = 8;

/** 绘制层附加序列的名字。悬浮框会跳过它，避免把同一条 0 读两遍。 */
export const FLAT_ZERO_STROKE_SERIES_PREFIX = '\0flat-zero:';

/**
 * 整条序列都是 0、且数值轴下限就是 0 时，返回只用于绘制的上移像素。
 * 其它情况返回 null：不改采样、不改轴、不抬非零线。
 */
export const flatZeroStrokeLift = (
  samples: readonly number[],
  requested: number | undefined,
  axisMin: number
): number | null => {
  if (requested !== FLAT_ZERO_STROKE_LIFT_PX) return null;
  if (axisMin !== 0) return null;
  if (!samples.length) return null;
  for (const value of samples) {
    if (value !== 0) return null;
  }
  return FLAT_ZERO_STROKE_LIFT_PX;
};
