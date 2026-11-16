import type {
  ConditionFieldOption,
  ConditionFieldValueType,
} from '@/app/ops-analysis/types/dataSource';

const readOptionList = (raw: unknown): NonNullable<ConditionFieldOption['options']> => {
  if (!Array.isArray(raw)) return [];
  return raw.flatMap((option) => {
    if (!option || typeof option !== 'object') return [];
    const record = option as { label?: unknown; value?: unknown };
    if (record.value === undefined || record.value === null || record.value === '') return [];
    const value = typeof record.value === 'number' ? record.value : String(record.value);
    return [{
      label: String(record.label ?? value),
      value,
    }];
  });
};

/** 枚举必须自带选项。没有选项的字段是输入框，不再另挂选项数据源。 */
export const presentConditionField = (field: ConditionFieldOption): ConditionFieldOption => {
  const next: ConditionFieldOption = {
    value: field.value,
    label: field.label,
  };
  if (field.valueType === 'number') {
    next.valueType = 'number';
    return next;
  }
  const options = readOptionList(field.options);
  if (field.valueType === 'enum' && options.length > 0) {
    next.valueType = 'enum';
    next.options = options;
    return next;
  }
  next.valueType = 'string';
  return next;
};

export const conditionFieldFromSourceRow = (
  item: Record<string, unknown>,
  valueField: string,
  labelField: string,
): ConditionFieldOption | null => {
  const rawValue = item[valueField];
  if (rawValue === undefined || rawValue === null || rawValue === '') return null;
  const valueType: ConditionFieldValueType = item.value_type === 'number' || item.value_type === 'enum'
    ? item.value_type
    : 'string';
  return presentConditionField({
    value: String(rawValue),
    label: String(item[labelField] ?? rawValue),
    valueType,
    options: readOptionList(item.options),
  });
};

export interface ConditionFieldDraft {
  value: string;
  label: string;
  valueMode: 'input' | 'number' | 'options';
  options: Array<{ label: string; value: string }>;
}

export const draftFromConditionField = (field: ConditionFieldOption): ConditionFieldDraft => {
  const shared = {
    value: field.value,
    label: field.label,
  };
  if (field.valueType === 'number') {
    return { ...shared, valueMode: 'number', options: [] };
  }
  if (field.valueType === 'enum' && field.options?.length) {
    return {
      ...shared,
      valueMode: 'options',
      options: field.options.map((option) => ({
        label: String(option.label ?? option.value),
        value: String(option.value),
      })),
    };
  }
  return { ...shared, valueMode: 'input', options: [] };
};

export const conditionFieldFromDraft = (draft: ConditionFieldDraft): ConditionFieldOption | null => {
  const value = draft.value.trim();
  const label = draft.label.trim();
  if (!value || !label) return null;
  const shared = {
    value,
    label,
  };
  if (draft.valueMode === 'number') {
    return { ...shared, valueType: 'number' };
  }
  if (draft.valueMode === 'options') {
    const options = draft.options
      .map((option) => ({
        label: option.label.trim(),
        value: option.value.trim(),
      }))
      .filter((option) => option.label && option.value);
    if (!options.length) return null;
    return { ...shared, valueType: 'enum', options };
  }
  return { ...shared, valueType: 'string' };
};
