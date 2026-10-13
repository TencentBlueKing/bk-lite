import type {
  FilterBindings,
  FilterValue,
  UnifiedFilterDefinition,
} from '@/app/ops-analysis/types/dashBoard';
import type { InputOption } from '@/app/ops-analysis/types/dataSource';
import type { InputControlConfig } from '@/app/ops-analysis/types/dataSource';
import type { ScreenItem, ScreenWidgetItem } from '@/app/ops-analysis/types/screen';
import { isScreenWidgetItem } from '@/app/ops-analysis/(pages)/view/screen/utils/screenItems';
import { readPersistedServerRoomId } from '@/app/ops-analysis/utils/room3DConfig';

export const ROOM3D_FILTER_KEY = 'server_room_id';
export const ROOM3D_FILTER_ID = 'server_room_id__string';
export const ROOM3D_FILTER_NAME = 'Room';
export const ROOM3D_ROOM_LIST_REST_API = 'cmdb/get_room_list';

export const ROOM3D_FILTER_INPUT_CONFIG: InputControlConfig = {
  control: 'select',
  optionsSource: {
    type: 'dynamic',
    sourceRef: { type: 'rest_api', value: ROOM3D_ROOM_LIST_REST_API },
    valueField: 'inst_uuid',
    labelField: 'inst_name',
  },
};

export const isRoom3DScreenItem = (
  item: ScreenItem,
): item is ScreenWidgetItem => {
  if (!isScreenWidgetItem(item)) return false;
  return (
    item.chartType === 'room3D' ||
    item.valueConfig?.chartType === 'room3D' ||
    item.valueConfig?.sceneWidgetType === 'room3D'
  );
};

const isRoomFilterDefinition = (definition: UnifiedFilterDefinition) =>
  definition.id === ROOM3D_FILTER_ID ||
  (definition.key === ROOM3D_FILTER_KEY && definition.type === 'string');

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

/**
 * 大屏含 room3D 且还没有机房筛选项时补一条。
 * 已有同 key 定义时原样保留名称、默认值、启用态和输入配置。
 */
export const ensureRoom3DCanvasFilter = (
  discovered: UnifiedFilterDefinition[],
  items: ScreenItem[],
  previousDefinitions: UnifiedFilterDefinition[] = discovered,
): UnifiedFilterDefinition[] => {
  const roomWidgets = items.filter(isRoom3DScreenItem);
  if (!roomWidgets.length) return discovered;
  if (discovered.some(isRoomFilterDefinition)) return discovered;

  const previous = previousDefinitions.find(isRoomFilterDefinition);
  if (previous) {
    return sortFilters([...discovered, previous]);
  }

  const legacyRoomId = readPersistedServerRoomId(roomWidgets[0]?.valueConfig);
  return sortFilters([
    ...discovered,
    {
      id: ROOM3D_FILTER_ID,
      key: ROOM3D_FILTER_KEY,
      name: ROOM3D_FILTER_NAME,
      type: 'string',
      defaultValue: legacyRoomId || null,
      order: nextFilterOrder(discovered),
      enabled: true,
      inputConfig: ROOM3D_FILTER_INPUT_CONFIG,
    },
  ]);
};

export const layoutDeclaresRoom3D = (
  items: Array<{ valueConfig?: { chartType?: string; sceneWidgetType?: string } | null }>,
) =>
  items.some(
    (item) =>
      item.valueConfig?.chartType === 'room3D' ||
      item.valueConfig?.sceneWidgetType === 'room3D',
  );

/** 全局筛选弹窗只扫描数据源参数。room3D 没有参数，这里把机房筛选项补回去。 */
export const includeRoom3DCanvasFilter = (
  discovered: UnifiedFilterDefinition[],
  hasRoom3D: boolean,
  previousDefinitions: UnifiedFilterDefinition[] = [],
  label = ROOM3D_FILTER_NAME,
): UnifiedFilterDefinition[] => {
  if (!hasRoom3D) return discovered;
  const withFilter = ensureRoom3DCanvasFilter(
    discovered,
    [
      {
        type: 'widget',
        chartType: 'room3D',
        valueConfig: { chartType: 'room3D', sceneWidgetType: 'room3D' },
      } as ScreenItem,
    ],
    previousDefinitions,
  );
  return relabelBuiltinRoom3DFilter({ filters: withFilter }, label).filters ?? withFilter;
};

export const relabelBuiltinRoom3DFilter = <T extends { filters?: UnifiedFilterDefinition[] }>(
  viewSets: T,
  label: string,
): T => {
  if (!label || label === ROOM3D_FILTER_NAME || !viewSets.filters?.length) {
    return viewSets;
  }
  let changed = false;
  const filters = viewSets.filters.map((definition) => {
    if (definition.id !== ROOM3D_FILTER_ID || definition.name !== ROOM3D_FILTER_NAME) {
      return definition;
    }
    changed = true;
    return { ...definition, name: label };
  });
  return changed ? { ...viewSets, filters } : viewSets;
};

const roomFilterEnabled = (definitions: UnifiedFilterDefinition[]) =>
  definitions.some((definition) => definition.id === ROOM3D_FILTER_ID);

export const applyRoom3DFilterBindings = (
  items: ScreenItem[],
  definitions: UnifiedFilterDefinition[],
): ScreenItem[] => {
  if (!roomFilterEnabled(definitions)) return items;
  let changed = false;
  const next = items.map((item) => {
    if (!isRoom3DScreenItem(item)) return item;
    const current = item.valueConfig?.filterBindings;
    if (current?.[ROOM3D_FILTER_ID] === true) {
      return item;
    }
    changed = true;
    return {
      ...item,
      valueConfig: {
        ...item.valueConfig,
        filterBindings: {
          ...(current || {}),
          [ROOM3D_FILTER_ID]: true,
        },
      },
    };
  });
  return changed ? next : items;
};

export const mergeRoom3DFilterBinding = (
  item: ScreenItem,
  cleaned: FilterBindings | undefined,
  definitions: UnifiedFilterDefinition[],
): FilterBindings | undefined => {
  if (!isRoom3DScreenItem(item) || !roomFilterEnabled(definitions)) {
    return cleaned;
  }
  return {
    ...(cleaned || {}),
    [ROOM3D_FILTER_ID]: true,
  };
};

const normalizeFilterRoomId = (value: unknown): string => {
  if (typeof value !== 'string') return '';
  return value.trim();
};

/** 非机房筛选项交给通用校正，不在这里选第一项。 */
export const ROOM_FILTER_PASSTHROUGH = Symbol('room-filter-passthrough');

const roomOptionValues = (options: Array<Pick<InputOption, 'value'>>) =>
  options
    .map((option) => option.value)
    .filter((value): value is string | number => typeof value === 'string' || typeof value === 'number');

/**
 * 只处理机房筛选。当前值非空时一律保留，不可见也不改成第一项或默认值。
 * 当前值为空时：有默认机房就用默认值（即使不可见），否则用列表第一项。
 * 返回 undefined 表示当前值不用改。
 */
export const resolveRoomFilterAppliedValue = (
  definition: Pick<UnifiedFilterDefinition, 'id' | 'key' | 'type' | 'defaultValue' | 'enabled'>,
  current: FilterValue | null | undefined,
  options: Array<Pick<InputOption, 'value'>>,
): FilterValue | undefined | typeof ROOM_FILTER_PASSTHROUGH => {
  const isRoomFilter = definition.id === ROOM3D_FILTER_ID
    || (definition.key === ROOM3D_FILTER_KEY && definition.type === 'string');
  if (!isRoomFilter || definition.enabled === false) {
    return ROOM_FILTER_PASSTHROUGH;
  }
  const defaultId = normalizeFilterRoomId(definition.defaultValue);
  const currentId = normalizeFilterRoomId(current);
  if (currentId) return undefined;
  if (defaultId) {
    return (current ?? null) === defaultId ? undefined : defaultId;
  }
  if (!options.length) return undefined;
  const first = roomOptionValues(options)[0];
  if (first === undefined || (current ?? null) === first) return undefined;
  return first;
};

/** room3D 读画布筛选：默认值走定义，已应用值走运行时。历史绑定 false 也视为开启。 */
export const resolveRoom3DCanvasSelection = ({
  filterDefinitions,
  unifiedFilterValues,
}: {
  filterBindings?: FilterBindings;
  filterDefinitions?: UnifiedFilterDefinition[];
  unifiedFilterValues?: Record<string, unknown>;
}): { savedRoomId: string; runtimeRoomId: string } => {
  const definition = filterDefinitions?.find(
    (item) => item.id === ROOM3D_FILTER_ID,
  );
  // 与普通组件一致：全局筛选关闭时不传该参数，交给可见列表第一个机房。
  if (definition?.enabled === false) {
    return { savedRoomId: '', runtimeRoomId: '' };
  }
  const applied = unifiedFilterValues?.[ROOM3D_FILTER_ID];
  return {
    savedRoomId: normalizeFilterRoomId(definition?.defaultValue),
    runtimeRoomId: normalizeFilterRoomId(applied),
  };
};
