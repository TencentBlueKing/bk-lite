const INTEGER_UNITS = new Set(['counts']);

/**
 * 格式化监控指标数值：计数不补无意义的小数位，其余指标保持两位精度。
 * percentunit 为 0–1 比例，展示前 ×100（与后端 UnitConverter 语义一致）。
 */
export const formatMetricValue = (
  value: number | string,
  unit = ''
): string => {
  const numericValue = Number(value);
  if (Number.isNaN(numericValue)) return String(value);
  if (INTEGER_UNITS.has(unit)) {
    return String(numericValue);
  }
  const displayValue =
    unit === 'percentunit' ? numericValue * 100 : numericValue;
  return displayValue.toFixed(2);
};
