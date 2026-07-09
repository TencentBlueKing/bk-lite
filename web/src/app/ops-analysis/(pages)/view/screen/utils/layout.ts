import { v4 as uuidv4 } from "uuid";
import type {
  FilterBindings,
  ScreenWidgetAppearance,
  UnifiedFilterDefinition,
  WidgetConfig,
} from "@/app/ops-analysis/types/dashBoard";
import type {
  DatasourceItem,
  ParamItem,
} from "@/app/ops-analysis/types/dataSource";
import type {
  ScreenItem,
  ScreenViewSets,
  ScreenViewportConfig,
  ScreenWidgetChartType,
  ScreenWidgetItem,
} from "@/app/ops-analysis/types/screen";
import { buildRelativeTimeRangeFilterValue } from "@/app/ops-analysis/utils/filterValue";
import {
  buildDefaultFilterBindings,
  getBindableFilterParams,
  getFilterDefinitionId,
} from "@/app/ops-analysis/utils/widgetDataTransform";
import { getScreenWidgetDefinition } from "../constants/widgets";

const DEFAULT_INSERT_X = 48;
const DEFAULT_INSERT_Y = 96;

const clamp = (value: number, min: number, max: number) =>
  Math.min(Math.max(value, min), max);

const getNextZIndex = (items: ScreenItem[]) =>
  items.reduce((max, item) => Math.max(max, item.zIndex || 0), 0) + 1;

export const normalizeScreenWidgetAppearance = (
  appearance?: ScreenWidgetAppearance,
): Required<ScreenWidgetAppearance> => ({
  frame: appearance?.frame === "bare" ? "bare" : "panel",
});

export const getDefaultScreenWidgetAppearance = (
  chartType?: ScreenWidgetChartType | string,
): Required<ScreenWidgetAppearance> => ({
  frame: chartType === "room3D" ? "bare" : "panel",
});

export const isScreenItemInsideViewport = (
  item: ScreenItem,
  viewport: ScreenViewportConfig,
) =>
  Number.isFinite(item.x) &&
  Number.isFinite(item.y) &&
  Number.isFinite(item.w) &&
  Number.isFinite(item.h) &&
  item.x >= 0 &&
  item.y >= 0 &&
  item.w > 0 &&
  item.h > 0 &&
  item.x + item.w <= viewport.width &&
  item.y + item.h <= viewport.height;

export const canViewportContainItems = (
  items: ScreenItem[],
  viewport: ScreenViewportConfig,
) => items.every((item) => isScreenItemInsideViewport(item, viewport));

const resolveScreenWidgetParams = (
  item: ScreenWidgetItem,
  dataSource?: DatasourceItem,
) => {
  const widgetParams = item.valueConfig?.dataSourceParams;
  return Array.isArray(widgetParams) && widgetParams.length > 0
    ? widgetParams
    : dataSource?.params;
};

const resolveScreenItemDataSource = (
  item: ScreenWidgetItem,
  dataSources: DatasourceItem[],
) => {
  const dataSourceId = item.valueConfig?.dataSource;
  const normalizedId =
    typeof dataSourceId === "string" ? parseInt(dataSourceId, 10) : dataSourceId;
  return dataSources.find((source) => source.id === normalizedId);
};

export const buildFiltersFromScreenItems = ({
  viewSets,
  previousDefinitions,
  dataSources,
}: {
  viewSets: ScreenViewSets;
  previousDefinitions: UnifiedFilterDefinition[];
  dataSources: DatasourceItem[];
}): UnifiedFilterDefinition[] => {
  const discoveredParams = new Map<
    string,
    ParamItem & { type: "string" | "timeRange" }
  >();

  viewSets.items.forEach((item) => {
    const dataSource = resolveScreenItemDataSource(item, dataSources);
    const params = resolveScreenWidgetParams(item, dataSource);
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
          (definition) =>
            definition.key === param.name && definition.type === param.type,
        );

      let defaultValue: UnifiedFilterDefinition["defaultValue"] = null;
      if (existing?.defaultValue !== undefined) {
        defaultValue = existing.defaultValue;
      } else if (param.value !== undefined && param.value !== null) {
        defaultValue =
          param.type === "timeRange" && typeof param.value === "number"
            ? buildRelativeTimeRangeFilterValue(param.value)
            : (param.value as UnifiedFilterDefinition["defaultValue"]);
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
    .sort((a, b) => {
      const orderDiff = (a.order ?? 0) - (b.order ?? 0);
      if (orderDiff !== 0) return orderDiff;
      return a.id.localeCompare(b.id);
    });
};

const cleanupScreenFilterBindings = (
  bindings: FilterBindings | undefined,
  params: ParamItem[] | undefined,
  definitions: UnifiedFilterDefinition[],
) => {
  if (!bindings) return undefined;
  const bindableParams = getBindableFilterParams(params);
  const validIds = new Set(
    definitions
      .filter((definition) =>
        bindableParams.some(
          (param) =>
            param.name === definition.key && param.type === definition.type,
        ),
      )
      .map((definition) => definition.id),
  );
  const cleaned = Object.entries(bindings).reduce<FilterBindings>(
    (acc, [filterId, enabled]) => {
      if (validIds.has(filterId)) {
        acc[filterId] = enabled;
      }
      return acc;
    },
    {},
  );
  return Object.keys(cleaned).length ? cleaned : undefined;
};

export const syncScreenFilterBindings = (
  viewSets: ScreenViewSets,
  definitions: UnifiedFilterDefinition[],
  dataSources: DatasourceItem[],
): ScreenViewSets => ({
  ...viewSets,
  filters: definitions,
  items: viewSets.items.map((item) => {
    const dataSource = resolveScreenItemDataSource(item, dataSources);
    const params = resolveScreenWidgetParams(item, dataSource);
    const nextBindings = cleanupScreenFilterBindings(
      buildDefaultFilterBindings(
        params,
        definitions,
        item.valueConfig?.filterBindings,
      ),
      params,
      definitions,
    );

    if (
      JSON.stringify(nextBindings ?? {}) ===
      JSON.stringify(item.valueConfig?.filterBindings ?? {})
    ) {
      return item;
    }

    return {
      ...item,
      valueConfig: {
        ...item.valueConfig,
        filterBindings: nextBindings,
      },
    };
  }),
});

export const createScreenWidgetItem = (
  chartType: ScreenWidgetChartType,
  existingItems: ScreenItem[],
): ScreenWidgetItem => {
  const definition = getScreenWidgetDefinition(chartType);
  if (!definition) {
    throw new Error(`Unsupported screen widget type: ${chartType}`);
  }

  return {
    id: uuidv4(),
    type: "widget",
    chartType,
    title: "",
    x: DEFAULT_INSERT_X,
    y: DEFAULT_INSERT_Y,
    w: definition.defaultWidth,
    h: definition.defaultHeight,
    zIndex: getNextZIndex(existingItems),
    valueConfig: {
      chartType,
      chartThemeMode: "screen-dark",
      appearance: getDefaultScreenWidgetAppearance(chartType),
      ...(chartType === "networkStatusTopology"
        ? { sceneWidgetType: "networkStatusTopology" as const }
        : {}),
    },
  };
};

export const isScreenWidgetChartType = (
  chartType?: string,
): chartType is ScreenWidgetChartType =>
  Boolean(
    chartType && getScreenWidgetDefinition(chartType as ScreenWidgetChartType),
  );

export const addConfiguredScreenWidget = (
  viewSets: ScreenViewSets,
  values: WidgetConfig,
): ScreenViewSets => {
  const chartType =
    values.sceneWidgetType === "networkStatusTopology"
      ? "networkStatusTopology"
      : values.chartType;

  if (!isScreenWidgetChartType(chartType)) {
    throw new Error(`Unsupported screen widget type: ${chartType || "empty"}`);
  }

  const item = createScreenWidgetItem(chartType, viewSets.items);
  return {
    ...viewSets,
    items: [
      ...viewSets.items,
      {
        ...item,
        title: values.name || item.title,
        valueConfig: {
          ...item.valueConfig,
          ...values,
          chartType,
          chartThemeMode: "screen-dark",
          appearance:
            values.appearance || getDefaultScreenWidgetAppearance(chartType),
          ...(chartType === "networkStatusTopology"
            ? { sceneWidgetType: "networkStatusTopology" as const }
            : {}),
        },
      },
    ],
  };
};

export const moveScreenItem = (
  viewSets: ScreenViewSets,
  itemId: string,
  position: { x: number; y: number },
): ScreenViewSets => ({
  ...viewSets,
  items: viewSets.items.map((item) =>
    item.id === itemId
      ? {
        ...item,
        x: clamp(position.x, 0, viewSets.viewport.width - item.w),
        y: clamp(position.y, 0, viewSets.viewport.height - item.h),
      }
      : item,
  ),
});

export const resizeScreenItem = (
  viewSets: ScreenViewSets,
  itemId: string,
  size: { w: number; h: number },
): ScreenViewSets => ({
  ...viewSets,
  items: viewSets.items.map((item) =>
    item.id === itemId
      ? {
        ...item,
        w: clamp(size.w, 1, viewSets.viewport.width - item.x),
        h: clamp(size.h, 1, viewSets.viewport.height - item.y),
      }
      : item,
  ),
});

export const updateScreenItemConfig = (
  viewSets: ScreenViewSets,
  itemId: string,
  nextItem: ScreenItem,
): ScreenViewSets => ({
  ...viewSets,
  items: viewSets.items.map((item) => (item.id === itemId ? nextItem : item)),
});

export const deleteScreenItem = (
  viewSets: ScreenViewSets,
  itemId: string,
): ScreenViewSets => ({
  ...viewSets,
  items: viewSets.items.filter((item) => item.id !== itemId),
});
