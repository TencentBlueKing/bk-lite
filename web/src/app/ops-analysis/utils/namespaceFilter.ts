import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import type { LayoutItem } from '@/app/ops-analysis/types/dashBoard';

export interface NamespaceOption {
  label: string;
  value: number;
}

export const collectNamespaceOptions = (
  layout: LayoutItem[],
  dataSources: DatasourceItem[],
  namespaceList: Array<{ id: number; name: string }>,
): NamespaceOption[] => {
  const namespaceIds = collectNamespaceIdsFromLayout(layout, dataSources);

  if (namespaceIds.size === 0) return [];

  return namespaceList
    .filter((ns) => namespaceIds.has(ns.id))
    .map((ns) => ({
      label: ns.name || String(ns.id),
      value: ns.id,
    }));
};

export const collectNamespaceIdsFromLayout = (
  layout: LayoutItem[],
  dataSources: DatasourceItem[],
): Set<number> => {
  const namespaceIds = new Set<number>();

  layout.forEach((item) => {
    const dsId = item.valueConfig?.dataSource;
    const normalizedId = typeof dsId === 'string' ? parseInt(dsId, 10) : dsId;
    const ds = dataSources.find((d) => d.id === normalizedId);
    if (ds?.namespaces) {
      ds.namespaces.forEach((id) => namespaceIds.add(id));
    }
  });

  return namespaceIds;
};
