import type { ResponseFieldDefinition } from '@/app/ops-analysis/types/dataSource';
import type { TableColumnConfigItem } from '@/app/ops-analysis/types/dashBoard';

export type DisplayColumnRow = TableColumnConfigItem & {
  id: string;
  isDefault?: boolean;
};

/**
 * Check if a field key should be displayed by default
 * Excludes fields starting with underscore
 */
export const isDisplayableDefaultField = (key: string): boolean => {
  const normalized = (key || '').trim();
  if (!normalized) {
    return false;
  }
  return !normalized.startsWith('_');
};

/**
 * Build display columns from schema field definitions
 */
export const buildDisplayColumnsFromSchema = (
  fields: ResponseFieldDefinition[],
): DisplayColumnRow[] => {
  return (fields || [])
    .filter((field) => isDisplayableDefaultField(field.key))
    .map((field, idx) => ({
      id: `column_schema_${Date.now()}_${idx}`,
      key: field.key,
      title: field.title || field.key,
      visible: true,
      order: idx,
      isDefault: true,
    }));
};

/**
 * Extract the first record from source data for field detection
 * Handles multiple data structures: table format {items: [...]} and chart format [...]
 */
export const extractFirstRecordFromSourceData = (
  sourceData: any,
): Record<string, unknown> | null => {
  if (!sourceData) return null;

  if (
    typeof sourceData === 'object' &&
    !Array.isArray(sourceData) &&
    Array.isArray(sourceData.items)
  ) {
    const first = sourceData.items.find(
      (item: any) => item && typeof item === 'object',
    );
    return first || null;
  }

  if (Array.isArray(sourceData)) {
    const first = sourceData.find(
      (item: any) => item && typeof item === 'object',
    );
    return first || null;
  }

  return null;
};

/**
 * Merge detected field keys with schema definitions to build display columns
 */
export const mergeDetectedFieldsWithSchema = (
  detectedFieldKeys: string[],
  schemaFields: ResponseFieldDefinition[],
): DisplayColumnRow[] => {
  const schemaTitleMap = new Map(
    (schemaFields || []).map((field) => [field.key, field.title || field.key]),
  );

  return detectedFieldKeys
    .filter((key) => isDisplayableDefaultField(key))
    .map((key, idx) => ({
      id: `column_detected_${Date.now()}_${idx}`,
      key,
      title: schemaTitleMap.get(key) || key,
      visible: true,
      order: idx,
      isDefault: true,
    }));
};

/**
 * Merge probed default columns with current columns
 * Preserves custom columns and updates default columns
 */
export const mergeProbedDefaultsWithCurrentColumns = (
  probedColumns: DisplayColumnRow[],
  currentColumns: DisplayColumnRow[],
): DisplayColumnRow[] => {
  const existingDefaultMap = new Map(
    currentColumns.filter((col) => col.isDefault).map((col) => [col.key, col]),
  );

  const mergedDefaults = probedColumns.map((col, idx) => {
    const existing = existingDefaultMap.get(col.key);
    return {
      ...col,
      id: existing?.id || col.id,
      visible: existing?.visible ?? col.visible,
      order: idx,
      isDefault: true,
    };
  });

  const customColumns = currentColumns
    .filter((col) => !col.isDefault)
    .map((col, idx) => ({
      ...col,
      order: mergedDefaults.length + idx,
    }));

  return [...mergedDefaults, ...customColumns];
};

/**
 * Create a new default display column
 */
export const createDefaultDisplayColumn = (
  currentLength: number,
): DisplayColumnRow => ({
  id: `column_${Date.now()}_${Math.random().toString(16).slice(2, 8)}`,
  key: '',
  title: '',
  visible: true,
  order: currentLength,
  isDefault: false,
});
