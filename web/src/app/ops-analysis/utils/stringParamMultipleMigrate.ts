import type {
  FilterBindings,
  FilterValue,
  UnifiedFilterDefinition,
} from '@/app/ops-analysis/types/dashBoard';
import type {
  InputControlConfig,
  InputOption,
  ParamItem,
} from '@/app/ops-analysis/types/dataSource';
import { normalizeInputConfig } from '@/app/ops-analysis/utils/paramInputConfigUtils';

export const LEGACY_STRING_LIST_TYPE = 'stringList';

export interface StringParamMigrationWarning {
  code:
    | 'string_list_component_switch_conflict'
    | 'string_list_dual_id_incompatible';
  key?: string;
  message: string;
  fields?: string[];
}

/** 读路径可识别旧 stringList；规范化后写回正式 UnifiedFilterDefinition。 */
export type LegacyUnifiedFilterDefinition = Omit<UnifiedFilterDefinition, 'type'> & {
  type: UnifiedFilterDefinition['type'] | typeof LEGACY_STRING_LIST_TYPE | string;
};

const DEFAULT_MULTIPLE_SELECT_CONFIG = {
  control: 'select' as const,
  multiple: true,
  optionsSource: {
    type: 'static' as const,
    staticItems: [] as InputOption[],
  },
} satisfies InputControlConfig;

const cloneJson = <T,>(value: T): T => {
  if (value === null || typeof value !== 'object') {
    return value;
  }
  return JSON.parse(JSON.stringify(value)) as T;
};

const stableSerialize = (value: unknown): string => {
  if (value === null || typeof value !== 'object') {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map((item) => stableSerialize(item)).join(',')}]`;
  }
  const record = value as Record<string, unknown>;
  const keys = Object.keys(record).sort();
  return `{${keys
    .map((key) => `${JSON.stringify(key)}:${stableSerialize(record[key])}`)
    .join(',')}}`;
};

const optionsSourceIdentity = (
  optionsSource: Extract<InputControlConfig, { control: 'select' | 'radio' }>['optionsSource'],
): string => {
  if (optionsSource.type === 'static') {
    const values = (optionsSource.staticItems || [])
      .map((item) => String(item.value))
      .sort();
    return stableSerialize({ type: 'static', values });
  }
  return stableSerialize(optionsSource);
};

export const areNormalizedInputConfigsCompatible = (
  left?: InputControlConfig,
  right?: InputControlConfig,
): boolean => {
  if (!left && !right) return true;
  if (!left || !right) return false;
  if (left.control !== right.control) return false;
  if (left.control === 'input' || right.control === 'input') {
    return left.control === right.control;
  }
  const leftPicker = left.picker ?? 'dropdown';
  const rightPicker = right.picker ?? 'dropdown';
  if (leftPicker !== rightPicker) return false;
  return optionsSourceIdentity(left.optionsSource) === optionsSourceIdentity(right.optionsSource);
};

export const normalizeStringListInputConfig = (
  entity?: { inputConfig?: InputControlConfig; options?: InputOption[] } | null,
): { inputConfig: InputControlConfig; warnings: StringParamMigrationWarning[] } => {
  const warnings: StringParamMigrationWarning[] = [];
  const normalized = normalizeInputConfig(entity);

  if (!normalized) {
    return { inputConfig: cloneJson(DEFAULT_MULTIPLE_SELECT_CONFIG), warnings };
  }

  if (normalized.control === 'input') {
    return { inputConfig: { control: 'input' }, warnings };
  }

  const next: Extract<InputControlConfig, { control: 'select' | 'radio' }> = {
    control: normalized.control,
    optionsSource: cloneJson(normalized.optionsSource),
    multiple: true,
    ...(normalized.maxCount !== undefined ? { maxCount: normalized.maxCount } : {}),
    ...(normalized.picker ? { picker: normalized.picker } : {}),
  };

  if (normalized.componentSwitch) {
    warnings.push({
      code: 'string_list_component_switch_conflict',
      message:
        '旧 stringList 与 componentSwitch 互斥；已保留列表传参（multiple: true）并关闭 componentSwitch',
    });
  }

  return { inputConfig: next, warnings };
};

export const stringFilterDefinitionId = (key: string): string => `${key}__string`;

export const migrateParamItemFromStringList = (
  param: ParamItem,
): { param: ParamItem; warnings: StringParamMigrationWarning[] } => {
  if (param.type !== LEGACY_STRING_LIST_TYPE) {
    return { param, warnings: [] };
  }

  const { inputConfig, warnings } = normalizeStringListInputConfig(param);
  return {
    param: {
      ...param,
      type: 'string',
      inputConfig,
      options: undefined,
    },
    warnings: warnings.map((item) => ({ ...item, key: param.name })),
  };
};

export const migrateParamItemsFromStringList = (
  params: ParamItem[] | undefined | null,
): { params: ParamItem[]; warnings: StringParamMigrationWarning[] } => {
  if (!Array.isArray(params)) {
    return { params: [], warnings: [] };
  }

  const warnings: StringParamMigrationWarning[] = [];
  const next = params.map((param) => {
    const migrated = migrateParamItemFromStringList(param);
    warnings.push(...migrated.warnings);
    return migrated.param;
  });
  return { params: next, warnings };
};

export const normalizeDatasourceItemParams = <
  T extends { params?: ParamItem[] | null },
>(item: T): T => {
  if (!item || !Array.isArray(item.params)) {
    return item;
  }
  const { params } = migrateParamItemsFromStringList(item.params);
  return {
    ...item,
    params,
  };
};

export const normalizeDatasourceItemsParams = <
  T extends { params?: ParamItem[] | null },
>(items: T[]): T[] => items.map((item) => normalizeDatasourceItemParams(item));

const migrateSingleFilterDefinition = (
  definition: LegacyUnifiedFilterDefinition,
): {
  definition: UnifiedFilterDefinition;
  warnings: StringParamMigrationWarning[];
} => {
  if (definition.type !== LEGACY_STRING_LIST_TYPE) {
    return {
      definition: definition as UnifiedFilterDefinition,
      warnings: [],
    };
  }

  const { inputConfig, warnings } = normalizeStringListInputConfig(definition);
  return {
    definition: {
      ...(definition as UnifiedFilterDefinition),
      id: stringFilterDefinitionId(definition.key),
      type: 'string',
      inputConfig,
      options: undefined,
    },
    warnings: warnings.map((item) => ({ ...item, key: definition.key })),
  };
};

export const migrateFilterBindings = (
  bindings?: FilterBindings | null,
): FilterBindings => {
  if (!bindings || typeof bindings !== 'object') {
    return {};
  }

  const next: FilterBindings = {};
  Object.entries(bindings).forEach(([filterId, enabled]) => {
    const stringListSuffix = `__${LEGACY_STRING_LIST_TYPE}`;
    const targetId = filterId.endsWith(stringListSuffix)
      ? `${filterId.slice(0, -stringListSuffix.length)}__string`
      : filterId;

    if (Object.prototype.hasOwnProperty.call(next, targetId)) {
      next[targetId] = Boolean(next[targetId] || enabled);
    } else {
      next[targetId] = Boolean(enabled);
    }
  });
  return next;
};

export const migrateUnifiedFilterDefinitions = (
  definitions: LegacyUnifiedFilterDefinition[],
  values: Record<string, FilterValue> = {},
): {
  definitions: UnifiedFilterDefinition[];
  values: Record<string, FilterValue>;
  warnings: StringParamMigrationWarning[];
} => {
  const warnings: StringParamMigrationWarning[] = [];
  const migratedSingles = definitions.map((definition) => {
    const migrated = migrateSingleFilterDefinition(definition);
    warnings.push(...migrated.warnings);
    return migrated.definition;
  });

  const byKey = new Map<string, UnifiedFilterDefinition[]>();
  migratedSingles.forEach((definition) => {
    const group = byKey.get(definition.key) || [];
    group.push(definition);
    byKey.set(definition.key, group);
  });

  const nextDefinitions: UnifiedFilterDefinition[] = [];
  const nextValues: Record<string, FilterValue> = { ...values };

  const takeValue = (
    preferredId: string,
    fallbackId?: string,
  ): FilterValue | undefined => {
    if (Object.prototype.hasOwnProperty.call(values, preferredId)) {
      return values[preferredId];
    }
    if (fallbackId && Object.prototype.hasOwnProperty.call(values, fallbackId)) {
      return values[fallbackId];
    }
    return undefined;
  };

  Array.from(byKey.entries()).forEach(([key, group]) => {
    const stringId = stringFilterDefinitionId(key);
    const legacyId = `${key}__${LEGACY_STRING_LIST_TYPE}`;
    const listOrigin = definitions.find(
      (item) => item.key === key && item.type === LEGACY_STRING_LIST_TYPE,
    );
    const stringOrigin = definitions.find(
      (item) => item.key === key && item.type === 'string' && item.id === stringId,
    );

    if (listOrigin && stringOrigin) {
      const listMigrated = migrateSingleFilterDefinition(listOrigin).definition;
      const stringMigrated = stringOrigin as UnifiedFilterDefinition;
      if (!areNormalizedInputConfigsCompatible(
        listMigrated.inputConfig,
        stringMigrated.inputConfig,
      )) {
        warnings.push({
          code: 'string_list_dual_id_incompatible',
          key,
          message: `筛选项 ${key} 同时存在 string 与 stringList，配置不兼容；已以 stringList 侧为准合并为 ${stringId}`,
          fields: ['control', 'picker', 'optionsSource'],
        });
      }

      nextDefinitions.push({
        ...listMigrated,
        id: stringId,
        type: 'string',
        order: Math.min(listMigrated.order ?? 0, stringMigrated.order ?? 0),
        enabled: Boolean(listMigrated.enabled || stringMigrated.enabled),
      });

      const preferredValue = takeValue(legacyId, stringId);
      delete nextValues[legacyId];
      delete nextValues[stringId];
      if (preferredValue !== undefined) {
        nextValues[stringId] = preferredValue;
      }
      return;
    }

    const [only] = group;
    nextDefinitions.push(only);
    if (listOrigin) {
      const preferredValue = takeValue(legacyId, stringId);
      delete nextValues[legacyId];
      if (preferredValue !== undefined) {
        nextValues[stringId] = preferredValue;
      }
    }
  });

  nextDefinitions.sort((left, right) => {
    const orderDiff = (left.order ?? 0) - (right.order ?? 0);
    if (orderDiff !== 0) return orderDiff;
    return left.id.localeCompare(right.id);
  });

  Object.keys(nextValues).forEach((filterId) => {
    if (filterId.endsWith(`__${LEGACY_STRING_LIST_TYPE}`)) {
      delete nextValues[filterId];
    }
  });

  return { definitions: nextDefinitions, values: nextValues, warnings };
};

export const coerceValueForMultiple = (
  value: FilterValue | undefined | null,
  multiple: boolean,
): FilterValue | null => {
  if (multiple) {
    if (Array.isArray(value)) return value;
    if (typeof value === 'string' || typeof value === 'number') {
      return [value];
    }
    return value ?? null;
  }
  if (Array.isArray(value)) {
    return value[0] ?? null;
  }
  return value ?? null;
};

export const isMultipleSelectInputConfig = (
  inputConfig?: InputControlConfig | null,
): boolean =>
  Boolean(
    inputConfig
    && inputConfig.control !== 'input'
    && inputConfig.multiple,
  );

/** 按筛选项当前 multiple 规范化运行时/默认值形状；不改变非 string 筛选项。 */
export const coerceFilterValuesForDefinitions = (
  definitions: UnifiedFilterDefinition[],
  values: Record<string, FilterValue>,
): Record<string, FilterValue> => {
  const next: Record<string, FilterValue> = { ...values };
  definitions.forEach((definition) => {
    if (definition.type !== 'string') return;
    if (!Object.prototype.hasOwnProperty.call(next, definition.id)) return;
    next[definition.id] = coerceValueForMultiple(
      next[definition.id],
      isMultipleSelectInputConfig(definition.inputConfig),
    );
  });
  return next;
};

/** 请求边界：按消费者 multiple 规范化；空值返回 null 供调用方省略。 */
export const coerceRequestValueForMultiple = (
  value: unknown,
  multiple: boolean,
): unknown | null => {
  if (value === null || value === undefined || value === '') {
    return null;
  }
  if (Array.isArray(value) && value.length === 0) {
    return null;
  }
  const coerced = coerceValueForMultiple(
    value as FilterValue,
    multiple,
  );
  if (coerced === null || coerced === undefined || coerced === '') {
    return null;
  }
  if (Array.isArray(coerced) && coerced.length === 0) {
    return null;
  }
  return coerced;
};

export const logStringParamMigrationWarnings = (
  warnings: StringParamMigrationWarning[],
  context?: { canvasId?: string | number },
): void => {
  if (!warnings.length) return;
  warnings.forEach((warning) => {
    console.warn('[ops-analysis][string-param-multiple]', {
      ...warning,
      canvasId: context?.canvasId,
    });
  });
};
