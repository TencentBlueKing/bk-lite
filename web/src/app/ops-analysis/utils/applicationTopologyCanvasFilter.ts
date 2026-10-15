import type {
  FilterBindings,
  FilterValue,
  UnifiedFilterDefinition,
} from '@/app/ops-analysis/types/dashBoard';
import type { InputOption, InputControlConfig } from '@/app/ops-analysis/types/dataSource';
import {
  ROOM_FILTER_PASSTHROUGH,
  resolveRoomFilterAppliedValue,
} from '@/app/ops-analysis/utils/room3DScreenFilter';

export const APPLICATION_TOPOLOGY_FILTER_KEY = 'application_system_id';
export const APPLICATION_TOPOLOGY_FILTER_ID = 'application_system_id__string';
export const APPLICATION_TOPOLOGY_FILTER_NAME = 'Application System';
export const APPLICATION_TOPOLOGY_SYSTEM_LIST_REST_API = 'cmdb/list_application_systems';

export const APPLICATION_TOPOLOGY_FILTER_INPUT_CONFIG: InputControlConfig = {
  control: 'select',
  optionsSource: {
    type: 'dynamic',
    sourceRef: { type: 'rest_api', value: APPLICATION_TOPOLOGY_SYSTEM_LIST_REST_API },
    valueField: 'inst_uuid',
    labelField: 'inst_name',
  },
};

interface TopologyCarrier {
  id?: string;
  chartType?: string;
  valueConfig?: {
    chartType?: string;
    sceneWidgetType?: string;
    applicationTopology?: { instUuid?: string };
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

/**
 * 画布含应用拓扑且还没有应用系统筛选项时补一条。
 * 已有同 key 定义时原样保留名称、默认值、启用态和输入配置。
 */
export const ensureApplicationTopologyCanvasFilter = (
  discovered: UnifiedFilterDefinition[],
  items: TopologyCarrier[],
  previousDefinitions: UnifiedFilterDefinition[] = discovered,
): UnifiedFilterDefinition[] => {
  const widgets = items.filter(isApplicationTopologyCarrier);
  if (!widgets.length) return discovered;
  if (discovered.some(isSystemFilterDefinition)) return discovered;

  const previous = previousDefinitions.find(isSystemFilterDefinition);
  if (previous) {
    return sortFilters([...discovered, previous]);
  }

  return sortFilters([
    ...discovered,
    {
      id: APPLICATION_TOPOLOGY_FILTER_ID,
      key: APPLICATION_TOPOLOGY_FILTER_KEY,
      name: APPLICATION_TOPOLOGY_FILTER_NAME,
      type: 'string',
      defaultValue: legacySystemId(widgets) || null,
      order: nextFilterOrder(discovered),
      enabled: true,
      inputConfig: APPLICATION_TOPOLOGY_FILTER_INPUT_CONFIG,
    },
  ]);
};

export const layoutDeclaresApplicationTopology = (items: TopologyCarrier[]) =>
  items.some(isApplicationTopologyCarrier);

export const includeApplicationTopologyCanvasFilter = (
  discovered: UnifiedFilterDefinition[],
  hasWidget: boolean,
  previousDefinitions: UnifiedFilterDefinition[] = [],
): UnifiedFilterDefinition[] => {
  if (!hasWidget) return discovered;
  return ensureApplicationTopologyCanvasFilter(
    discovered,
    [{ chartType: 'applicationTopology', valueConfig: { chartType: 'applicationTopology' } }],
    previousDefinitions,
  );
};

const systemFilterEnabled = (definitions: UnifiedFilterDefinition[]) =>
  definitions.some((definition) => isSystemFilterDefinition(definition) && definition.enabled !== false);

export const withApplicationTopologyFilterBinding = (
  chartType: string | undefined,
  sceneType: string | undefined,
  bindings: FilterBindings | undefined,
  definitions: UnifiedFilterDefinition[],
): FilterBindings | undefined => {
  if (!isApplicationTopologyCarrier({ chartType, valueConfig: { chartType, sceneWidgetType: sceneType } })) {
    return bindings;
  }
  if (!systemFilterEnabled(definitions)) return bindings;
  if (bindings?.[APPLICATION_TOPOLOGY_FILTER_ID] === true) return bindings;
  return {
    ...(bindings || {}),
    [APPLICATION_TOPOLOGY_FILTER_ID]: true,
  };
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
