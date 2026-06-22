import { useCallback, useEffect, useRef, useState } from 'react';
import type React from 'react';
import type { Model } from '@antv/x6';
import type {
  FilterValue,
  UnifiedFilterDefinition,
} from '@/app/ops-analysis/types/dashBoard';
import type {
  TopologyProps,
  TopologyViewportConfig,
} from '@/app/ops-analysis/types/topology';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import { collectTopologyNamespaceIds } from '@/app/ops-analysis/utils/canvasResources';
import {
  buildFiltersFromNodes,
  syncFilterValuesWithDefinitions,
} from '../utils/namespaceUtils';
import { getTopologyViewportDraft } from '../utils/viewport';
import type { useTopologyState } from './useTopologyState';

interface UseTopologyLifecycleParams {
  selectedTopology: TopologyProps['selectedTopology'];
  state: ReturnType<typeof useTopologyState>;
  definitions: UnifiedFilterDefinition[];
  appliedFilterValues: Record<string, FilterValue>;
  appliedNamespaceId: number | undefined;
  viewportConfig: TopologyViewportConfig;
  setAppliedFilterValues: React.Dispatch<
    React.SetStateAction<Record<string, FilterValue>>
  >;
  setAppliedNamespaceId: (value: number | undefined) => void;
  setDefinitions: (definitions: UnifiedFilterDefinition[]) => void;
  setFilterValues: (values: Record<string, FilterValue>) => void;
  setNamespaceDraftId: (value: number | undefined) => void;
  setViewportConfig: (value: TopologyViewportConfig) => void;
  clearOperationHistory: () => void;
  clearRefreshTimer: () => void;
  finishInitialization: () => void;
  handleLoadTopology: (dataId: number | string) => Promise<{
    filters?: UnifiedFilterDefinition[];
    viewport?: TopologyViewportConfig | null;
  }>;
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
  refreshTopologyNodes: (
    scope: 'reload',
    values?: Record<string, FilterValue>,
    definitions?: UnifiedFilterDefinition[],
    namespaceId?: number,
  ) => void;
  scheduleTopologyInitialization: (callback: () => void) => void;
  startInitialization: () => void;
  syncTopologyCanvasResources: () => Promise<DatasourceItem[]>;
  toggleEditMode: () => void;
}

export const useTopologyLifecycle = ({
  selectedTopology,
  state,
  definitions,
  appliedFilterValues,
  appliedNamespaceId,
  viewportConfig,
  setAppliedFilterValues,
  setAppliedNamespaceId,
  setDefinitions,
  setFilterValues,
  setNamespaceDraftId,
  setViewportConfig,
  clearOperationHistory,
  clearRefreshTimer,
  finishInitialization,
  handleLoadTopology,
  loadCanvasNamespaces,
  refreshAllSingleValueNodes,
  refreshAllChartNodes,
  refreshTopologyNodes,
  scheduleTopologyInitialization,
  startInitialization,
  syncTopologyCanvasResources,
  toggleEditMode,
}: UseTopologyLifecycleParams) => {
  const [originalGraphState, setOriginalGraphState] =
    useState<Model.FromJSONData | null>(null);
  const [originalDefinitions, setOriginalDefinitions] = useState<
    UnifiedFilterDefinition[]
  >([]);
  const [originalViewportConfig, setOriginalViewportConfig] =
    useState<TopologyViewportConfig>(() => getTopologyViewportDraft(null));
  const handleLoadTopologyRef = useRef(handleLoadTopology);

  useEffect(() => {
    handleLoadTopologyRef.current = handleLoadTopology;
  }, [handleLoadTopology]);

  const handleEnterEditMode = useCallback(() => {
    if (state.graphInstance) {
      setOriginalGraphState(state.graphInstance.toJSON());
      setOriginalDefinitions([...definitions]);
      setOriginalViewportConfig(getTopologyViewportDraft(viewportConfig));
    }
    toggleEditMode();
  }, [state.graphInstance, definitions, toggleEditMode, viewportConfig]);

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
    setViewportConfig(getTopologyViewportDraft(originalViewportConfig));
    toggleEditMode();
    refreshTopologyNodes(
      'reload',
      restoredValues,
      restoredDefs,
      appliedNamespaceId,
    );
  }, [
    state.graphInstance,
    originalGraphState,
    originalDefinitions,
    appliedFilterValues,
    appliedNamespaceId,
    originalViewportConfig,
    setDefinitions,
    setFilterValues,
    setAppliedFilterValues,
    setViewportConfig,
    toggleEditMode,
    refreshTopologyNodes,
  ]);

  useEffect(() => {
    state.resetAllStates();
    startInitialization();
    clearOperationHistory();
    setDefinitions([]);
    setFilterValues({});
    setAppliedFilterValues({});
    setOriginalDefinitions([]);
    setViewportConfig(getTopologyViewportDraft(null));
    setOriginalViewportConfig(getTopologyViewportDraft(null));
    setNamespaceDraftId(undefined);
    setAppliedNamespaceId(undefined);

    clearRefreshTimer();

    if (selectedTopology?.data_id && state.graphInstance) {
      handleLoadTopologyRef
        .current(selectedTopology.data_id)
        .then(async ({ filters: loadedFilters, viewport }) => {
          const loadedViewport = getTopologyViewportDraft(viewport);
          setViewportConfig(loadedViewport);
          setOriginalViewportConfig(loadedViewport);
          const canvasDataSources = await syncTopologyCanvasResources();
          const autoBuiltFilters = buildFiltersFromNodes(
            state.graphInstance,
            canvasDataSources,
            loadedFilters,
          );

          const syncedValues = syncFilterValuesWithDefinitions(
            autoBuiltFilters,
            {},
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
      clearRefreshTimer();
    };
  }, [
    selectedTopology?.data_id,
    state.graphInstance,
    loadCanvasNamespaces,
    scheduleTopologyInitialization,
    syncTopologyCanvasResources,
  ]);

  return {
    handleCancelEdit,
    handleEnterEditMode,
  };
};
