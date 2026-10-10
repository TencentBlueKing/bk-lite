import type { Key } from 'react';

import type { TableDataItem } from '@/app/node-manager/types';

export type NodeSelectionClearReason =
  | 'filters'
  | 'unassigned'
  | 'cloudRegion'
  | 'pagination';

export function nextSelectedNodeMap({
  previous,
  selectedKeys,
  currentPageRows
}: {
  previous: Map<Key, TableDataItem>;
  selectedKeys: Key[];
  currentPageRows: TableDataItem[];
}): Map<Key, TableDataItem> {
  const pageByKey = new Map(
    currentPageRows.map((row) => [row.key ?? row.id, row] as const)
  );
  const next = new Map<Key, TableDataItem>();
  for (const key of selectedKeys) {
    const row = pageByKey.get(key) || previous.get(key);
    if (row) {
      next.set(key, row);
    }
  }
  return next;
}

export function shouldClearNodeSelection({
  reason
}: {
  reason: NodeSelectionClearReason;
}): boolean {
  return reason !== 'pagination';
}

export function selectedNodesFromMap(
  selectedKeys: Key[],
  selectedMap: Map<Key, TableDataItem>
): TableDataItem[] {
  return selectedKeys
    .map((key) => selectedMap.get(key))
    .filter((item): item is TableDataItem => Boolean(item));
}
