import { useCallback } from 'react';

import type {
  DashboardLayoutItem,
  FilterBindings,
  FilterValue,
  UnifiedFilterDefinition,
} from '@/app/ops-analysis/types/dashBoard';
import type {
  DatasourceItem,
  ParamItem,
} from '@/app/ops-analysis/types/dataSource';
import {
  buildDefaultFilterBindings,
  getBindableFilterParams,
  getFilterDefinitionId,
} from '@/app/ops-analysis/utils/widgetDataTransform';
import {
  buildRelativeTimeRangeFilterValue,
  normalizeTimeRangeFilterValue,
} from '@/app/ops-analysis/utils/filterValue';
import {
  collectDashboardNamespaceIds,
} from '@/app/ops-analysis/utils/canvasResources';
import {
  isDashboardWidgetItem,
} from '@/app/ops-analysis/utils/dashboardGroups';

export const resolveWidgetBindableParams = (
  valueConfig: DashboardLayoutItem['valueConfig'] | undefined,
  dataSource?: DatasourceItem,
) => {
  const widgetParams = valueConfig?.dataSourceParams;

  if (Array.isArray(widgetParams) && widgetParams.length > 0) {
    return widgetParams;
  }

  return dataSource?.params;
};

interface UseDashboardLayoutSyncOptions {
  dataSources: DatasourceItem[];
  namespaceDraftId: number | undefined;
  appliedNamespaceId: number | undefined;
  applyQueryState: (
    nextDefinitions: UnifiedFilterDefinition[],
    nextValues: Record<string, FilterValue>,
    nextNamespaceId: number | undefined,
  ) => void;
  setDefinitions: (definitions: UnifiedFilterDefinition[]) => void;
  setFilterValues: (values: Record<string, FilterValue>) => void;
}

export const syncFilterValuesForDefinitions = (
  nextDefinitions: UnifiedFilterDefinition[],
  currentValues: Record<string, FilterValue>,
): Record<string, FilterValue> => {
  const allowedIds = new Set(nextDefinitions.map((definition) => definition.id));
  const updatedValues = Object.entries(currentValues).reduce<
    Record<string, FilterValue>
  >((acc, [filterId, value]) => {
    if (allowedIds.has(filterId)) {
      acc[filterId] = value;
    }
    return acc;
  }, {});

  nextDefinitions.forEach((def) => {
    if (
      def.enabled &&
      def.defaultValue !== null &&
      def.defaultValue !== undefined &&
      (updatedValues[def.id] === undefined || updatedValues[def.id] === null)
    ) {
      if (def.type === 'timeRange') {
        const normalizedValue = normalizeTimeRangeFilterValue(def.defaultValue);
        if (normalizedValue) {
          updatedValues[def.id] = normalizedValue;
        }
      } else {
        updatedValues[def.id] = def.defaultValue;
      }
    }
  });

  return updatedValues;
};

export const useDashboardLayoutSync = ({
  dataSources,
  namespaceDraftId,
  appliedNamespaceId,
  applyQueryState,
  setDefinitions,
  setFilterValues,
}: UseDashboardLayoutSyncOptions) => {
  const buildFiltersFromLayout = useCallback(
    (
      nextLayout: DashboardLayoutItem[],
      previousDefinitions: UnifiedFilterDefinition[],
    ): UnifiedFilterDefinition[] => {
      const discoveredParams = new Map<
        string,
        ParamItem & { type: 'string' | 'timeRange' }
      >();

      nextLayout.forEach((item) => {
        if (!isDashboardWidgetItem(item)) {
          return;
        }

        const dataSourceId = item.valueConfig?.dataSource;
        const normalizedId =
          typeof dataSourceId === 'string'
            ? parseInt(dataSourceId, 10)
            : dataSourceId;
        const dataSource = dataSources.find(
          (source) => source.id === normalizedId,
        );
        const params = resolveWidgetBindableParams(item.valueConfig, dataSource);

        getBindableFilterParams(params).forEach((param) => {
          const id = getFilterDefinitionId(param.name, param.type);
          if (!discoveredParams.has(id)) {
            discoveredParams.set(id, param);
          }
        });
      });

      const existingDefinitions = new Map(
        previousDefinitions.map((definition) => [definition.id, definition]),
      );

      return Array.from(discoveredParams.entries()).map(
        ([id, param], index) => {
          const existing =
            existingDefinitions.get(id) ||
            previousDefinitions.find(
              (definition) =>
                definition.key === param.name && definition.type === param.type,
            );

          let defaultValue: FilterValue = null;
          if (existing?.defaultValue !== undefined) {
            defaultValue = existing.defaultValue;
          } else if (param.value !== undefined && param.value !== null) {
            if (param.type === 'timeRange' && typeof param.value === 'number') {
              defaultValue = buildRelativeTimeRangeFilterValue(param.value);
            } else {
              defaultValue = param.value as FilterValue;
            }
          }

          return {
            id,
            key: param.name,
            name: existing?.name || param.alias_name || param.name,
            type: param.type,
            defaultValue,
            order: index,
            enabled: existing?.enabled ?? true,
          };
        },
      );
    },
    [dataSources],
  );

  const syncLayoutFilterBindings = useCallback(
    (
      nextLayout: DashboardLayoutItem[],
      definitions: UnifiedFilterDefinition[],
    ) => {
      const allowedIds = new Set(
        definitions.map((definition) => definition.id),
      );

      return nextLayout.map((item) => {
        if (!isDashboardWidgetItem(item)) {
          return item;
        }

        const existingBindings = item.valueConfig?.filterBindings;
        const dataSourceId = item.valueConfig?.dataSource;
        const normalizedId =
          typeof dataSourceId === 'string'
            ? parseInt(dataSourceId, 10)
            : dataSourceId;
        const dataSource = dataSources.find(
          (source) => source.id === normalizedId,
        );
        const currentParams = resolveWidgetBindableParams(
          item.valueConfig,
          dataSource,
        );

        const autoBindings = buildDefaultFilterBindings(
          currentParams,
          definitions,
          existingBindings,
        );

        if (!autoBindings) {
          if (existingBindings === undefined) {
            return item;
          }

          return {
            ...item,
            valueConfig: {
              ...item.valueConfig,
              filterBindings: undefined,
            },
          };
        }

        const prunedBindings = Object.entries(autoBindings).reduce<FilterBindings>(
          (acc, [filterId, enabled]) => {
            if (allowedIds.has(filterId)) {
              acc[filterId] = enabled;
            }
            return acc;
          },
          {},
        );

        const newBindings = Object.keys(prunedBindings).length
          ? prunedBindings
          : undefined;

        if (JSON.stringify(existingBindings) === JSON.stringify(newBindings)) {
          return item;
        }

        return {
          ...item,
          valueConfig: {
            ...item.valueConfig,
            filterBindings: newBindings,
          },
        };
      });
    },
    [dataSources],
  );

  const syncFilterValuesWithDefinitions = useCallback(
    (
      nextDefinitions: UnifiedFilterDefinition[],
      currentValues: Record<string, FilterValue>,
    ): Record<string, FilterValue> =>
      syncFilterValuesForDefinitions(nextDefinitions, currentValues),
    [],
  );

  const resolveLayoutNamespaceId = useCallback(
    (
      nextLayout: DashboardLayoutItem[],
      canvasDataSources: DatasourceItem[],
    ) => {
      const nextWidgetLayout = nextLayout.filter(isDashboardWidgetItem);

      if (namespaceDraftId !== undefined) {
        return namespaceDraftId;
      }
      if (appliedNamespaceId !== undefined) {
        return appliedNamespaceId;
      }

      const namespaceIds = Array.from(
        collectDashboardNamespaceIds(nextWidgetLayout, canvasDataSources),
      );
      return namespaceIds[0];
    },
    [appliedNamespaceId, namespaceDraftId],
  );

  const syncFilterStateAfterLayoutChange = useCallback(
    (
      nextDefinitions: UnifiedFilterDefinition[],
      nextDraftValues: Record<string, FilterValue>,
      nextAppliedValues: Record<string, FilterValue>,
    ) => {
      setDefinitions(nextDefinitions);
      setFilterValues(nextDraftValues);
      applyQueryState(nextDefinitions, nextAppliedValues, appliedNamespaceId);
    },
    [appliedNamespaceId, applyQueryState, setDefinitions, setFilterValues],
  );

  return {
    buildFiltersFromLayout,
    resolveLayoutNamespaceId,
    syncFilterStateAfterLayoutChange,
    syncFilterValuesWithDefinitions,
    syncLayoutFilterBindings,
  };
};
