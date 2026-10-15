import type {
  FilterBindings,
  FilterValue,
  UnifiedFilterDefinition,
} from '@/app/ops-analysis/types/dashBoard';
import type { InputOption, InputControlConfig } from '@/app/ops-analysis/types/dataSource';
import {
  APPLICATION_TOPOLOGY_DEFAULT_DEPTH,
  APPLICATION_TOPOLOGY_MAX_DEPTH,
} from '@/app/ops-analysis/types/sceneWidget';
import {
  ROOM_FILTER_PASSTHROUGH,
  resolveRoomFilterAppliedValue,
} from '@/app/ops-analysis/utils/room3DScreenFilter';

export const APPLICATION_TOPOLOGY_FILTER_KEY = 'application_system_id';
export const APPLICATION_TOPOLOGY_FILTER_ID = 'application_system_id__string';
export const APPLICATION_TOPOLOGY_FILTER_NAME = 'Application System';
export const APPLICATION_TOPOLOGY_SYSTEM_LIST_REST_API = 'cmdb/list_application_systems';
export const APPLICATION_TOPOLOGY_DEPTH_FILTER_KEY = 'application_topology_depth';
export const APPLICATION_TOPOLOGY_DEPTH_FILTER_ID = 'application_topology_depth__string';
export const APPLICATION_TOPOLOGY_DEPTH_FILTER_NAME = 'Expand depth';

/** 代码常量和已经写进画布的默认显示名。自定义名称不在这里，加载时不会被改掉。 */
const SHIPPED_SYSTEM_FILTER_NAMES = new Set([
  APPLICATION_TOPOLOGY_FILTER_NAME,
  '应用系统',
]);
const SHIPPED_DEPTH_FILTER_NAMES = new Set([
  APPLICATION_TOPOLOGY_DEPTH_FILTER_NAME,
  '展开层级',
]);

export const APPLICATION_TOPOLOGY_FILTER_INPUT_CONFIG: InputControlConfig = {
  control: 'select',
  optionsSource: {
    type: 'dynamic',
    sourceRef: { type: 'rest_api', value: APPLICATION_TOPOLOGY_SYSTEM_LIST_REST_API },
    valueField: 'inst_uuid',
    labelField: 'inst_name',
  },
};

export const APPLICATION_TOPOLOGY_DEPTH_FILTER_INPUT_CONFIG: InputControlConfig = {
  control: 'select',
  optionsSource: {
    type: 'static',
    staticItems: Array.from({ length: APPLICATION_TOPOLOGY_MAX_DEPTH }, (_, index) => {
      const depth = String(index + 1);
      return { label: depth, value: depth };
    }),
  },
};

interface TopologyCarrier {
  id?: string;
  chartType?: string;
  valueConfig?: {
    chartType?: string;
    sceneWidgetType?: string;
    applicationTopology?: { instUuid?: string; depth?: number };
    filterBindings?: FilterBindings;
  } | null;
}

export const isApplicationTopologyCarrier = (item: TopologyCarrier) =>
  item.chartType === 'applicationTopology'
  || item.valueConfig?.chartType === 'applicationTopology'
  || item.valueConfig?.sceneWidgetType === 'applicationTopology';

const isSystemFilterDefinition = (definition: UnifiedFilterDefinition) =>
  definition.id === APPLICATION_TOPOLOGY_FILTER_ID
  || (definition.key === APPLICATION_TOPOLOGY_FILTER_KEY && definition.type === 'string');

const isDepthFilterDefinition = (definition: UnifiedFilterDefinition) =>
  definition.id === APPLICATION_TOPOLOGY_DEPTH_FILTER_ID
  || (definition.key === APPLICATION_TOPOLOGY_DEPTH_FILTER_KEY && definition.type === 'string');

const nextFilterOrder = (definitions: UnifiedFilterDefinition[]) =>
  definitions.reduce(
    (maxOrder, definition) => Math.max(maxOrder, definition.order ?? -1),
    -1,
  ) + 1;

const sortFilters = (definitions: UnifiedFilterDefinition[]) =>
  [...definitions].sort((left, right) => {
    const orderDiff = (left.order ?? 0) - (right.order ?? 0);
    if (orderDiff !== 0) return orderDiff;
    return left.id.localeCompare(right.id);
  });

const legacySystemId = (items: TopologyCarrier[]) => {
  for (const item of items) {
    const instUuid = item.valueConfig?.applicationTopology?.instUuid?.trim();
    if (instUuid) return instUuid;
  }
  return '';
};

const configuredDepthValue = (widgets: TopologyCarrier[]): string => {
  for (const item of widgets) {
    const depth = Number(item.valueConfig?.applicationTopology?.depth);
    if (Number.isInteger(depth) && depth >= 1 && depth <= APPLICATION_TOPOLOGY_MAX_DEPTH) {
      return String(depth);
    }
  }
  return String(APPLICATION_TOPOLOGY_DEFAULT_DEPTH);
};

/**
 * 画布含应用拓扑时补齐应用系统和展开层级两条全局筛选。
 * 已有同 key 定义时原样保留名称、默认值、启用态和输入配置。
 */
export const ensureApplicationTopologyCanvasFilter = (
  discovered: UnifiedFilterDefinition[],
  items: TopologyCarrier[],
  previousDefinitions: UnifiedFilterDefinition[] = discovered,
): UnifiedFilterDefinition[] => {
  const widgets = items.filter(isApplicationTopologyCarrier);
  if (!widgets.length) return discovered;

  const appendMissing = (
    definitions: UnifiedFilterDefinition[],
    matches: (definition: UnifiedFilterDefinition) => boolean,
    create: (current: UnifiedFilterDefinition[]) => UnifiedFilterDefinition,
  ) => {
    if (definitions.some(matches)) return definitions;
    const previous = previousDefinitions.find(matches);
    if (previous && !definitions.some((item) => item.id === previous.id)) {
      return sortFilters([...definitions, previous]);
    }
    return sortFilters([...definitions, create(definitions)]);
  };

  const withSystem = appendMissing(discovered, isSystemFilterDefinition, (current) => ({
    id: APPLICATION_TOPOLOGY_FILTER_ID,
    key: APPLICATION_TOPOLOGY_FILTER_KEY,
    name: APPLICATION_TOPOLOGY_FILTER_NAME,
    type: 'string',
    defaultValue: legacySystemId(widgets) || null,
    order: nextFilterOrder(current),
    enabled: true,
    inputConfig: APPLICATION_TOPOLOGY_FILTER_INPUT_CONFIG,
  }));

  return appendMissing(withSystem, isDepthFilterDefinition, (current) => ({
    id: APPLICATION_TOPOLOGY_DEPTH_FILTER_ID,
    key: APPLICATION_TOPOLOGY_DEPTH_FILTER_KEY,
    name: APPLICATION_TOPOLOGY_DEPTH_FILTER_NAME,
    type: 'string',
    defaultValue: configuredDepthValue(widgets),
    order: nextFilterOrder(current),
    enabled: true,
    inputMode: 'select',
    inputConfig: APPLICATION_TOPOLOGY_DEPTH_FILTER_INPUT_CONFIG,
  }));
};

export const layoutDeclaresApplicationTopology = (items: TopologyCarrier[]) =>
  items.some(isApplicationTopologyCarrier);

export const relabelApplicationTopologyFilters = <T extends { filters?: UnifiedFilterDefinition[] }>(
  viewSets: T,
  labels: { system?: string; depth?: string },
): T => {
  if (!viewSets.filters?.length) return viewSets;
  let changed = false;
  const filters = viewSets.filters.map((definition) => {
    const nextName = definition.id === APPLICATION_TOPOLOGY_FILTER_ID
      && labels.system
      && SHIPPED_SYSTEM_FILTER_NAMES.has(definition.name)
      ? labels.system
      : definition.id === APPLICATION_TOPOLOGY_DEPTH_FILTER_ID
        && labels.depth
        && SHIPPED_DEPTH_FILTER_NAMES.has(definition.name)
        ? labels.depth
        : undefined;
    if (!nextName || nextName === definition.name) return definition;
    changed = true;
    return { ...definition, name: nextName };
  });
  return changed ? { ...viewSets, filters } : viewSets;
};

export const includeApplicationTopologyCanvasFilter = (
  discovered: UnifiedFilterDefinition[],
  hasWidget: boolean,
  previousDefinitions: UnifiedFilterDefinition[] = [],
  labels: { system?: string; depth?: string } = {},
): UnifiedFilterDefinition[] => {
  if (!hasWidget) return discovered;
  const withFilters = ensureApplicationTopologyCanvasFilter(
    discovered,
    [{ chartType: 'applicationTopology', valueConfig: { chartType: 'applicationTopology' } }],
    previousDefinitions,
  );
  return relabelApplicationTopologyFilters({ filters: withFilters }, labels).filters ?? withFilters;
};

const filterEnabled = (
  definitions: UnifiedFilterDefinition[],
  matches: (definition: UnifiedFilterDefinition) => boolean,
) => definitions.some((definition) => matches(definition) && definition.enabled !== false);

export const withApplicationTopologyFilterBinding = (
  chartType: string | undefined,
  sceneType: string | undefined,
  bindings: FilterBindings | undefined,
  definitions: UnifiedFilterDefinition[],
): FilterBindings | undefined => {
  if (!isApplicationTopologyCarrier({ chartType, valueConfig: { chartType, sceneWidgetType: sceneType } })) {
    return bindings;
  }
  const next: FilterBindings = { ...(bindings || {}) };
  let changed = false;
  const ensure = (enabled: boolean, filterId: string) => {
    if (!enabled || next[filterId] === true) return;
    next[filterId] = true;
    changed = true;
  };
  ensure(filterEnabled(definitions, isSystemFilterDefinition), APPLICATION_TOPOLOGY_FILTER_ID);
  ensure(filterEnabled(definitions, isDepthFilterDefinition), APPLICATION_TOPOLOGY_DEPTH_FILTER_ID);
  if (!changed) return bindings;
  return next;
};

const normalizeFilterSystemId = (value: unknown): string => {
  if (typeof value !== 'string') return '';
  return value.trim();
};

const systemOptionValues = (options: Array<Pick<InputOption, 'value'>>) =>
  options
    .map((option) => option.value)
    .filter((value): value is string | number => typeof value === 'string' || typeof value === 'number');

export const resolveApplicationSystemFilterAppliedValue = (
  definition: Pick<UnifiedFilterDefinition, 'id' | 'key' | 'type' | 'defaultValue' | 'enabled'>,
  current: FilterValue | null | undefined,
  options: Array<Pick<InputOption, 'value'>>,
): FilterValue | undefined | typeof ROOM_FILTER_PASSTHROUGH => {
  const isSystemFilter = definition.id === APPLICATION_TOPOLOGY_FILTER_ID
    || (definition.key === APPLICATION_TOPOLOGY_FILTER_KEY && definition.type === 'string');
  if (!isSystemFilter || definition.enabled === false) {
    return ROOM_FILTER_PASSTHROUGH;
  }
  const defaultId = normalizeFilterSystemId(definition.defaultValue);
  const currentId = normalizeFilterSystemId(current);
  if (currentId) return undefined;
  if (defaultId) {
    return (current ?? null) === defaultId ? undefined : defaultId;
  }
  if (!options.length) return undefined;
  const first = systemOptionValues(options)[0];
  if (first === undefined || (current ?? null) === first) return undefined;
  return first;
};

/** 机房筛选和应用系统筛选都在选项到达时补上默认值，其它筛选项交给通用校正。 */
export const resolveBuiltinCanvasFilterAppliedValue = (
  definition: Pick<UnifiedFilterDefinition, 'id' | 'key' | 'type' | 'defaultValue' | 'enabled'>,
  current: FilterValue | null | undefined,
  options: Array<Pick<InputOption, 'value'>>,
): FilterValue | undefined | typeof ROOM_FILTER_PASSTHROUGH => {
  const roomValue = resolveRoomFilterAppliedValue(definition, current, options);
  if (roomValue !== ROOM_FILTER_PASSTHROUGH) return roomValue;
  return resolveApplicationSystemFilterAppliedValue(definition, current, options);
};

/** 应用拓扑读画布筛选。运行时已选值优先，否则用筛选项默认值。 */
export const resolveApplicationTopologyCanvasSelection = ({
  filterDefinitions,
  unifiedFilterValues,
  fallbackInstUuid = '',
}: {
  filterDefinitions?: UnifiedFilterDefinition[];
  unifiedFilterValues?: Record<string, unknown>;
  fallbackInstUuid?: string;
}): string => {
  const definition = filterDefinitions?.find((item) => item.id === APPLICATION_TOPOLOGY_FILTER_ID);
  if (definition?.enabled === false) {
    return fallbackInstUuid.trim();
  }
  const runtime = normalizeFilterSystemId(unifiedFilterValues?.[APPLICATION_TOPOLOGY_FILTER_ID]);
  if (runtime) return runtime;
  const saved = normalizeFilterSystemId(definition?.defaultValue);
  if (saved) return saved;
  return fallbackInstUuid.trim();
};

const parseTopologyDepth = (value: unknown): number | null => {
  if (value == null || value === '') return null;
  const depth = Number(value);
  if (!Number.isInteger(depth) || depth < 1 || depth > APPLICATION_TOPOLOGY_MAX_DEPTH) {
    return null;
  }
  return depth;
};

/** 展开层级读已生效的全局筛选。未选时用筛选项默认值，再回退组件配置。 */
export const resolveApplicationTopologyDepth = ({
  filterDefinitions,
  unifiedFilterValues,
  fallbackDepth,
}: {
  filterDefinitions?: UnifiedFilterDefinition[];
  unifiedFilterValues?: Record<string, unknown>;
  fallbackDepth?: unknown;
}): number => {
  const definition = filterDefinitions?.find(isDepthFilterDefinition);
  const fallback = parseTopologyDepth(fallbackDepth) ?? APPLICATION_TOPOLOGY_DEFAULT_DEPTH;
  if (definition?.enabled === false) return fallback;
  const runtime = parseTopologyDepth(unifiedFilterValues?.[APPLICATION_TOPOLOGY_DEPTH_FILTER_ID]);
  if (runtime != null) return runtime;
  const saved = parseTopologyDepth(definition?.defaultValue);
  if (saved != null) return saved;
  return fallback;
};
