import { useCallback, useEffect, useMemo } from 'react';
import type { Graph } from '@antv/x6';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import { useOpsAnalysis } from '@/app/ops-analysis/context/common';
import { useCanvasResources } from '@/app/ops-analysis/hooks/useCanvasResources';
import {
  collectTopologyDataSourceIds,
  collectTopologyNamespaceIds,
} from '@/app/ops-analysis/utils/canvasResources';
import { collectNamespaceOptionsFromNodes } from '../utils/namespaceUtils';

interface UseTopologyCanvasResourcesParams {
  graphInstance: Graph | null;
  dataSources: DatasourceItem[];
  nodeChangeKey: number;
  namespaceDraftId: number | undefined;
  appliedNamespaceId: number | undefined;
  setNamespaceDraftId: (value: number | undefined) => void;
  setAppliedNamespaceId: (value: number | undefined) => void;
}

export const useTopologyResources = ({
  graphInstance,
  dataSources,
  nodeChangeKey,
  namespaceDraftId,
  appliedNamespaceId,
  setNamespaceDraftId,
  setAppliedNamespaceId,
}: UseTopologyCanvasResourcesParams) => {
  const { namespaceList } = useOpsAnalysis();
  const { syncCanvasResources } = useCanvasResources();

  const syncTopologyCanvasResources = useCallback(async () => {
    return syncCanvasResources({
      source: graphInstance,
      getDataSourceIds: (currentGraph) => {
        return collectTopologyDataSourceIds(currentGraph?.toJSON() || {});
      },
      getNamespaceIds: collectTopologyNamespaceIds,
    });
  }, [graphInstance, syncCanvasResources]);

  const namespaceOptions = useMemo(() => {
    return collectNamespaceOptionsFromNodes(
      graphInstance,
      dataSources,
      namespaceList,
    );
  }, [graphInstance, dataSources, namespaceList, nodeChangeKey]);

  useEffect(() => {
    if (namespaceOptions.length > 0) {
      const fallbackNamespaceId = namespaceOptions[0].value;
      const draftValid =
        namespaceDraftId !== undefined &&
        namespaceOptions.some((option) => option.value === namespaceDraftId);
      const appliedValid =
        appliedNamespaceId !== undefined &&
        namespaceOptions.some((option) => option.value === appliedNamespaceId);

      if (!draftValid) {
        setNamespaceDraftId(fallbackNamespaceId);
      }
      if (!appliedValid) {
        setAppliedNamespaceId(fallbackNamespaceId);
      }
      return;
    }

    setNamespaceDraftId(undefined);
    setAppliedNamespaceId(undefined);
  }, [
    appliedNamespaceId,
    namespaceDraftId,
    namespaceOptions,
    setAppliedNamespaceId,
    setNamespaceDraftId,
  ]);

  return {
    namespaceOptions,
    syncTopologyCanvasResources,
  };
};
