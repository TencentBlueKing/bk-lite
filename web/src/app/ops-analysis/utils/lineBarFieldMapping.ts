import type { ResponseFieldDefinition } from '@/app/ops-analysis/types/dataSource';
import {
  collectSampleFieldKeys,
  collectSampleRows,
  type WidgetFieldSelectOption,
} from '@/app/ops-analysis/components/widgetConfig/utils/chartFieldOptions';
import { coerceTopNNumericValue } from '@/app/ops-analysis/utils/topNData';

export interface LineBarFieldMappingInput {
  dimensionField?: string;
  valueField?: string;
  valueFields?: string[];
  seriesField?: string;
  fieldLabels?: Record<string, string>;
}

export const trimLineBarField = (value?: string) => {
  const trimmed = value?.trim();
  return trimmed || '';
};

export const normalizeLineBarFieldList = (fields?: string[] | null): string[] => {
  const result: string[] = [];
  const seen = new Set<string>();
  (fields || []).forEach((field) => {
    const trimmed = trimLineBarField(typeof field === 'string' ? field : '');
    if (!trimmed || seen.has(trimmed)) {
      return;
    }
    seen.add(trimmed);
    result.push(trimmed);
  });
  return result;
};

export const resolveLineBarValueFields = (
  mapping?: LineBarFieldMappingInput,
): string[] => {
  const listed = normalizeLineBarFieldList(mapping?.valueFields);
  if (listed.length > 0) {
    return listed;
  }
  const single = trimLineBarField(mapping?.valueField);
  return single ? [single] : [];
};

export const hasExplicitLineBarMapping = (mapping?: LineBarFieldMappingInput) =>
  Boolean(
    trimLineBarField(mapping?.dimensionField)
    || trimLineBarField(mapping?.valueField)
    || normalizeLineBarFieldList(mapping?.valueFields).length
    || trimLineBarField(mapping?.seriesField),
  );

export type LineBarMappingPlan =
  | { kind: 'none' }
  | { kind: 'legacy'; dimensionField: string; valueField: string }
  | { kind: 'single'; dimensionField: string; valueField: string }
  | { kind: 'wide'; dimensionField: string; valueFields: string[] }
  | { kind: 'long'; dimensionField: string; valueField: string; seriesField: string }
  | { kind: 'conflict' }
  | { kind: 'incomplete' };

/**
 * valueFields / seriesField 走新三字段规则。
 * 只带 dimensionField / valueField 的旧配置保持逐行单系列。
 */
export const planLineBarMapping = (
  mapping?: LineBarFieldMappingInput,
): LineBarMappingPlan => {
  if (!hasExplicitLineBarMapping(mapping)) {
    return { kind: 'none' };
  }

  const usesNewFields = normalizeLineBarFieldList(mapping?.valueFields).length > 0
    || Boolean(trimLineBarField(mapping?.seriesField));
  const dimensionField = trimLineBarField(mapping?.dimensionField);
  const valueFields = resolveLineBarValueFields(mapping);
  const seriesField = trimLineBarField(mapping?.seriesField);

  if (!usesNewFields) {
    return {
      kind: 'legacy',
      dimensionField,
      valueField: valueFields[0] || '',
    };
  }

  if (!dimensionField || valueFields.length === 0) {
    return { kind: 'incomplete' };
  }
  if (valueFields.length >= 2 && seriesField) {
    return { kind: 'conflict' };
  }
  if (valueFields.length >= 2) {
    return { kind: 'wide', dimensionField, valueFields };
  }
  if (seriesField) {
    return {
      kind: 'long',
      dimensionField,
      valueField: valueFields[0],
      seriesField,
    };
  }
  return { kind: 'single', dimensionField, valueField: valueFields[0] };
};

export const lineBarCellIsEmpty = (value: unknown) =>
  value == null || (typeof value === 'string' && value.trim() === '');

export const lineBarValueFieldsParse = (
  rows: Array<Record<string, unknown>>,
  fields: string[],
) => fields.every((field) => rows.every((row) => (
  lineBarCellIsEmpty(row[field]) || coerceTopNNumericValue(row[field]) !== null
)));

export const seriesLabelForField = (
  field: string,
  labels?: Record<string, string>,
) => trimLineBarField(labels?.[field]) || field;

export const toLineBarFieldMapping = (
  config?: LineBarFieldMappingInput,
  schema?: Array<{ key?: string; title?: string }>,
): LineBarFieldMappingInput => {
  const fieldLabels: Record<string, string> = {};
  (schema || []).forEach((field) => {
    const key = trimLineBarField(field.key);
    const title = trimLineBarField(field.title);
    if (key && title && title !== key) {
      fieldLabels[key] = title;
    }
  });
  return {
    dimensionField: config?.dimensionField,
    valueField: config?.valueField,
    valueFields: config?.valueFields,
    seriesField: config?.seriesField,
    ...(Object.keys(fieldLabels).length > 0 ? { fieldLabels } : {}),
  };
};

export const buildLineBarValueFieldOptions = (
  schemaFields: ResponseFieldDefinition[] = [],
  options: WidgetFieldSelectOption[],
): WidgetFieldSelectOption[] => {
  const schemaKeys = new Set(
    schemaFields.map((field) => field.key.trim()).filter(Boolean),
  );
  const numberKeys = new Set(
    schemaFields
      .filter((field) => field.value_type === 'number')
      .map((field) => field.key.trim())
      .filter(Boolean),
  );
  if (numberKeys.size === 0) {
    return options;
  }
  return options.filter((option) => (
    numberKeys.has(option.value) || !schemaKeys.has(option.value)
  ));
};

const isPlainRecord = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === 'object' && !Array.isArray(value);

const columnLooksNumeric = (
  key: string,
  valueType: string | undefined,
  rows: Array<Record<string, unknown>>,
) => {
  if (valueType === 'number') {
    return true;
  }
  if (valueType) {
    return false;
  }
  const present = rows
    .map((row) => row[key])
    .filter((value) => !lineBarCellIsEmpty(value));
  return present.length > 0
    && present.every((value) => coerceTopNNumericValue(value) !== null);
};

/** 字段名启发式，仅供测试和内部调用。配置界面不提供「恢复推荐」。 */
export const recommendLineBarFields = (
  fields: Array<{ key?: string; value_type?: string }> = [],
  sample?: unknown,
): { dimensionField?: string; valueFields: string[] } => {
  const rows = collectSampleRows(sample).filter(isPlainRecord);
  const keys: string[] = [];
  const seen = new Set<string>();
  const types = new Map<string, string>();
  const push = (key?: string, valueType?: string) => {
    const trimmed = trimLineBarField(key);
    if (!trimmed || seen.has(trimmed)) {
      return;
    }
    seen.add(trimmed);
    keys.push(trimmed);
    if (valueType) {
      types.set(trimmed, valueType);
    }
  };
  fields.forEach((field) => push(field.key, field.value_type));
  collectSampleFieldKeys(sample).forEach((key) => push(key));

  const nameKey = keys.find((key) => key.toLowerCase() === 'name');
  const valueKey = keys.find((key) => key.toLowerCase() === 'value');
  if (nameKey && valueKey && nameKey !== valueKey) {
    return { dimensionField: nameKey, valueFields: [valueKey] };
  }

  const numeric = (key: string) => columnLooksNumeric(key, types.get(key), rows);
  return {
    dimensionField: keys.find((key) => !numeric(key)),
    valueFields: keys.some(numeric) ? [keys.find(numeric) as string] : [],
  };
};

export interface LineBarFormFields {
  dimensionField?: string;
  valueField?: string;
  valueFields?: string[];
  seriesField?: string;
}

export const persistLineBarFormFields = (
  values: LineBarFormFields,
  forPreview = false,
): { error: 'incomplete' | 'conflict' } | { fields: LineBarFormFields } => {
  const dimensionField = trimLineBarField(values.dimensionField);
  // 没有 valueFields 数组时沿用旧的 valueField，并且不把列表写回去。
  // 空数组表示用户清空了多选，不再退回 valueField。
  const userListedValues = Array.isArray(values.valueFields);
  const listedValues = userListedValues
    ? normalizeLineBarFieldList(values.valueFields)
    : [];
  const legacyValue = trimLineBarField(values.valueField);
  const valueFields = listedValues.length > 0
    ? listedValues
    : (!userListedValues && legacyValue ? [legacyValue] : []);
  const rawSeries = trimLineBarField(values.seriesField);
  const seriesCollides = Boolean(
    rawSeries && (rawSeries === dimensionField || valueFields.includes(rawSeries)),
  );
  const seriesField = seriesCollides ? '' : rawSeries;
  const any = Boolean(dimensionField || valueFields.length || rawSeries);
  if (!any) {
    return { fields: {} };
  }

  if (valueFields.length >= 2 && seriesField) {
    if (!forPreview) {
      return { error: 'conflict' };
    }
    return {
      fields: {
        dimensionField: dimensionField || undefined,
        valueFields,
        seriesField,
      },
    };
  }

  if (!dimensionField || valueFields.length === 0) {
    if (!forPreview) {
      return { error: 'incomplete' };
    }
    return {
      fields: {
        dimensionField: dimensionField || undefined,
        valueFields: userListedValues && valueFields.length > 0 ? valueFields : undefined,
        valueField: valueFields.length === 1 ? valueFields[0] : undefined,
        seriesField: seriesField || undefined,
      },
    };
  }

  return {
    fields: {
      dimensionField,
      valueFields: userListedValues ? valueFields : undefined,
      valueField: valueFields.length === 1 ? valueFields[0] : undefined,
      seriesField: seriesField || undefined,
    },
  };
};
