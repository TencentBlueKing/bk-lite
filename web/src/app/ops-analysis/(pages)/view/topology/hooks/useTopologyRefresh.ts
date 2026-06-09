import { useCallback, useEffect } from 'react';
import type React from 'react';
import { buildDefaultFilterBindings } from '@/app/ops-analysis/utils/widgetDataTransform';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import type {
  FilterValue,
  UnifiedFilterDefinition,
} from '@/app/ops-analysis/types/dashBoard';
import type { TopologyNodeData } from '@/app/ops-analysis/types/topology';
import { collectTopologyNamespaceIds } from '@/app/ops-analysis/utils/canvasResources';
import {
  buildFiltersFromNodes,
  syncFilterValuesWithDefinitions,
} from '../utils/namespaceUtils';

type RefreshScope =
  | 'filter-search'
  | 'namespace-search'
  | 'combined-search'
  | 'reload';

interface NamespaceOption {
  value: number;
}

interface PostMutationPayload {
  definitions: UnifiedFilterDefinition[];
  appliedValues: Record<string, FilterValue>;
  dataSources: DatasourceItem[];
  namespaceId: number | undefined;
}

interface UseTopologyRefreshControllerParams {
  graphInstance: unknown;
  namespaceOptions: NamespaceOption[];
  refreshTimerRef: React.MutableRefObject<NodeJS.Timeout | null>;
  dataSources: DatasourceItem[];
  definitions: UnifiedFilterDefinition[];
  filterValues: Record<string, FilterValue>;
  appliedFilterValues: Record<string, FilterValue>;
  appliedNamespaceId: number | undefined;
  namespaceDraftId: number | undefined;
  setAppliedFilterValues: React.Dispatch<
    React.SetStateAction<Record<string, FilterValue>>
  >;
  setAppliedNamespaceId: (value: number | undefined) => void;
  setDefinitions: (definitions: UnifiedFilterDefinition[]) => void;
  setFilterValues: (values: Record<string, FilterValue>) => void;
  setNamespaceDraftId: (value: number | undefined) => void;
  setNodeChangeKey: React.Dispatch<React.SetStateAction<number>>;
  syncTopologyCanvasResources: () => Promise<DatasourceItem[]>;
  refreshAllSingleValueNodes: (
    values?: Record<string, FilterValue>,
    definitions?: UnifiedFilterDefinition[],
    namespaceId?: number,
    dataSources?: DatasourceItem[],
    shouldRefreshNode?: (
      nodeData: TopologyNodeData,
      dataSource?: DatasourceItem,
    ) => boolean,
  ) => void;
  refreshAllChartNodes: (
    values?: Record<string, FilterValue>,
    definitions?: UnifiedFilterDefinition[],
    dataSources?: DatasourceItem[],
    namespaceId?: number,
    shouldRefreshNode?: (
      nodeData: TopologyNodeData,
      dataSource?: DatasourceItem,
    ) => boolean,
  ) => void;
  updateDefinitions: (definitions: UnifiedFilterDefinition[]) => void;
}

export const useTopologyRefresh = ({
  graphInstance,
  namespaceOptions,
  refreshTimerRef,
  dataSources,
  definitions,
  filterValues,
  appliedFilterValues,
  appliedNamespaceId,
  namespaceDraftId,
  setAppliedFilterValues,
  setAppliedNamespaceId,
  setDefinitions,
  setFilterValues,
  setNamespaceDraftId,
  setNodeChangeKey,
  syncTopologyCanvasResources,
  refreshAllSingleValueNodes,
  refreshAllChartNodes,
  updateDefinitions,
}: UseTopologyRefreshControllerParams) => {
  const refreshTopologyNodes = useCallback(
    (
      scope: RefreshScope,
      nextValues = appliedFilterValues,
      nextDefinitions = definitions,
      nextNamespaceId = appliedNamespaceId,
    ) => {
      let shouldRefreshNode:
        | ((nodeData: TopologyNodeData, dataSource?: DatasourceItem) => boolean)
        | undefined;

      if (scope !== 'reload') {
        shouldRefreshNode = (
          nodeData: TopologyNodeData,
          dataSource?: DatasourceItem,
        ) => {
          const bindings = buildDefaultFilterBindings(
            nodeData.valueConfig?.dataSourceParams?.length
              ? nodeData.valueConfig.dataSourceParams
              : dataSource?.params,
            nextDefinitions,
            nodeData.valueConfig?.filterBindings,
          );
          const hasActiveFilterBinding = Boolean(
            bindings && Object.values(bindings).some((enabled) => enabled),
          );
          const usesNamespace = Boolean(
            Array.isArray(dataSource?.namespaces) &&
            dataSource.namespaces.length > 0,
          );

          if (scope === 'filter-search') {
            return hasActiveFilterBinding;
          }
          if (scope === 'namespace-search') {
            return usesNamespace;
          }

          return hasActiveFilterBinding || usesNamespace;
        };
      }

      refreshAllSingleValueNodes(
        nextValues,
        nextDefinitions,
        nextNamespaceId,
        dataSources,
        shouldRefreshNode,
      );
      refreshAllChartNodes(
        nextValues,
        nextDefinitions,
        dataSources,
        nextNamespaceId,
        shouldRefreshNode,
      );
    },
    [
      appliedFilterValues,
      appliedNamespaceId,
      dataSources,
      definitions,
      refreshAllChartNodes,
      refreshAllSingleValueNodes,
    ],
  );

  useEffect(() => {
    if (
      !graphInstance ||
      namespaceOptions.length === 0 ||
      appliedNamespaceId !== undefined
    ) {
      return;
    }

    const initialNamespaceId = namespaceOptions[0].value;
    setNamespaceDraftId(initialNamespaceId);
    setAppliedNamespaceId(initialNamespaceId);
    refreshTopologyNodes(
      'namespace-search',
      appliedFilterValues,
      definitions,
      initialNamespaceId,
    );
  }, [
    graphInstance,
    namespaceOptions,
    appliedNamespaceId,
    appliedFilterValues,
    definitions,
    refreshTopologyNodes,
    setAppliedNamespaceId,
    setNamespaceDraftId,
  ]);

  const clearRefreshTimer = useCallback(() => {
    if (refreshTimerRef.current) {
      clearInterval(refreshTimerRef.current);
      refreshTimerRef.current = null;
    }
  }, [refreshTimerRef]);

  const handleFrequencyChange = useCallback(
    (frequency: number) => {
      clearRefreshTimer();

      if (frequency > 0) {
        refreshTimerRef.current = setInterval(() => {
          refreshTopologyNodes('reload');
        }, frequency);
      }
    },
    [clearRefreshTimer, refreshTimerRef, refreshTopologyNodes],
  );

  const handleRefresh = useCallback(() => {
    setAppliedFilterValues(filterValues);
    setAppliedNamespaceId(namespaceDraftId);
    refreshTopologyNodes('reload', filterValues, definitions, namespaceDraftId);
  }, [
    definitions,
    filterValues,
    namespaceDraftId,
    refreshTopologyNodes,
    setAppliedFilterValues,
    setAppliedNamespaceId,
  ]);

  const handleFilterSearch = useCallback(
    (values: Record<string, FilterValue>) => {
      const namespaceChanged = namespaceDraftId !== appliedNamespaceId;
      setFilterValues(values);
      setAppliedFilterValues(values);
      setAppliedNamespaceId(namespaceDraftId);
      refreshTopologyNodes(
        namespaceChanged ? 'combined-search' : 'filter-search',
        values,
        definitions,
        namespaceDraftId,
      );
    },
    [
      appliedNamespaceId,
      definitions,
      namespaceDraftId,
      refreshTopologyNodes,
      setAppliedFilterValues,
      setAppliedNamespaceId,
      setFilterValues,
    ],
  );

  const handleFilterConfigConfirm = useCallback(
    (newDefinitions: UnifiedFilterDefinition[]) => {
      updateDefinitions(newDefinitions);
      setFilterValues(
        syncFilterValuesWithDefinitions(newDefinitions, filterValues),
      );
      setAppliedFilterValues((prev) =>
        syncFilterValuesWithDefinitions(newDefinitions, prev),
      );
    },
    [filterValues, setAppliedFilterValues, setFilterValues, updateDefinitions],
  );

  const resolveTopologyNamespaceId = useCallback(
    (canvasDataSources: DatasourceItem[]) => {
      if (namespaceDraftId !== undefined) {
        return namespaceDraftId;
      }
      if (appliedNamespaceId !== undefined) {
        return appliedNamespaceId;
      }

      const namespaceIds = Array.from(
        collectTopologyNamespaceIds(graphInstance as any, canvasDataSources),
      );
      return namespaceIds[0];
    },
    [appliedNamespaceId, graphInstance, namespaceDraftId],
  );

  const scheduleTopologyPostMutation = useCallback(
    (callback?: (payload: PostMutationPayload) => void) => {
      setTimeout(() => {
        const newDefinitions = buildFiltersFromNodes(
          graphInstance as any,
          dataSources,
          definitions,
        );
        const syncedValues = syncFilterValuesWithDefinitions(
          newDefinitions,
          filterValues,
        );
        const nextAppliedValues = syncFilterValuesWithDefinitions(
          newDefinitions,
          appliedFilterValues,
        );

        setDefinitions(newDefinitions);
        setFilterValues(syncedValues);
        setAppliedFilterValues(nextAppliedValues);
        setNodeChangeKey((prev) => prev + 1);
        void syncTopologyCanvasResources().then((canvasDataSources) => {
          callback?.({
            definitions: newDefinitions,
            appliedValues: nextAppliedValues,
            dataSources: canvasDataSources,
            namespaceId: resolveTopologyNamespaceId(canvasDataSources),
          });
        });
      }, 100);
    },
    [
      appliedFilterValues,
      dataSources,
      definitions,
      filterValues,
      graphInstance,
      resolveTopologyNamespaceId,
      setAppliedFilterValues,
      setDefinitions,
      setFilterValues,
      setNodeChangeKey,
      syncTopologyCanvasResources,
    ],
  );

  const scheduleTopologyInitialization = useCallback((callback: () => void) => {
    setTimeout(callback, 100);
  }, []);

  const rebuildFiltersFromNodes = useCallback(() => {
    scheduleTopologyPostMutation();
  }, [scheduleTopologyPostMutation]);

  return {
    clearRefreshTimer,
    handleFilterConfigConfirm,
    handleFilterSearch,
    handleFrequencyChange,
    handleRefresh,
    rebuildFiltersFromNodes,
    refreshTopologyNodes,
    scheduleTopologyInitialization,
    scheduleTopologyPostMutation,
  };
};
