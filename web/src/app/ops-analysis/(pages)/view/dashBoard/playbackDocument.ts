import type {
  DashboardLayoutItem,
  FilterValue,
  OtherConfig,
  UnifiedFilterDefinition,
} from '@/app/ops-analysis/types/dashBoard';
import { normalizeCanvasRefreshInterval } from '@/app/ops-analysis/utils/canvasRefreshInterval';
import {
  deserializeDashboardGridStackLayout,
} from '@/app/ops-analysis/utils/dashboardGridStack';
import { migrateDashboardGridLayout } from '@/app/ops-analysis/utils/dashboardGridRows';
import { isDashboardWidgetItem } from '@/app/ops-analysis/utils/dashboardGroups';
import {
  migrateFilterBindings,
  migrateParamItemsFromStringList,
  logStringParamMigrationWarnings,
} from '@/app/ops-analysis/utils/stringParamMultipleMigrate';
import {
  applySelectedOrganizationToFilterValues,
  fillMissingOrganizationFilterValues,
  normalizeStoredFilterState,
} from '@/app/ops-analysis/utils/unifiedFilterState';

export interface DashboardPlaybackDetail {
  view_sets?: unknown;
  other?: OtherConfig;
  refresh_interval?: unknown;
  filters?: unknown;
}

export interface DashboardPlaybackDocument {
  layout: DashboardLayoutItem[];
  other: OtherConfig;
  refreshInterval: number;
  definitions: UnifiedFilterDefinition[];
  values: Record<string, FilterValue>;
}

/** 把已缓存的仪表盘详情收成可直接铺上的布局，不发部件请求。 */
export const prepareDashboardPlaybackDocument = (
  detail: DashboardPlaybackDetail,
  options: {
    canvasId: string | number;
    labelFilters: (filters: UnifiedFilterDefinition[]) => UnifiedFilterDefinition[];
    syncValues: (
      definitions: UnifiedFilterDefinition[],
      values: Record<string, FilterValue>,
    ) => Record<string, FilterValue>;
    organizationId: string | number | null | undefined;
    homepageMode: boolean;
    renderMode: boolean;
    renderFilterValues?: Record<string, FilterValue>;
  },
): DashboardPlaybackDocument => {
  const preparedLayout = deserializeDashboardGridStackLayout(detail.view_sets).map((item) => {
    if (!isDashboardWidgetItem(item) || !item.valueConfig) {
      return item;
    }
    const valueConfig = item.valueConfig;
    return {
      ...item,
      valueConfig: {
        ...valueConfig,
        ...(valueConfig.filterBindings
          ? { filterBindings: migrateFilterBindings(valueConfig.filterBindings) }
          : {}),
        ...(valueConfig.dataSourceParams
          ? (() => {
            const migratedParams = migrateParamItemsFromStringList(valueConfig.dataSourceParams);
            logStringParamMigrationWarnings(migratedParams.warnings, {
              canvasId: options.canvasId,
            });
            return { dataSourceParams: migratedParams.params };
          })()
          : {}),
      },
    };
  });
  const migratedGrid = migrateDashboardGridLayout(preparedLayout, detail.other || {});
  const storedFilters = normalizeStoredFilterState(
    detail.filters,
    options.renderMode ? (options.renderFilterValues ?? {}) : {},
    { canvasId: options.canvasId },
  );
  const definitions = options.labelFilters(storedFilters.definitions);
  const filledValues = fillMissingOrganizationFilterValues(
    definitions,
    options.syncValues(definitions, storedFilters.values),
    options.organizationId,
  );
  const values = options.homepageMode
    ? applySelectedOrganizationToFilterValues(definitions, filledValues, options.organizationId)
    : filledValues;
  return {
    layout: migratedGrid.layout,
    other: migratedGrid.other,
    refreshInterval: normalizeCanvasRefreshInterval(detail.refresh_interval),
    definitions,
    values,
  };
};
