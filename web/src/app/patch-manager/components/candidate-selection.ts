import type { CandidateItem } from '@/app/patch-manager/types';
import type { Key } from 'react';

export interface CandidateSelection {
  keys: string[];
  items: CandidateItem[];
}

export function createCandidateSelection(): CandidateSelection {
  return { keys: [], items: [] };
}

export function reconcileCandidatePageSelection(
  previous: CandidateSelection,
  pageItems: CandidateItem[],
  selectedRowKeys: Key[],
): CandidateSelection {
  const pageKeys = new Set(pageItems.map((item) => item.key));
  const selectedPageKeys = new Set(
    selectedRowKeys.map(String).filter((key) => pageKeys.has(key)),
  );
  const keys = previous.keys.filter((key) => !pageKeys.has(key));
  pageItems.forEach((item) => {
    if (selectedPageKeys.has(item.key)) keys.push(item.key);
  });

  const itemsByKey = new Map(previous.items.map((item) => [item.key, item]));
  pageItems.forEach((item) => itemsByKey.set(item.key, item));

  return {
    keys,
    items: keys.flatMap((key) => {
      const item = itemsByKey.get(key);
      return item ? [item] : [];
    }),
  };
}

export function removeCandidateFromSelection(
  previous: CandidateSelection,
  key: string,
): CandidateSelection {
  return {
    keys: previous.keys.filter((selectedKey) => selectedKey !== key),
    items: previous.items.filter((item) => item.key !== key),
  };
}
