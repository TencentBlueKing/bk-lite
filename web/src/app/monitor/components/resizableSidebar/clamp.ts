// Clamp a sidebar width into [min, max]; NaN/invalid → fallback.
export const clampWidth = (
  value: number,
  min: number,
  max: number,
  fallback: number
): number => {
  if (!Number.isFinite(value)) return fallback;
  return Math.min(max, Math.max(min, Math.round(value)));
};
