import type {
  ConditionFieldOption,
  ConditionFieldSource,
  ConditionFieldValueType,
  SourceRef,
} from '@/app/ops-analysis/types/dataSource';

const readOptionList = (raw: unknown): NonNullable<ConditionFieldOption['options']> => {
  if (!Array.isArray(raw)) return [];
  return raw.flatMap((option) => {
    if (!option || typeof option !== 'object') return [];
    const record = option as { label?: unknown; value?: unknown; query_objects?: unknown };
    if (record.value === undefined || record.value === null || record.value === '') return [];
    const value = typeof record.value === 'number' ? record.value : String(record.value);
    const queryObjects = Array.isArray(record.query_objects)
      ? record.query_objects.map((item) => String(item)).filter(Boolean)
      : [];
    return [{
      label: String(record.label ?? value),
      value,
      ...(queryObjects.length ? { query_objects: queryObjects } : {}),
    }];
  });
};

/** 枚举必须自带选项。没有选项的字段是输入框，不再另挂选项数据源。 */
export const presentConditionField = (field: ConditionFieldOption): ConditionFieldOption => {
  const queryObjects = field.query_objects?.filter(Boolean);
  const next: ConditionFieldOption = {
    value: field.value,
    label: field.label,
    ...(queryObjects?.length ? { query_objects: queryObjects } : {}),
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
  options: Array<{ label: string; value: string; query_objects?: string[] }>;
  query_objects?: string[];
}

export const draftFromConditionField = (field: ConditionFieldOption): ConditionFieldDraft => {
  const queryObjects = field.query_objects?.filter(Boolean);
  const shared = {
    value: field.value,
    label: field.label,
    ...(queryObjects?.length ? { query_objects: queryObjects } : {}),
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
        ...(option.query_objects?.length ? { query_objects: option.query_objects } : {}),
      })),
    };
  }
  return { ...shared, valueMode: 'input', options: [] };
};

export const conditionFieldFromDraft = (draft: ConditionFieldDraft): ConditionFieldOption | null => {
  const value = draft.value.trim();
  const label = draft.label.trim();
  if (!value || !label) return null;
  const queryObjects = draft.query_objects?.filter(Boolean);
  const shared = {
    value,
    label,
    ...(queryObjects?.length ? { query_objects: queryObjects } : {}),
  };
  if (draft.valueMode === 'number') {
    return { ...shared, valueType: 'number' };
  }
  if (draft.valueMode === 'options') {
    const options = draft.options
      .map((option) => ({
        label: option.label.trim(),
        value: option.value.trim(),
        ...(option.query_objects?.length ? { query_objects: option.query_objects } : {}),
      }))
      .filter((option) => option.label && option.value);
    if (!options.length) return null;
    return { ...shared, valueType: 'enum', options };
  }
  return { ...shared, valueType: 'string' };
};

/** 旧的跟随模型配置，打开齿轮时摊成和字符串下拉一样的数据源配置。 */
export const legacyDynamicConditionSource = (
  source: ConditionFieldSource,
): {
  sourceRef: SourceRef;
  valueField: string;
  labelField: string;
  queryParams: NonNullable<ConditionFieldSource['queryParams']>;
} | null => {
  if (source.kind === 'modelAttrs') {
    return {
      sourceRef: { type: 'rest_api', value: 'cmdb/list_cmdb_attr_options' },
      valueField: 'attr_id',
      labelField: 'attr_name',
      queryParams: { model_id: { ref: source.modelParam || 'model_id' } },
    };
  }
  if (source.kind === 'endModelAttrs') {
    return {
      sourceRef: { type: 'rest_api', value: 'cmdb/list_cmdb_attr_options' },
      valueField: 'attr_id',
      labelField: 'attr_name',
      queryParams: {
        start_model_id: { ref: source.startModelParam || 'start_model_id' },
        model_asst_id: { ref: source.associationParam || 'model_asst_id' },
      },
    };
  }
  return null;
};
