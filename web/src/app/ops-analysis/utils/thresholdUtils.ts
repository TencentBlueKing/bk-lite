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
 * 验证阈值配置的有效性
 * @param thresholds 阈值配置数组
 * @returns 验证结果
 */
export const validateThresholds = (thresholds: ThresholdColorConfig[]) => {
  const errors: string[] = [];

  for (let i = 0; i < thresholds.length; i++) {
    const threshold = thresholds[i];

    // 检查颜色格式
    if (!threshold.color || !threshold.color.match(/^#[0-9A-Fa-f]{6}$/)) {
      errors.push(`第${i + 1}个阈值的颜色格式无效`);
    }

    // 检查数值格式
    const value = parseFloat(threshold.value);
    if (isNaN(value)) {
      errors.push(`第${i + 1}个阈值的数值无效`);
    }
  }

  return {
    isValid: errors.length === 0,
    errors
  };
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
  // 结构化单位：委托单位库（opt-in，旧调用不受影响）
  if (unitId && unitId.trim()) {
    return formatUnit(value, unitId, {
      decimals: decimalPlaces,
      conversionFactor,
    }).text;
  }

  if (value === null || value === undefined || value === '') {
    return '--';
  }

  const numValue = typeof value === 'string' ? parseFloat(value) : value;

  if (isNaN(numValue)) {
    return String(value);
  }

  // 应用换算系数
  const factor = conversionFactor !== undefined ? conversionFactor : 1;
  const convertedValue = numValue * factor;

  // 格式化小数位
  let formattedValue = decimalPlaces !== undefined
    ? convertedValue.toFixed(decimalPlaces)
    : String(convertedValue);

  // 添加单位
  if (unit && unit.trim()) {
    formattedValue += unit;
  }

  return formattedValue;
};

/**
 * 从嵌套对象中根据路径提取值
 * @param obj 数据对象
 * @param path 路径，支持 "." 分隔的嵌套路径和数组索引 "[0]"
 * @returns 提取的值
 */
export const getValueByPath = (
  obj: unknown,
  path: string | undefined
): unknown => {
  if (!path || obj === null || obj === undefined) {
    return undefined;
  }

  // 处理路径，将 "[0]" 转换为 ".0"
  const normalizedPath = path.replace(/\[(\d+)\]/g, '.$1');
  const keys = normalizedPath.split('.');

  let current: unknown = obj;
  for (const key of keys) {
    if (current === null || current === undefined) {
      return undefined;
    }
    if (typeof current === 'object') {
      current = (current as Record<string, unknown>)[key];
    } else {
      return undefined;
    }
  }

  return current;
};
