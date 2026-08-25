import type {
  FilterValue,
  UnifiedFilterDefinition,
} from '@/app/ops-analysis/types/dashBoard';
import { normalizeTimeRangeFilterValue } from '@/app/ops-analysis/utils/filterValue';
import { validateDateRangeValue } from '@/app/ops-analysis/utils/dateRange';
import type { DateRangeValue } from '@/app/ops-analysis/types/dateRange';
import {
  coerceFilterValuesForDefinitions,
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

    updatedValues[definition.id] = definition.defaultValue;
  });

  return coerceFilterValuesForDefinitions(nextDefinitions, updatedValues);
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
): FilterConfigConfirmSnapshot => ({
  definitions: newDefinitions,
  filterValues: syncFilterValuesWithDefinitions(
    newDefinitions,
    currentFilterValues,
  ),
  appliedFilterValues: syncFilterValuesWithDefinitions(
    newDefinitions,
    currentAppliedFilterValues,
  ),
});
