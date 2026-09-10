import type { Key } from 'react';

export function collectSelectedAlertIds(
  keys: ReadonlyArray<Key> | null | undefined
): number[] {
  if (!keys?.length) {
    return [];
  }

  const ids: number[] = [];
  const seen = new Set<number>();
  for (const key of keys) {
    if (typeof key !== 'string' && typeof key !== 'number') {
      continue;
    }
    const id = typeof key === 'number' ? key : Number(key);
    if (!Number.isInteger(id) || seen.has(id)) {
      continue;
    }
    seen.add(id);
    ids.push(id);
  }
  return ids;
}
