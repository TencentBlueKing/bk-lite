import { useCallback, useEffect, useRef, useState } from 'react';
import type React from 'react';
import type { Model } from '@antv/x6';
import type {
  FilterValue,
  UnifiedFilterDefinition,
} from '@/app/ops-analysis/types/dashBoard';
import type { TopologyProps } from '@/app/ops-analysis/types/topology';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import { collectTopologyNamespaceIds } from '@/app/ops-analysis/utils/canvasResources';
import {
  buildFiltersFromNodes,
  syncFilterValuesWithDefinitions,
} from '../utils/namespaceUtils';
import { syncAndFillOrganizationFilterValues } from '@/app/ops-analysis/utils/unifiedFilterState';
import type { useTopologyState } from './useTopologyState';

interface UseTopologyLifecycleParams {
  selectedTopology: TopologyProps['selectedTopology'];
  state: ReturnType<typeof useTopologyState>;
  definitions: UnifiedFilterDefinition[];
  appliedFilterValues: Record<string, FilterValue>;
  appliedNamespaceId: number | undefined;
  setAppliedFilterValues: React.Dispatch<
    React.SetStateAction<Record<string, FilterValue>>
  >;
  setAppliedNamespaceId: (value: number | undefined) => void;
  setDefinitions: (definitions: UnifiedFilterDefinition[]) => void;
  setFilterValues: (values: Record<string, FilterValue>) => void;
  setNamespaceDraftId: (value: number | undefined) => void;
  clearOperationHistory: () => void;
  clearRefreshTimer: () => void;
  finishInitialization: () => void;
  handleLoadTopology: (dataId: number | string, signal?: AbortSignal) => Promise<{
    filters?: UnifiedFilterDefinition[];
    refreshInterval?: number;
  }>;
  onLoadedRefreshInterval?: (interval: number) => void;
  organizationId?: string | number | null;
  loadCanvasNamespaces: (namespaceIds?: (string | number)[]) => unknown;
  refreshAllSingleValueNodes: (
    values?: Record<string, FilterValue>,
    definitions?: UnifiedFilterDefinition[],
    namespaceId?: number,
  ) => void;
  refreshAllChartNodes: (
    values?: Record<string, FilterValue>,
    definitions?: UnifiedFilterDefinition[],
    dataSources?: DatasourceItem[],
    namespaceId?: number,
  ) => void;
  abortInflightDataRequests: () => void;
  refreshTopologyNodes: (
    scope: 'reload',
    values?: Record<string, FilterValue>,
    definitions?: UnifiedFilterDefinition[],
    namespaceId?: number,
  ) => void;
  scheduleTopologyInitialization: (callback: () => void) => void;
  startInitialization: () => void;
  syncTopologyCanvasResources: () => Promise<DatasourceItem[] | null>;
  toggleEditMode: () => void;
}

export const useTopologyLifecycle = ({
  selectedTopology,
  state,
  definitions,
  appliedFilterValues,
  appliedNamespaceId,
  setAppliedFilterValues,
  setAppliedNamespaceId,
  setDefinitions,
  setFilterValues,
  setNamespaceDraftId,
  clearOperationHistory,
  clearRefreshTimer,
  finishInitialization,
  handleLoadTopology,
  loadCanvasNamespaces,
  refreshAllSingleValueNodes,
  refreshAllChartNodes,
  abortInflightDataRequests,
  refreshTopologyNodes,
  scheduleTopologyInitialization,
  startInitialization,
  syncTopologyCanvasResources,
  toggleEditMode,
  onLoadedRefreshInterval,
  organizationId,
}: UseTopologyLifecycleParams) => {
  const [originalGraphState, setOriginalGraphState] =
    useState<Model.FromJSONData | null>(null);
  const [originalDefinitions, setOriginalDefinitions] = useState<
    UnifiedFilterDefinition[]
  >([]);
  const handleLoadTopologyRef = useRef(handleLoadTopology);
  const seenTopologyIdRef = useRef(selectedTopology?.data_id);
  const abortInflightDataRequestsRef = useRef(abortInflightDataRequests);
  abortInflightDataRequestsRef.current = abortInflightDataRequests;

  useEffect(() => {
    handleLoadTopologyRef.current = handleLoadTopology;
  }, [handleLoadTopology]);

  const handleEnterEditMode = useCallback(() => {
    if (state.graphInstance) {
      setOriginalGraphState(state.graphInstance.toJSON());
      setOriginalDefinitions([...definitions]);
    }
    toggleEditMode();
  }, [state.graphInstance, definitions, toggleEditMode]);

  const handleCancelEdit = useCallback(() => {
    if (state.graphInstance && originalGraphState) {
      state.graphInstance.fromJSON(originalGraphState);
    }
    const restoredDefs = [...originalDefinitions];
    const restoredValues = syncFilterValuesWithDefinitions(
      restoredDefs,
      appliedFilterValues,
    );
    setDefinitions(restoredDefs);
    setFilterValues(restoredValues);
    setAppliedFilterValues(restoredValues);
    // 先完成 fromJSON 绘制，再退出编辑态（收起组件库、触发 resize）
    requestAnimationFrame(() => {
      toggleEditMode();
    });
  }, [
    state.graphInstance,
    originalGraphState,
    originalDefinitions,
    appliedFilterValues,
    setDefinitions,
    setFilterValues,
    setAppliedFilterValues,
    toggleEditMode,
  ]);

  useEffect(() => {
    const detailController = new AbortController();
    if (seenTopologyIdRef.current !== selectedTopology?.data_id) {
      seenTopologyIdRef.current = selectedTopology?.data_id;
      abortInflightDataRequestsRef.current();
    }
    state.resetAllStates();
    startInitialization();
    clearOperationHistory();
    setDefinitions([]);
    setFilterValues({});
    setAppliedFilterValues({});
    setOriginalDefinitions([]);
    setNamespaceDraftId(undefined);
    setAppliedNamespaceId(undefined);

    clearRefreshTimer();

    if (selectedTopology?.data_id && state.graphInstance) {
      handleLoadTopologyRef
        .current(selectedTopology.data_id, detailController.signal)
        .then(async ({ filters: loadedFilters, refreshInterval }) => {
          if (detailController.signal.aborted) return;
          onLoadedRefreshInterval?.(refreshInterval ?? 0);
          const canvasDataSources = await syncTopologyCanvasResources();
          if (detailController.signal.aborted) return;
          if (canvasDataSources == null) {
            finishInitialization();
            return;
          }
          const autoBuiltFilters = buildFiltersFromNodes(
            state.graphInstance,
            canvasDataSources,
            loadedFilters,
          );

          const syncedValues = syncAndFillOrganizationFilterValues(
            autoBuiltFilters,
            {},
            organizationId,
          );
          if (autoBuiltFilters.length > 0) {
            setDefinitions(autoBuiltFilters);
            setFilterValues(syncedValues);
            setAppliedFilterValues(syncedValues);
            setOriginalDefinitions([...autoBuiltFilters]);
          }

          const namespaceIds = Array.from(
            collectTopologyNamespaceIds(state.graphInstance, canvasDataSources),
          );
          const initialNamespaceId =
            namespaceIds.length > 0 ? namespaceIds[0] : undefined;
          setNamespaceDraftId(initialNamespaceId);
          setAppliedNamespaceId(initialNamespaceId);

          scheduleTopologyInitialization(() => {
            refreshAllSingleValueNodes(
              syncedValues,
              autoBuiltFilters,
              initialNamespaceId,
            );
            refreshAllChartNodes(
              syncedValues,
              autoBuiltFilters,
              canvasDataSources,
              initialNamespaceId,
            );
            finishInitialization();
          });
        });
    } else if (!selectedTopology?.data_id && state.graphInstance) {
      void loadCanvasNamespaces([]);
      scheduleTopologyInitialization(() => {
        finishInitialization();
      });
    }

    return () => {
      detailController.abort();
      clearRefreshTimer();
    };
  }, [
    selectedTopology?.data_id,
    state.graphInstance,
    loadCanvasNamespaces,
    organizationId,
    scheduleTopologyInitialization,
    syncTopologyCanvasResources,
  ]);

  return {
    handleCancelEdit,
    handleEnterEditMode,
  };
};
