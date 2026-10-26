import { useCallback } from 'react';
import { useTranslation } from '@/utils/i18n';

import type {
  DashboardLayoutItem,
  DashboardWidgetLayoutItem,
  FilterBindings,
  FilterValue,
  UnifiedFilterDefinition,
} from '@/app/ops-analysis/types/dashBoard';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import type { DateRangeValue } from '@/app/ops-analysis/types/dateRange';
import { validateDateRangeValue } from '@/app/ops-analysis/utils/dateRange';
import {
  buildDefaultFilterBindings,
  discoverFollowedFilterParams,
  preserveUnfollowedFilterBindings,
} from '@/app/ops-analysis/utils/widgetDataTransform';
import {
  buildRelativeTimeRangeFilterValue,
} from '@/app/ops-analysis/utils/filterValue';
import {
  syncFilterValuesWithDefinitions as syncFilterValuesForDefinitions,
} from '@/app/ops-analysis/utils/unifiedFilterState';
import {
  collectDashboardNamespaceIds,
} from '@/app/ops-analysis/utils/canvasResources';
import {
  isDashboardWidgetItem,
} from '@/app/ops-analysis/utils/dashboardGroups';
import {
  ensureApplicationTopologyCanvasFilter,
  relabelApplicationTopologyFilters,
  withApplicationTopologyFilterBinding,
} from '@/app/ops-analysis/utils/applicationTopologyCanvasFilter';

export const resolveWidgetBindableParams = (
  valueConfig: DashboardWidgetLayoutItem['valueConfig'] | undefined,
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

export const buildFiltersFromDashboardLayout = ({
  layout,
  previousDefinitions,
  dataSources,
}: {
  layout: DashboardLayoutItem[];
  previousDefinitions: UnifiedFilterDefinition[];
  dataSources: DatasourceItem[];
}): UnifiedFilterDefinition[] => {
  const discoveredParams = discoverFollowedFilterParams(
    layout.filter(isDashboardWidgetItem).map((item) => {
      const dataSourceId = item.valueConfig?.dataSource;
      const normalizedId =
        typeof dataSourceId === 'string'
          ? parseInt(dataSourceId, 10)
          : dataSourceId;
      const dataSource = dataSources.find(
        (source) => source.id === normalizedId,
      );
      return {
        params: resolveWidgetBindableParams(item.valueConfig, dataSource),
        filterBindings: item.valueConfig?.filterBindings,
      };
    }),
  );

  const existingDefinitions = new Map(
    previousDefinitions.map((definition) => [definition.id, definition]),
  );
  const maxExistingOrder = previousDefinitions.reduce(
    (maxOrder, definition) => Math.max(maxOrder, definition.order ?? -1),
    -1,
  );
  let nextOrder = maxExistingOrder + 1;

  const rebuiltDefinitions = Array.from(discoveredParams.entries()).map(
    ([id, param]) => {
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

      if (param.type === 'dateRange') {
        defaultValue = validateDateRangeValue(defaultValue).valid
          && defaultValue !== null
          ? { ...(defaultValue as DateRangeValue) }
          : null;
      }

      return {
        id,
        key: param.name,
        name: existing?.name || param.alias_name || param.name,
        type: param.type,
        defaultValue,
        order: existing?.order ?? nextOrder++,
        enabled: existing?.enabled ?? true,
        inputMode: existing?.inputMode,
        options: existing?.options,
        inputConfig: existing ? existing.inputConfig : param.inputConfig,
      };
    },
  );

  return ensureApplicationTopologyCanvasFilter(
    rebuiltDefinitions.sort((a, b) => {
      const orderDiff = (a.order ?? 0) - (b.order ?? 0);
      if (orderDiff !== 0) return orderDiff;
      return a.id.localeCompare(b.id);
    }),
    layout as Parameters<typeof ensureApplicationTopologyCanvasFilter>[1],
    previousDefinitions,
  );
};

export const syncDashboardLayoutFilterBindings = (
  nextLayout: DashboardLayoutItem[],
  definitions: UnifiedFilterDefinition[],
  dataSources: DatasourceItem[],
): DashboardLayoutItem[] => {
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
      const preserved = preserveUnfollowedFilterBindings(
        existingBindings,
        currentParams,
        undefined,
      );
      if (JSON.stringify(existingBindings ?? undefined) === JSON.stringify(preserved)) {
        return item;
      }
      return {
        ...item,
        valueConfig: {
          ...item.valueConfig,
          filterBindings: preserved,
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

    const boundBindings = withApplicationTopologyFilterBinding(
      item.valueConfig?.chartType,
      item.valueConfig?.sceneWidgetType,
      Object.keys(prunedBindings).length ? prunedBindings : undefined,
      definitions,
    );

    const newBindings = preserveUnfollowedFilterBindings(
      existingBindings,
      currentParams,
      boundBindings && Object.keys(boundBindings).length
        ? boundBindings
        : undefined,
    );

    if (JSON.stringify(existingBindings ?? undefined) === JSON.stringify(newBindings)) {
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
};

export const useDashboardLayoutSync = ({
  dataSources,
  namespaceDraftId,
  appliedNamespaceId,
  applyQueryState,
  setDefinitions,
  setFilterValues,
}: UseDashboardLayoutSyncOptions) => {
  const { t } = useTranslation();
  const buildFiltersFromLayout = useCallback(
    (
      nextLayout: DashboardLayoutItem[],
      previousDefinitions: UnifiedFilterDefinition[],
    ): UnifiedFilterDefinition[] =>
      relabelApplicationTopologyFilters({
        filters: buildFiltersFromDashboardLayout({
          layout: nextLayout,
          previousDefinitions,
          dataSources,
        }),
      }, {
        system: t('dashboard.applicationTopologyFilterName'),
        depth: t('dashboard.applicationTopologyDepth'),
      }).filters ?? [],
    [dataSources, t],
  );

  const syncLayoutFilterBindings = useCallback(
    (
      nextLayout: DashboardLayoutItem[],
      definitions: UnifiedFilterDefinition[],
    ) => syncDashboardLayoutFilterBindings(nextLayout, definitions, dataSources),
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
