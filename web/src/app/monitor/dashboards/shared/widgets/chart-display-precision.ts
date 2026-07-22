const DEFAULT_DECIMAL_PLACES = 2;

export const roundChartValueToDisplayPrecision = (
  value: number | null,
  decimalPlaces = DEFAULT_DECIMAL_PLACES
): number | null => {
  if (value == null || !Number.isFinite(value)) return value;

  const factor = 10 ** decimalPlaces;
  const rounded = Math.sign(value) * Math.round((Math.abs(value) + Number.EPSILON) * factor) / factor;
  return Object.is(rounded, -0) ? 0 : rounded;
};
