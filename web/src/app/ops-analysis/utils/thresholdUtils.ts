/**
 * 阈值颜色配置工具函数
 * 共享模块：供 topology 和 dashBoard 使用
 */
import { DEFAULT_THRESHOLD_COLORS } from '@/app/ops-analysis/constants/threshold';
import { formatUnit } from '@/app/ops-analysis/utils/unitFormat';

export interface ThresholdColorConfig {
  value: string;
  color: string;
}

/** 写盘时保留用户显式给出的列表（含空数组）；缺省或非数组则省略。 */
export const persistThresholdColorConfig = (
  colors: unknown,
): ThresholdColorConfig[] | undefined => {
  if (!Array.isArray(colors)) return undefined;
  return colors.flatMap((item) => {
    if (!item || typeof item !== 'object') return [];
    const row = item as Record<string, unknown>;
    const value = String(row.value ?? '').trim();
    const color = String(row.color ?? '').trim();
    if (!value && !color) return [];
    return [{ value, color }];
  });
};

/** InputNumber 清空后是 null；只有有限数字才视为用户显式配置。 */
export const isFiniteNumber = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value);

/**
 * 初始化阈值颜色：如果传入有效数组则按值降序排列，否则返回默认值
 */
export const initThresholdColors = (
  colors: ThresholdColorConfig[] | undefined | null,
): ThresholdColorConfig[] => {
  if (colors && Array.isArray(colors)) {
    return [...colors].sort(
      (a, b) => parseFloat(b.value) - parseFloat(a.value),
    );
  }
  return DEFAULT_THRESHOLD_COLORS;
};

const clampRatio = (value: number, min: number, max: number) => {
  if (value < min) return min;
  if (value > max) return max;
  return value;
};

/**
 * 将「当值 ≥ N」阈值转为 ECharts gauge axisLine.lineStyle.color。
 * ECharts 语义是「该颜色画到该比例为止」，因此每档颜色应延伸到下一更高阈值
 * （最后一档延伸到 max），而不是停在本档阈值起点。
 */
export const buildGaugeAxisLineColor = (
  min: number,
  max: number,
  thresholds: Array<{ value: string; color: string }> = [],
  defaultColor: string = '#366CE4',
): Array<[number, string]> => {
  if (!thresholds.length || max <= min) {
    return [[1, defaultColor]];
  }

  const range = max - min;
  const sorted = [...thresholds]
    .map((item) => ({
      value: Number(item.value),
      color: item.color,
    }))
    .filter((item) => Number.isFinite(item.value))
    .sort((a, b) => a.value - b.value);

  if (!sorted.length) {
    return [[1, defaultColor]];
  }

  const axisLine: Array<[number, string]> = [];
  sorted.forEach((item, index) => {
    const endRatio =
      index === sorted.length - 1
        ? 1
        : clampRatio((sorted[index + 1].value - min) / range, 0, 1);
    if (endRatio <= 0) {
      return;
    }
    const prevRatio = axisLine.length ? axisLine[axisLine.length - 1][0] : 0;
    if (endRatio <= prevRatio) {
      // 同比例时保留更高阈值色（后写入覆盖）
      if (endRatio === prevRatio && axisLine.length) {
        axisLine[axisLine.length - 1] = [endRatio, item.color];
      }
      return;
    }
    axisLine.push([endRatio, item.color]);
  });

  if (!axisLine.length) {
    return [[1, sorted[sorted.length - 1].color]];
  }

  if (axisLine[axisLine.length - 1][0] < 1) {
    axisLine.push([1, sorted[sorted.length - 1].color]);
  }

  return axisLine;
};

/**
 * 根据数据值和阈值配置计算对应的颜色
 * @param dataValue 数据值
 * @param thresholds 阈值配置数组，按值从高到低排序
 * @returns 对应的颜色值，如果没有匹配的阈值则返回默认颜色
 */
export const getColorByThreshold = (
  dataValue: number | string | null | undefined,
  thresholds: ThresholdColorConfig[] = [],
  defaultColor: string = '#000000'
): string => {
  if (thresholds.length === 0) {
    return defaultColor;
  }

  // 如果数据值为null、undefined或空字符串，返回默认颜色
  if (dataValue === null || dataValue === undefined || dataValue === '') {
    return defaultColor;
  }

  // 转换为数字进行比较
  const numValue = typeof dataValue === 'string' ? parseFloat(dataValue) : dataValue;

  // 如果无法转换为有效数字，返回默认颜色
  if (isNaN(numValue)) {
    return defaultColor;
  }

  // 按阈值从高到低排序
  const sortedThresholds = [...thresholds]
    .sort((a, b) => parseFloat(b.value) - parseFloat(a.value));

  // 查找第一个满足条件的阈值（数据值 >= 阈值）
  for (const threshold of sortedThresholds) {
    const thresholdValue = parseFloat(threshold.value);
    if (!isNaN(thresholdValue) && numValue >= thresholdValue) {
      return threshold.color;
    }
  }

  // 如果没有匹配的阈值，返回最小阈值的颜色或默认颜色
  if (sortedThresholds.length > 0) {
    return sortedThresholds[sortedThresholds.length - 1].color;
  }

  return defaultColor;
};

/**
 * 格式化显示值（添加单位、小数位等）
 * @param value 原始值
 * @param unit 单位（自由文本后缀，兼容旧逻辑）
 * @param decimalPlaces 小数位数
 * @param conversionFactor 换算系数，默认为1
 * @param unitId 结构化单位 id（如 bytesIEC/bps/ms/percent/short）。传入时启用
 *               单位库自动量纲缩放；不传则保持原有自由文本后缀行为（向后兼容）。
 * @returns 格式化后的显示值
 */
export const formatDisplayValue = (
  value: number | string | null | undefined,
  unit?: string,
  decimalPlaces?: number,
  conversionFactor?: number,
  unitId?: string
): string => {
  const resolvedDecimalPlaces = isFiniteNumber(decimalPlaces)
    ? decimalPlaces
    : undefined;
  const resolvedConversionFactor = isFiniteNumber(conversionFactor)
    ? conversionFactor
    : undefined;

  // 结构化单位：委托单位库（opt-in，旧调用不受影响）
  if (unitId && unitId.trim()) {
    return formatUnit(value, unitId, {
      decimals: resolvedDecimalPlaces,
      conversionFactor: resolvedConversionFactor,
    }).text;
  }

  if (value === null || value === undefined || value === '') {
    return '--';
  }

  const numValue = typeof value === 'string' ? parseFloat(value) : value;

  if (isNaN(numValue)) {
    return String(value);
  }

  // 应用换算系数；清空后的 null 回退为 1，避免 `value * null === 0`
  const factor = resolvedConversionFactor ?? 1;
  const convertedValue = numValue * factor;

  // 格式化小数位；清空后的 null 回退默认展示，避免 `toFixed(null)` 变成 0 位
  let formattedValue = resolvedDecimalPlaces !== undefined
    ? convertedValue.toFixed(resolvedDecimalPlaces)
    : String(convertedValue);

  // 添加单位
  if (unit && unit.trim()) {
    formattedValue += unit;
  }

  return formattedValue;
};
