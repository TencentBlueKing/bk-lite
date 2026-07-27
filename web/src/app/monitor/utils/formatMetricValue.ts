const INTEGER_UNITS = new Set(['counts']);

/**
 * 格式化监控指标数值：计数不补无意义的小数位，其余指标保持两位精度。
 */
export const formatMetricValue = (
  value: number | string,
  unit = ''
): string => {
  const numericValue = Number(value);
  if (Number.isNaN(numericValue)) return String(value);
  return INTEGER_UNITS.has(unit)
    ? String(numericValue)
    : numericValue.toFixed(2);
};
