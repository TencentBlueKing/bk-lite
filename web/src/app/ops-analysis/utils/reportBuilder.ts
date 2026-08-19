import type { DatasourceItem, ParamItem } from '@/app/ops-analysis/types/dataSource';
import type {
  FilterBindings,
  FilterValue,
  UnifiedFilterDefinition,
  WidgetConfig,
} from '@/app/ops-analysis/types/dashBoard';
import type { DateRangeValue } from '@/app/ops-analysis/types/dateRange';
import type {
  ReportSection,
  ReportViewSets,
} from '@/app/ops-analysis/types/report';
import { validateDateRangeValue } from './dateRange';
import { buildRelativeTimeRangeFilterValue } from './filterValue';
import { isChartTypeSupportedOnSurface } from './chartTypeSurface';
import { normalizeStoredFilterDefinitions } from './unifiedFilterState';
import {
  type BindableParamType,
  buildDefaultFilterBindings,
  getBindableFilterParams,
  getFilterDefinitionId,
} from './widgetDataTransform';

export const EMPTY_REPORT_VIEW_SETS: ReportViewSets = {
  schema_version: 1,
  filters: [],
  sections: [],
};

export interface ReportLoadGuard {
  currentRequestId: number;
}

export const createReportLoadGuard = (): ReportLoadGuard => ({ currentRequestId: 0 });
export const beginReportLoad = (guard: ReportLoadGuard) => ++guard.currentRequestId;
export const invalidateReportLoads = (guard: ReportLoadGuard) => {
  guard.currentRequestId += 1;
};
export const isCurrentReportLoad = (guard: ReportLoadGuard, requestId: number) =>
  guard.currentRequestId === requestId;

/** 只有详情加载成功拿到乐观锁令牌后才允许进入编辑，避免空草稿覆盖服务端报表。 */
export const canEnterReportEdit = ({
  reportId,
  isBuiltIn,
  savedVersion,
  loading,
}: {
  reportId?: string | number | null;
  isBuiltIn?: boolean;
  savedVersion: string;
  loading: boolean;
}): boolean => Boolean(reportId) && Boolean(savedVersion) && !isBuiltIn && !loading;

const isRecord = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === 'object' && !Array.isArray(value);

const normalizeSection = (value: unknown, index: number): ReportSection => {
  if (!isRecord(value)) {
    throw new Error(`sections[${index}] 必须是对象`);
  }
  const id = typeof value.id === 'string' ? value.id.trim() : '';
  if (!id) {
    throw new Error(`sections[${index}].id 必须是非空字符串`);
  }
  if (!isRecord(value.valueConfig)) {
    throw new Error(`sections[${index}].valueConfig 必须是对象`);
  }
  const chartType = value.valueConfig.chartType;
  if (
    typeof chartType !== 'string' ||
    !isChartTypeSupportedOnSurface(chartType, 'report')
  ) {
    throw new Error(`sections[${index}].valueConfig.chartType 当前不受支持`);
  }
  return {
    id,
    valueConfig: {
      ...value.valueConfig,
      chartType,
      name:
        typeof value.valueConfig.name === 'string'
          ? value.valueConfig.name
          : '',
    },
  } as ReportSection;
};

export const normalizeReportViewSets = (value: unknown): ReportViewSets => {
  if (!isRecord(value)) {
    return EMPTY_REPORT_VIEW_SETS;
  }
  if (value.schema_version !== undefined && value.schema_version !== 1) {
    throw new Error(`schema_version 仅支持 1，收到 ${String(value.schema_version)}`);
  }
  const sections = Array.isArray(value.sections) ? value.sections : [];
  const normalizedSections = sections.map(normalizeSection);
  const ids = new Set(normalizedSections.map((section) => section.id));
  if (ids.size !== normalizedSections.length) {
    throw new Error('报表组件 ID 不能重复');
  }
  return {
    schema_version: 1,
    filters: normalizeStoredFilterDefinitions(value.filters),
    sections: normalizedSections,
  };
};

export const isReportDraftDirty = (
  saved: ReportViewSets,
  draft: ReportViewSets,
) => JSON.stringify(saved) !== JSON.stringify(draft);

export const appendReportSection = (
  viewSets: ReportViewSets,
  section: ReportSection,
): ReportViewSets => ({
  ...viewSets,
  sections: [...viewSets.sections, section],
});

export const updateReportSection = (
  viewSets: ReportViewSets,
  sectionId: string,
  valueConfig: WidgetConfig,
): ReportViewSets => ({
  ...viewSets,
  sections: viewSets.sections.map((section) =>
    section.id === sectionId ? { ...section, valueConfig } : section,
  ),
});

export const removeReportSection = (
  viewSets: ReportViewSets,
  sectionId: string,
): ReportViewSets => ({
  ...viewSets,
  sections: viewSets.sections.filter((section) => section.id !== sectionId),
});

export const reorderReportSection = (
  viewSets: ReportViewSets,
  activeId: string,
  overId: string,
): ReportViewSets => {
  const oldIndex = viewSets.sections.findIndex((section) => section.id === activeId);
  const newIndex = viewSets.sections.findIndex((section) => section.id === overId);
  if (oldIndex < 0 || newIndex < 0 || oldIndex === newIndex) return viewSets;
  const sections = [...viewSets.sections];
  const [moved] = sections.splice(oldIndex, 1);
  sections.splice(newIndex, 0, moved);
  return { ...viewSets, sections };
};

const resolveSectionDataSource = (
  dataSourceId: WidgetConfig['dataSource'],
  dataSources: DatasourceItem[],
) => {
  if (dataSourceId === undefined) return undefined;
  const id = typeof dataSourceId === 'string' ? parseInt(dataSourceId, 10) : dataSourceId;
  return dataSources.find((source) => source.id === id);
};

const resolveSectionBindableParams = (
  valueConfig: WidgetConfig,
  dataSource?: DatasourceItem,
) => {
  const widgetParams = valueConfig.dataSourceParams;
  if (Array.isArray(widgetParams) && widgetParams.length > 0) {
    return widgetParams;
  }
  return dataSource?.params;
};

export const buildFiltersFromReportSections = (
  sections: ReportSection[],
  previousDefinitions: UnifiedFilterDefinition[],
  dataSources: DatasourceItem[],
): UnifiedFilterDefinition[] => {
  const discoveredParams = new Map<string, ParamItem & { type: BindableParamType }>();

  sections.forEach((section) => {
    const dataSource = resolveSectionDataSource(section.valueConfig.dataSource, dataSources);
    getBindableFilterParams(
      resolveSectionBindableParams(section.valueConfig, dataSource),
    ).forEach((param) => {
      const id = getFilterDefinitionId(param.name, param.type);
      if (!discoveredParams.has(id)) {
        discoveredParams.set(id, param);
      }
    });
  });

  const existingDefinitions = new Map(
    previousDefinitions.map((definition) => [definition.id, definition]),
  );
  const maxExistingOrder = previousDefinitions.reduce(
    (maxOrder, definition) => Math.max(maxOrder, definition.order ?? -1),
    -1,
  );
  let nextOrder = maxExistingOrder + 1;

  return Array.from(discoveredParams.entries())
    .map(([id, param]) => {
      const existing =
        existingDefinitions.get(id) ||
        previousDefinitions.find(
          (definition) => definition.key === param.name && definition.type === param.type,
        );

      let defaultValue: FilterValue | undefined = existing?.defaultValue;
      if (defaultValue === undefined && param.value !== undefined && param.value !== null) {
        defaultValue =
          param.type === 'timeRange' && typeof param.value === 'number'
            ? buildRelativeTimeRangeFilterValue(param.value)
            : (param.value as FilterValue);
      }
      if (defaultValue === undefined) {
        defaultValue = null;
      }
      if (param.type === 'dateRange') {
        defaultValue = validateDateRangeValue(defaultValue).valid && defaultValue !== null
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
      };
    })
    .sort((left, right) => {
      const orderDiff = (left.order ?? 0) - (right.order ?? 0);
      if (orderDiff !== 0) return orderDiff;
      return left.id.localeCompare(right.id);
    });
};

export const syncReportFiltersFromSections = (
  viewSets: ReportViewSets,
  dataSources: DatasourceItem[],
): ReportViewSets => {
  const filters = buildFiltersFromReportSections(
    viewSets.sections,
    viewSets.filters,
    dataSources,
  );
  const allowedIds = new Set(filters.map((definition) => definition.id));
  const sections = viewSets.sections.map((section) => {
    const dataSource = resolveSectionDataSource(section.valueConfig.dataSource, dataSources);
    const params = resolveSectionBindableParams(section.valueConfig, dataSource);
    const nextBindings = Object.entries(
      buildDefaultFilterBindings(params, filters, section.valueConfig.filterBindings) || {},
    ).reduce<FilterBindings>((bindings, [filterId, enabled]) => {
      if (allowedIds.has(filterId)) {
        bindings[filterId] = enabled;
      }
      return bindings;
    }, {});
    const filterBindings = Object.keys(nextBindings).length ? nextBindings : undefined;
    if (
      JSON.stringify(section.valueConfig.filterBindings ?? {}) ===
      JSON.stringify(filterBindings ?? {})
    ) {
      return section;
    }
    return {
      ...section,
      valueConfig: {
        ...section.valueConfig,
        filterBindings,
      },
    };
  });

  return {
    ...viewSets,
    filters,
    sections,
  };
};
