const INTEGER_UNITS = new Set(['counts']);

/** 计数最多两位小数。整数不补 `.00`，长尾如 `3.89966555139465` 收到 `3.9`。 */
const formatCount = (value: number) => {
  const fixed = value.toFixed(2);
  if (/e/i.test(fixed)) return String(value);
  const trimmed = fixed.replace(/\.00$/, '').replace(/(\.\d)0$/, '$1');
  return trimmed === '-0' ? '0' : trimmed;
};

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
    return formatCount(numericValue);
  }
  const displayValue =
    unit === 'percentunit' ? numericValue * 100 : numericValue;
  return displayValue.toFixed(2);
};
