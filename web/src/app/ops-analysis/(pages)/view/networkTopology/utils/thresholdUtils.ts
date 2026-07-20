/**
 * 阈值命中判定工具(design.md §2.5, §7.7)。
 *
 * 阈值数据结构为 `[{value: number, color: string}]`,由用户配置任意值 + 任意颜色;
 * 命中等级按阈值数值从小到大计算,不依赖配置数组展示顺序。
 *
 * 单个指标的命中规则:
 * - 当前值 V(有限数字)
 * - 找到位置最深的、value <= V 的阈值,用其 color
 * - 未命中(value < 最小阈值) -> 用最小阈值的 color(基线状态)
 * - V 为 null/undefined/NaN / 阈值列表为空 -> null,不参与聚合
 */

export interface SimpleThreshold {
  value: number;
  color: string;
}

interface OrderedThreshold extends SimpleThreshold {
  numericValue: number;
  originalIndex: number;
}

function getOrderedThresholds(
  thresholds: ReadonlyArray<SimpleThreshold>,
): OrderedThreshold[] {
  if (!Array.isArray(thresholds)) return [];
  return thresholds
    .map((threshold, originalIndex) => ({
      ...threshold,
      numericValue: Number(threshold?.value),
      originalIndex,
    }))
    .filter((threshold) => Number.isFinite(threshold.numericValue))
    .sort((a, b) => a.numericValue - b.numericValue || a.originalIndex - b.originalIndex);
}

/**
 * 在阈值数组中找到按数值排序后最深的、value <= V 的阈值等级。
 * 规则(design.md §7.7):
 * - 阈值数组为空 -> -1(让上层决定是否回退 unknown)
 * - 阈值数组非空:若 value < 最小阈值,返回 0(基线状态命中最小阈值)
 * - 否则返回最深命中的数值等级
 */
export function pickThresholdLevel(
  thresholds: ReadonlyArray<SimpleThreshold>,
  value: number,
): number {
  const orderedThresholds = getOrderedThresholds(thresholds);
  if (orderedThresholds.length === 0) return -1;
  let level = 0;
  for (let i = 0; i < orderedThresholds.length; i += 1) {
    if (value >= orderedThresholds[i].numericValue) {
      level = i;
    } else {
      break;
    }
  }
  return level;
}

/** 阈值列表结构校验(用于 Drawer 中提交前过滤)。 */
export function isValidThresholdList(
  thresholds: ReadonlyArray<unknown>,
): thresholds is ReadonlyArray<SimpleThreshold> {
  if (!Array.isArray(thresholds)) return false;
  for (const t of thresholds) {
    if (!t || typeof t !== 'object') return false;
    const value = Number((t as SimpleThreshold).value);
    if (!Number.isFinite(value)) return false;
    const color = (t as SimpleThreshold).color;
    if (typeof color !== 'string' || color.trim() === '') return false;
  }
  return true;
}

/** 取最深命中阈值。命中(level >= 0) -> {level, color};否则 null。 */
export function pickDeepestThresholdHit(
  thresholds: ReadonlyArray<SimpleThreshold>,
  value: number,
): { level: number; color: string } | null {
  const orderedThresholds = getOrderedThresholds(thresholds);
  if (orderedThresholds.length === 0) return null;
  const level = pickThresholdLevel(thresholds, value);
  if (level < 0) return null;
  const hit = orderedThresholds[level];
  if (!hit || typeof hit.color !== 'string') return null;
  return { level, color: hit.color };
}
