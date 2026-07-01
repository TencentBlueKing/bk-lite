interface ColorPickerLikeValue {
  toHexString?: () => string;
  toRgbString?: () => string;
}

const isColorPickerLikeValue = (value: unknown): value is ColorPickerLikeValue =>
  typeof value === 'object' && value !== null;

export const normalizeColorPickerValue = (
  colorValue: unknown,
): string | undefined => {
  if (!colorValue) return undefined;
  if (typeof colorValue === 'string') return colorValue;
  if (!isColorPickerLikeValue(colorValue)) return undefined;

  if (typeof colorValue.toHexString === 'function') {
    return colorValue.toHexString();
  }

  if (typeof colorValue.toRgbString === 'function') {
    return colorValue.toRgbString();
  }

  return undefined;
};

export const normalizeColorFields = <T extends object>(
  values: T,
  keys: string[],
): T => {
  const normalizedValues = { ...values } as Record<string, unknown>;

  keys.forEach((key) => {
    if (normalizedValues[key]) {
      normalizedValues[key] = normalizeColorPickerValue(normalizedValues[key]);
    }
  });

  return normalizedValues as T;
};
