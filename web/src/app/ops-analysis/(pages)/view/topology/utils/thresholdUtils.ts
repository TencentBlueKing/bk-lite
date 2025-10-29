/**
 * 阈值颜色配置工具函数
 */
export interface ThresholdColorConfig {
  value: string;
  color: string;
}

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
 * @param unit 单位
 * @param decimalPlaces 小数位数
 * @param conversionFactor 换算系数，默认为1
 * @returns 格式化后的显示值
 */
export const formatDisplayValue = (
  value: number | string | null | undefined,
  unit?: string,
  decimalPlaces?: number,
  conversionFactor?: number
): string => {
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
