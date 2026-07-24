export const flattenExtractorPaths = (
  value: unknown,
  prefix = '',
  result = new Set<string>()
): Set<string> => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return result;
  Object.entries(value).forEach(([key, child]) => {
    const segment = /^[A-Za-z_][A-Za-z0-9_]*$/.test(key)
      ? key
      : `[${JSON.stringify(key)}]`;
    const path = prefix
      ? segment.startsWith('[')
        ? `${prefix}${segment}`
        : `${prefix}.${segment}`
      : segment;
    result.add(path);
    flattenExtractorPaths(child, path, result);
  });
  return result;
};

export const normalizeExtractorSamples = (
  payload: unknown
): Record<string, unknown>[] => {
  if (Array.isArray(payload)) {
    return payload.filter(
      (item): item is Record<string, unknown> =>
        Boolean(item) && typeof item === 'object' && !Array.isArray(item)
    );
  }
  if (payload && typeof payload === 'object') {
    const data = (payload as Record<string, unknown>).data;
    if (Array.isArray(data)) return normalizeExtractorSamples(data);
  }
  return [];
};

export const moveExtractorItem = <T,>(
  items: T[],
  index: number,
  offset: -1 | 1
): T[] | null => {
  const target = index + offset;
  if (target < 0 || target >= items.length) return null;
  const next = [...items];
  [next[index], next[target]] = [next[target], next[index]];
  return next;
};

export const reorderExtractorItem = <T,>(
  items: T[],
  from: number,
  to: number
): T[] | null => {
  if (
    from === to ||
    from < 0 ||
    to < 0 ||
    from >= items.length ||
    to >= items.length
  ) {
    return null;
  }
  const next = [...items];
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
};

export const shouldShowExtractorHeaderAdd = (
  canOperate: boolean | undefined,
  ruleCount: number
) => Boolean(canOperate) && ruleCount > 0;

export const shouldShowExtractorPublicationAlert = (
  status: 'pending' | 'generating' | 'published' | 'failed'
) => status !== 'published';
