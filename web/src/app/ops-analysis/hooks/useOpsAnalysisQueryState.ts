import { useCallback, useState } from 'react';
import type {
  FilterValue,
  UnifiedFilterDefinition,
} from '@/app/ops-analysis/types/dashBoard';
import {
  syncAndFillOrganizationFilterValues,
  syncFilterValuesWithDefinitions,
} from '@/app/ops-analysis/utils/unifiedFilterState';

interface QuerySnapshot {
  definitions: UnifiedFilterDefinition[];
  filterValues: Record<string, FilterValue>;
  appliedFilterValues: Record<string, FilterValue>;
  namespaceDraftId?: number;
  appliedNamespaceId?: number;
  organizationId?: string | number | null;
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
  const [organizationId, setOrganizationId] = useState<
    string | number | null | undefined
  >();

  const resetQueryState = useCallback((snapshot?: Partial<QuerySnapshot>) => {
    const nextDefinitions = snapshot?.definitions ?? [];
    const nextValues = syncAndFillOrganizationFilterValues(
      nextDefinitions,
      snapshot?.filterValues ?? {},
      snapshot?.organizationId,
    );
    const nextAppliedValues = syncAndFillOrganizationFilterValues(
      nextDefinitions,
      snapshot?.appliedFilterValues ?? nextValues,
      snapshot?.organizationId,
    );

    setDefinitionsState(nextDefinitions);
    setFilterValuesState(nextValues);
    setAppliedFilterValuesState(nextAppliedValues);
    setNamespaceDraftId(snapshot?.namespaceDraftId);
    setAppliedNamespaceId(snapshot?.appliedNamespaceId);
    setOrganizationId(snapshot?.organizationId);
    setFilterSearchVersion(0);
    setNamespaceSearchVersion(0);
  }, []);

  const applyFilterConfigConfirm = useCallback(
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

  const setDefinitions = applyFilterConfigConfirm;

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
      const nextValues = syncAndFillOrganizationFilterValues(
        definitions,
        values,
        organizationId,
      );
      setFilterValuesState(nextValues);
      setAppliedFilterValuesState(nextValues);
      setFilterSearchVersion((current) => current + 1);
    },
    [definitions, organizationId],
  );

  const applyNamespace = useCallback((namespaceId: number | undefined) => {
    setNamespaceDraftId(namespaceId);
    setAppliedNamespaceId(namespaceId);
    setNamespaceSearchVersion((current) => current + 1);
  }, []);

  const applyQuery = useCallback(
    (values: Record<string, FilterValue>, namespaceId: number | undefined) => {
      const nextValues = syncAndFillOrganizationFilterValues(
        definitions,
        values,
        organizationId,
      );
      const namespaceChanged = appliedNamespaceId !== namespaceId;
      setFilterValuesState(nextValues);
      setAppliedFilterValuesState(nextValues);
      setNamespaceDraftId(namespaceId);
      setAppliedNamespaceId(namespaceId);
      setFilterSearchVersion((current) => current + 1);
      if (namespaceChanged) {
        setNamespaceSearchVersion((current) => current + 1);
      }
    },
    [appliedNamespaceId, definitions, organizationId],
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
    applyFilterConfigConfirm,
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
