import { useCallback } from 'react';
import { useOpsAnalysis } from '@/app/ops-analysis/context/common';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';

type ExtractNamespaceIds<T> = (source: T, dataSources: DatasourceItem[]) => Set<number>;
type ExtractDataSourceIds<T> = (source: T) => number[];

export const useCanvasResources = () => {
  const { loadCanvasDataSources, loadCanvasNamespaces } = useOpsAnalysis();

  const syncCanvasResources = useCallback(async <T,>(params: {
    source: T;
    getDataSourceIds: ExtractDataSourceIds<T>;
    getNamespaceIds: ExtractNamespaceIds<T>;
  }) => {
    const { source, getDataSourceIds, getNamespaceIds } = params;
    const dataSourceIds = getDataSourceIds(source);
    const canvasDataSources = await loadCanvasDataSources(dataSourceIds);
    const namespaceIds = Array.from(getNamespaceIds(source, canvasDataSources));
    await loadCanvasNamespaces(namespaceIds);
    return canvasDataSources;
  }, [loadCanvasDataSources, loadCanvasNamespaces]);

  return {
    syncCanvasResources,
  };
};
