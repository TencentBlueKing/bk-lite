export function pruneRelationFieldsCache<T>(
  prev: Record<string, T>,
  selectedModelIds: string[],
): Record<string, T> {
  const selected = new Set(selectedModelIds);
  const prevKeys = Object.keys(prev);
  const hasDroppedKey = prevKeys.some((key) => !selected.has(key));
  if (!hasDroppedKey) {
    return prev;
  }

  const next: Record<string, T> = {};
  for (const key of prevKeys) {
    if (selected.has(key)) {
      next[key] = prev[key];
    }
  }
  return next;
}
