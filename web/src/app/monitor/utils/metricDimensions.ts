type MetricDimension = string | { name?: unknown } | null | undefined;

const getDimensionName = (dimension: MetricDimension): string => {
  if (typeof dimension === 'string') {
    return dimension.trim();
  }
  if (dimension && typeof dimension === 'object') {
    return String(dimension.name || '').trim();
  }
  return '';
};

export const uniqueNonEmptyStrings = (values: unknown): string[] => {
  if (!Array.isArray(values)) {
    return [];
  }
  const result: string[] = [];
  const seen = new Set<string>();
  values.forEach((value) => {
    const item = String(value || '').trim();
    if (item && !seen.has(item)) {
      result.push(item);
      seen.add(item);
    }
  });
  return result;
};

export const getMetricDimensionNames = (dimensions: unknown): string[] => {
  if (!Array.isArray(dimensions)) {
    return [];
  }
  return uniqueNonEmptyStrings(dimensions.map(getDimensionName));
};

export const sanitizeGroupBy = uniqueNonEmptyStrings;
