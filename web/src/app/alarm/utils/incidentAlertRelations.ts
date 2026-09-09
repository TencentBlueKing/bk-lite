export function collectSelectedAlertIds(
  keys: ReadonlyArray<string | number> | null | undefined
): number[] {
  if (!keys?.length) {
    return [];
  }

  const ids: number[] = [];
  const seen = new Set<number>();
  for (const key of keys) {
    const id = typeof key === 'number' ? key : Number(key);
    if (!Number.isInteger(id) || seen.has(id)) {
      continue;
    }
    seen.add(id);
    ids.push(id);
  }
  return ids;
}
