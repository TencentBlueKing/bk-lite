export const clampWidth = (
  value: number,
  minWidth: number,
  maxWidth: number,
  defaultWidth: number,
) => {
  if (!Number.isFinite(value)) return defaultWidth;
  return Math.min(maxWidth, Math.max(minWidth, value));
};
