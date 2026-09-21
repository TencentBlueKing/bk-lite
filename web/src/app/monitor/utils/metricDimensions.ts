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

/** 模板没写分组维度时，回退到对象固定维度和指标维度，避免克隆后分组为空。 */
export const resolveLoadedGroupBy = (
  savedGroupBy: unknown,
  fallbackGroupBy: unknown
): string[] => {
  const saved = sanitizeGroupBy(savedGroupBy);
  if (saved.length) return saved;
  const fallback = sanitizeGroupBy(fallbackGroupBy);
  return fallback.length ? fallback : ['instance_id'];
};
