import { useCallback, useState } from 'react';
import type {
  FilterValue,
  UnifiedFilterDefinition,
} from '@/app/ops-analysis/types/dashBoard';
import { syncFilterValuesWithDefinitions } from '@/app/ops-analysis/utils/unifiedFilterState';

interface QuerySnapshot {
  definitions: UnifiedFilterDefinition[];
  filterValues: Record<string, FilterValue>;
  appliedFilterValues: Record<string, FilterValue>;
  namespaceDraftId?: number;
  appliedNamespaceId?: number;
}

export const useOpsAnalysisQueryState = () => {
  const [definitions, setDefinitionsState] = useState<
    UnifiedFilterDefinition[]
  >([]);
  const [filterValues, setFilterValuesState] = useState<
    Record<string, FilterValue>
  >({});
  const [appliedFilterValues, setAppliedFilterValuesState] = useState<
    Record<string, FilterValue>
  >({});
  const [namespaceDraftId, setNamespaceDraftId] = useState<
    number | undefined
  >();
  const [appliedNamespaceId, setAppliedNamespaceId] = useState<
    number | undefined
  >();
  const [filterSearchVersion, setFilterSearchVersion] = useState(0);
  const [namespaceSearchVersion, setNamespaceSearchVersion] = useState(0);

  const resetQueryState = useCallback((snapshot?: Partial<QuerySnapshot>) => {
    const nextDefinitions = snapshot?.definitions ?? [];
    const nextValues = syncFilterValuesWithDefinitions(
      nextDefinitions,
      snapshot?.filterValues ?? {},
    );
    const nextAppliedValues = syncFilterValuesWithDefinitions(
      nextDefinitions,
      snapshot?.appliedFilterValues ?? nextValues,
    );

    setDefinitionsState(nextDefinitions);
    setFilterValuesState(nextValues);
    setAppliedFilterValuesState(nextAppliedValues);
    setNamespaceDraftId(snapshot?.namespaceDraftId);
    setAppliedNamespaceId(snapshot?.appliedNamespaceId);
    setFilterSearchVersion(0);
    setNamespaceSearchVersion(0);
  }, []);

  const setDefinitions = useCallback(
    (nextDefinitions: UnifiedFilterDefinition[]) => {
      setDefinitionsState(nextDefinitions);
      setFilterValuesState((current) =>
        syncFilterValuesWithDefinitions(nextDefinitions, current),
      );
      setAppliedFilterValuesState((current) =>
        syncFilterValuesWithDefinitions(nextDefinitions, current),
      );
    },
    [],
  );

  const setFilterValues = useCallback(
    (values: Record<string, FilterValue>) => {
      setFilterValuesState({ ...values });
    },
    [],
  );

  const setAppliedFilterValues = useCallback(
    (values: Record<string, FilterValue>) => {
      setAppliedFilterValuesState({ ...values });
    },
    [],
  );

  const applyFilters = useCallback(
    (values: Record<string, FilterValue>) => {
      const nextValues = syncFilterValuesWithDefinitions(definitions, values);
      setFilterValuesState(nextValues);
      setAppliedFilterValuesState(nextValues);
      setFilterSearchVersion((current) => current + 1);
    },
    [definitions],
  );

  const applyNamespace = useCallback((namespaceId: number | undefined) => {
    setNamespaceDraftId(namespaceId);
    setAppliedNamespaceId(namespaceId);
    setNamespaceSearchVersion((current) => current + 1);
  }, []);

  const applyQuery = useCallback(
    (values: Record<string, FilterValue>, namespaceId: number | undefined) => {
      const nextValues = syncFilterValuesWithDefinitions(definitions, values);
      setFilterValuesState(nextValues);
      setAppliedFilterValuesState(nextValues);
      setNamespaceDraftId(namespaceId);
      setAppliedNamespaceId(namespaceId);
      setFilterSearchVersion((current) => current + 1);
      setNamespaceSearchVersion((current) => current + 1);
    },
    [definitions],
  );

  return {
    definitions,
    filterValues,
    appliedFilterValues,
    namespaceDraftId,
    appliedNamespaceId,
    filterSearchVersion,
    namespaceSearchVersion,
    setDefinitions,
    setFilterValues,
    setAppliedFilterValues,
    setNamespaceDraftId,
    setAppliedNamespaceId,
    resetQueryState,
    applyFilters,
    applyNamespace,
    applyQuery,
  };
};
