import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import type { LayoutItem } from '@/app/ops-analysis/types/dashBoard';
import type { ScreenViewSets } from '@/app/ops-analysis/types/screen';
import { collectNamespaceIdsFromLayout } from '@/app/ops-analysis/utils/namespaceFilter';
import { collectNamespaceIdsFromNodes } from '@/app/ops-analysis/(pages)/view/topology/utils/namespaceUtils';
import type { Graph } from '@antv/x6';

export const collectDashboardDataSourceIds = (items: LayoutItem[] = []) => {
  const ids = new Set<number>();
  items.forEach((item) => {
    const rawId = item.valueConfig?.dataSource;
    const normalizedId = typeof rawId === 'string' ? parseInt(rawId, 10) : rawId;
    if (Number.isFinite(normalizedId)) {
      ids.add(normalizedId as number);
    }
  });
  return Array.from(ids);
};

export const collectDashboardNamespaceIds = (
  items: LayoutItem[] = [],
  dataSources: DatasourceItem[] = [],
) => {
  return collectNamespaceIdsFromLayout(items, dataSources);
};

export const collectTopologyDataSourceIds = (viewSets: any): number[] => {
  const ids = new Set<number>();
  const nodes = Array.isArray(viewSets?.nodes)
    ? viewSets.nodes
    : Array.isArray(viewSets?.cells)
      ? viewSets.cells
      : [];
  nodes.forEach((node: any) => {
    const rawId = node?.data?.valueConfig?.dataSource ?? node?.valueConfig?.dataSource;
    const normalizedId = typeof rawId === 'string' ? parseInt(rawId, 10) : rawId;
    if (Number.isFinite(normalizedId)) {
      ids.add(normalizedId as number);
    }
  });
  return Array.from(ids);
};

export const collectTopologyNamespaceIds = (
  graphInstance: Graph | null,
  dataSources: DatasourceItem[] = [],
) => {
  return collectNamespaceIdsFromNodes(graphInstance, dataSources);
};

export const collectScreenDataSourceIds = (viewSets: ScreenViewSets) => {
  const ids = new Set<number>();
  viewSets.items.forEach((item) => {
    const rawId = item.valueConfig?.dataSource;
    const normalizedId = typeof rawId === 'string' ? parseInt(rawId, 10) : rawId;
    if (Number.isFinite(normalizedId)) {
      ids.add(normalizedId as number);
    }
  });
  return Array.from(ids);
};

export const collectScreenNamespaceIds = (
  viewSets: ScreenViewSets,
  dataSources: DatasourceItem[] = [],
) => {
  const namespaceIds = new Set<number>();
  viewSets.items.forEach((item) => {
    const rawId = item.valueConfig?.dataSource;
    const normalizedId = typeof rawId === 'string' ? parseInt(rawId, 10) : rawId;
    const dataSource = dataSources.find((source) => source.id === normalizedId);
    dataSource?.namespaces?.forEach((id) => namespaceIds.add(id));
  });
  return namespaceIds;
};
