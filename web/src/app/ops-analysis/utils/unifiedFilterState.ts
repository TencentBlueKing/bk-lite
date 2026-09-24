import type {
  FilterValue,
  TimeRangeValue,
  UnifiedFilterDefinition,
} from '@/app/ops-analysis/types/dashBoard';
import { normalizeTimeRangeFilterValue } from '@/app/ops-analysis/utils/filterValue';
import { validateDateRangeValue } from '@/app/ops-analysis/utils/dateRange';
import type { DateRangeValue } from '@/app/ops-analysis/types/dateRange';
import { isOrganizationControl } from '@/app/ops-analysis/utils/paramInputConfigUtils';
import { isDynamicOptionFilter } from '@/app/ops-analysis/utils/optionBackedFilterValue';
import {
  coerceFilterValuesForDefinitions,
  coerceValueForMultiple,
  isMultipleSelectInputConfig,
  logStringParamMigrationWarnings,
  migrateUnifiedFilterDefinitions,
  type LegacyUnifiedFilterDefinition,
} from '@/app/ops-analysis/utils/stringParamMultipleMigrate';

export const hasInvalidDateRangeDefinitions = (
  definitions: UnifiedFilterDefinition[],
): boolean => definitions.some(
  (definition) => definition.type === 'dateRange'
    && definition.defaultValue !== null
    && definition.defaultValue !== undefined
    && !validateDateRangeValue(definition.defaultValue).valid,
);

export const buildResetFilterValues = (
  definitions: UnifiedFilterDefinition[],
): Record<string, FilterValue> => definitions.reduce<Record<string, FilterValue>>(
  (values, definition) => {
    if (definition.type === 'dateRange') {
      if (definition.defaultValue === null || definition.defaultValue === undefined) {
        values[definition.id] = null;
      } else if (validateDateRangeValue(definition.defaultValue).valid) {
        values[definition.id] = {
          ...(definition.defaultValue as DateRangeValue),
        };
      }
      return values;
    }

    values[definition.id] = definition.defaultValue ?? null;
    return values;
  },
  {},
);

const parseStoredFilterDefinitions = (
  rawFilters: unknown,
): LegacyUnifiedFilterDefinition[] => {
  if (Array.isArray(rawFilters)) {
    return rawFilters as LegacyUnifiedFilterDefinition[];
  }
  if (!rawFilters || typeof rawFilters !== 'object') {
    return [];
  }
  const candidate = rawFilters as {
    definitions?: unknown;
    unifiedFilters?: unknown;
  };
  if (Array.isArray(candidate.definitions)) {
    return candidate.definitions as LegacyUnifiedFilterDefinition[];
  }
  if (Array.isArray(candidate.unifiedFilters)) {
    return candidate.unifiedFilters as LegacyUnifiedFilterDefinition[];
  }
  return [];
};

export const normalizeStoredFilterDefinitions = (
  rawFilters: unknown,
  options?: { canvasId?: string | number; values?: Record<string, FilterValue> },
): UnifiedFilterDefinition[] => {
  const migrated = migrateUnifiedFilterDefinitions(
    parseStoredFilterDefinitions(rawFilters),
    options?.values || {},
  );
  logStringParamMigrationWarnings(migrated.warnings, {
    canvasId: options?.canvasId,
  });
  return migrated.definitions;
};

export const normalizeStoredFilterState = (
  rawFilters: unknown,
  values: Record<string, FilterValue> = {},
  options?: { canvasId?: string | number },
): {
  definitions: UnifiedFilterDefinition[];
  values: Record<string, FilterValue>;
} => {
  const migrated = migrateUnifiedFilterDefinitions(
    parseStoredFilterDefinitions(rawFilters),
    values,
  );
  logStringParamMigrationWarnings(migrated.warnings, {
    canvasId: options?.canvasId,
  });
  return {
    definitions: migrated.definitions,
    values: migrated.values,
  };
};

export const syncFilterValuesWithDefinitions = (
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

  nextDefinitions.forEach((definition) => {
    if (
      definition.type === 'dateRange'
      && Object.prototype.hasOwnProperty.call(updatedValues, definition.id)
      && updatedValues[definition.id] === null
    ) {
      return;
    }

    const hasValue =
      updatedValues[definition.id] !== undefined &&
      updatedValues[definition.id] !== null;

    if (!definition.enabled || hasValue) return;

    if (
      definition.defaultValue === undefined ||
      definition.defaultValue === null
    ) {
      return;
    }

    if (definition.type === 'timeRange') {
      const normalizedValue = normalizeTimeRangeFilterValue(
        definition.defaultValue,
      );
      if (normalizedValue) {
        updatedValues[definition.id] = normalizedValue;
      }
      return;
    }

    if (definition.type === 'dateRange') {
      if (validateDateRangeValue(definition.defaultValue).valid) {
        updatedValues[definition.id] = {
          ...(definition.defaultValue as DateRangeValue),
        };
      }
      return;
    }

    // 动态选项的默认值可能属于别的组织，等选项列表回来后再套用。
    if (isDynamicOptionFilter(definition)) return;

    updatedValues[definition.id] = definition.defaultValue;
  });

  return coerceFilterValuesForDefinitions(nextDefinitions, updatedValues);
};

export const isOrganizationFilterDefinition = (
  definition: UnifiedFilterDefinition,
): boolean => definition.type === 'string'
  && isOrganizationControl(definition);

export const resolveCanvasOrganizationId = ({
  shareMode,
  renderMode = false,
  shareSpaceId,
  selectedGroupId,
}: {
  shareMode: boolean;
  renderMode?: boolean;
  shareSpaceId?: string | number | null;
  selectedGroupId?: string | number | null;
}): string | number | undefined => {
  if (renderMode) {
    return undefined;
  }
  if (shareMode) {
    if (shareSpaceId === undefined || shareSpaceId === null || shareSpaceId === '') {
      return undefined;
    }
    return shareSpaceId;
  }
  if (selectedGroupId === undefined || selectedGroupId === null || selectedGroupId === '') {
    return undefined;
  }
  return selectedGroupId;
};

export const applySelectedOrganizationToFilterValues = (
  definitions: UnifiedFilterDefinition[],
  values: Record<string, FilterValue>,
  selectedOrganizationId?: string | number | null,
): Record<string, FilterValue> => {
  if (
    selectedOrganizationId === undefined
    || selectedOrganizationId === null
    || selectedOrganizationId === ''
  ) {
    return values;
  }

  const nextValues = { ...values };
  const organizationValue = String(selectedOrganizationId);
  definitions.forEach((definition) => {
    if (!definition.enabled || !isOrganizationFilterDefinition(definition)) {
      return;
    }
    nextValues[definition.id] = organizationValue;
  });
  return nextValues;
};

export const fillMissingOrganizationFilterValues = (
  definitions: UnifiedFilterDefinition[],
  values: Record<string, FilterValue>,
  selectedOrganizationId?: string | number | null,
): Record<string, FilterValue> => {
  if (
    selectedOrganizationId === undefined
    || selectedOrganizationId === null
    || selectedOrganizationId === ''
  ) {
    return values;
  }

  const nextValues = { ...values };
  const organizationValue = String(selectedOrganizationId);
  let changed = false;
  definitions.forEach((definition) => {
    if (!definition.enabled || !isOrganizationFilterDefinition(definition)) {
      return;
    }
    const current = nextValues[definition.id];
    if (current === undefined || current === null || current === '') {
      nextValues[definition.id] = organizationValue;
      changed = true;
    }
  });
  return changed ? nextValues : values;
};

export const syncAndFillOrganizationFilterValues = (
  definitions: UnifiedFilterDefinition[],
  values: Record<string, FilterValue>,
  selectedOrganizationId?: string | number | null,
): Record<string, FilterValue> => fillMissingOrganizationFilterValues(
  definitions,
  syncFilterValuesWithDefinitions(definitions, values),
  selectedOrganizationId,
);

const isEmptyFilterValue = (value: FilterValue | undefined): boolean =>
  value === undefined || value === null;

const getTimeRangeIdentity = (value: FilterValue | undefined): string => {
  if (isEmptyFilterValue(value)) {
    return 'empty';
  }
  if (typeof value === 'number' && Number.isFinite(value) && value > 0) {
    return `relative:${value}`;
  }
  if (Array.isArray(value) && value.length === 2 && value[0] && value[1]) {
    return `custom:${String(value[0])}:${String(value[1])}`;
  }
  if (typeof value === 'object') {
    const candidate = value as Partial<TimeRangeValue>;
    if (
      typeof candidate.selectValue === 'number'
      && Number.isFinite(candidate.selectValue)
      && candidate.selectValue > 0
    ) {
      return `relative:${candidate.selectValue}`;
    }
    if (candidate.start && candidate.end) {
      return `custom:${String(candidate.start)}:${String(candidate.end)}`;
    }
  }
  return `other:${JSON.stringify(value)}`;
};

const isSameDateRangeValue = (
  left: FilterValue | undefined,
  right: FilterValue | undefined,
): boolean => {
  if (isEmptyFilterValue(left) && isEmptyFilterValue(right)) {
    return true;
  }
  if (isEmptyFilterValue(left) || isEmptyFilterValue(right)) {
    return false;
  }
  if (
    typeof left !== 'object'
    || typeof right !== 'object'
    || Array.isArray(left)
    || Array.isArray(right)
  ) {
    return false;
  }
  const leftRange = left as DateRangeValue;
  const rightRange = right as DateRangeValue;
  if (leftRange.rangeType !== rightRange.rangeType) {
    return false;
  }
  if (leftRange.rangeType === 'custom' && rightRange.rangeType === 'custom') {
    return leftRange.startDate === rightRange.startDate
      && leftRange.endDate === rightRange.endDate;
  }
  return true;
};

const isSamePlainFilterValue = (
  left: FilterValue | undefined,
  right: FilterValue | undefined,
): boolean => {
  if (isEmptyFilterValue(left) && isEmptyFilterValue(right)) {
    return true;
  }
  if (isEmptyFilterValue(left) || isEmptyFilterValue(right)) {
    return false;
  }
  if (Array.isArray(left) || Array.isArray(right)) {
    if (!Array.isArray(left) || !Array.isArray(right) || left.length !== right.length) {
      return false;
    }
    return left.every((item, index) => item === right[index]);
  }
  return left === right;
};

const shapeStringValue = (
  definition: UnifiedFilterDefinition,
  value: FilterValue | undefined,
): FilterValue | undefined => {
  if (definition.type !== 'string' || isEmptyFilterValue(value)) {
    return value;
  }
  return coerceValueForMultiple(
    value,
    isMultipleSelectInputConfig(definition.inputConfig),
  ) ?? null;
};

const isSameFilterValue = (
  type: UnifiedFilterDefinition['type'],
  left: FilterValue | undefined,
  right: FilterValue | undefined,
): boolean => {
  if (type === 'timeRange') {
    return getTimeRangeIdentity(left) === getTimeRangeIdentity(right);
  }
  if (type === 'dateRange') {
    return isSameDateRangeValue(left, right);
  }
  return isSamePlainFilterValue(left, right);
};

const materializeDefaultValue = (
  definition: UnifiedFilterDefinition,
): FilterValue => {
  const raw = definition.defaultValue;
  if (raw === undefined || raw === null) {
    return null;
  }
  if (definition.type === 'timeRange') {
    return normalizeTimeRangeFilterValue(raw) ?? null;
  }
  if (definition.type === 'dateRange') {
    return validateDateRangeValue(raw).valid
      ? { ...(raw as DateRangeValue) }
      : null;
  }
  if (definition.type === 'string') {
    return coerceValueForMultiple(
      raw,
      isMultipleSelectInputConfig(definition.inputConfig),
    );
  }
  return raw;
};

/**
 * 确认配置时：仅当某项默认值语义变化，且顶部筛选仍停在旧默认上，才写入新默认。
 * 相对时间只比 selectValue，避免 start/end 毫秒差误判；组织项不覆盖。
 */
const applyChangedDefaultsIfStillOnPrevious = (
  previousDefinitions: UnifiedFilterDefinition[],
  nextDefinitions: UnifiedFilterDefinition[],
  values: Record<string, FilterValue>,
): { values: Record<string, FilterValue>; updatedIds: string[] } => {
  if (!previousDefinitions.length) {
    return { values, updatedIds: [] };
  }

  const previousById = new Map(
    previousDefinitions.map((definition) => [definition.id, definition]),
  );
  const nextValues = { ...values };
  const updatedIds: string[] = [];

  nextDefinitions.forEach((definition) => {
    const previous = previousById.get(definition.id);
    if (!previous || !definition.enabled || isOrganizationFilterDefinition(definition)) {
      return;
    }

    const previousDefault = shapeStringValue(definition, previous.defaultValue);
    const nextDefault = shapeStringValue(definition, definition.defaultValue);
    const defaultChanged = previous.type !== definition.type
      || !isSameFilterValue(definition.type, previousDefault, nextDefault);
    if (!defaultChanged) {
      return;
    }

    const current = nextValues[definition.id];
    const compareType = previous.type === definition.type
      ? definition.type
      : previous.type;
    if (!isSameFilterValue(
      compareType,
      shapeStringValue(definition, current),
      shapeStringValue(previous, previous.defaultValue),
    )) {
      return;
    }

    nextValues[definition.id] = materializeDefaultValue(definition);
    updatedIds.push(definition.id);
  });

  return {
    values: coerceFilterValuesForDefinitions(nextDefinitions, nextValues),
    updatedIds,
  };
};

/** 筛选配置确认：draft/applied 使用同一版 definitions 规范化 values。 */
export interface FilterConfigConfirmSnapshot {
  definitions: UnifiedFilterDefinition[];
  filterValues: Record<string, FilterValue>;
  appliedFilterValues: Record<string, FilterValue>;
}

export const buildFilterConfigConfirmSnapshot = (
  newDefinitions: UnifiedFilterDefinition[],
  currentFilterValues: Record<string, FilterValue>,
  currentAppliedFilterValues: Record<string, FilterValue>,
  previousDefinitions: UnifiedFilterDefinition[] = [],
): FilterConfigConfirmSnapshot => {
  const syncedFilterValues = syncFilterValuesWithDefinitions(
    newDefinitions,
    currentFilterValues,
  );
  const syncedAppliedFilterValues = syncFilterValuesWithDefinitions(
    newDefinitions,
    currentAppliedFilterValues,
  );
  const { values: nextFilterValues, updatedIds } = applyChangedDefaultsIfStillOnPrevious(
    previousDefinitions,
    newDefinitions,
    syncedFilterValues,
  );
  const nextAppliedFilterValues = { ...syncedAppliedFilterValues };
  updatedIds.forEach((filterId) => {
    nextAppliedFilterValues[filterId] = nextFilterValues[filterId];
  });
  return {
    definitions: newDefinitions,
    filterValues: nextFilterValues,
    appliedFilterValues: nextAppliedFilterValues,
  };
};
