import type {
  ConditionFieldOption,
  ConditionFieldValueType,
  ConditionFilterItem,
  ConditionFilterValue,
  ConditionLogic,
} from '@/app/ops-analysis/types/dataSource';

export interface ConditionGroup {
  logic: ConditionLogic;
  items: ConditionFilterItem[];
}

const OPERATOR_BY_TYPE: Record<ConditionFieldValueType, string[]> = {
  string: ['eq', 'ne', 'regex', 'notRegex', 'contains', 'empty'],
  number: ['gt', 'gte', 'eq', 'lte', 'lt'],
  enum: ['eq', 'ne', 'in'],
};

export const operatorsForFieldType = (valueType: ConditionFieldValueType | undefined): string[] =>
  OPERATOR_BY_TYPE[valueType || 'string'];

export const parseConditionGroup = (raw: unknown): ConditionGroup => {
  if (Array.isArray(raw)) {
    return { logic: 'AND', items: raw.filter(isConditionItem) };
  }
  if (raw && typeof raw === 'object') {
    const record = raw as ConditionFilterValue;
    const logic: ConditionLogic = record.logic === 'OR' ? 'OR' : 'AND';
    const items = Array.isArray(record.items) ? record.items.filter(isConditionItem) : [];
    return { logic, items };
  }
  return { logic: 'AND', items: [] };
};

const isConditionItem = (item: unknown): item is ConditionFilterItem =>
  Boolean(item) && typeof item === 'object' && !Array.isArray(item);

export const toggleConditionLogic = (group: ConditionGroup): ConditionGroup => ({
  ...group,
  logic: group.logic === 'OR' ? 'AND' : 'OR',
});

export const setConditionLogic = (
  group: ConditionGroup,
  logic: ConditionLogic,
): ConditionGroup => ({
  ...group,
  logic: logic === 'OR' ? 'OR' : 'AND',
});

export const addConditionRow = (
  group: ConditionGroup,
  field?: ConditionFieldOption,
): ConditionGroup => ({
  ...group,
  items: [
    ...group.items,
    {
      field: field?.value || '',
      op: operatorsForFieldType(field?.valueType)[0],
      value: undefined,
    },
  ],
});

export const removeConditionRow = (group: ConditionGroup, index: number): ConditionGroup => ({
  logic: group.logic,
  items: group.items.filter((_, itemIndex) => itemIndex !== index),
});

export const updateConditionRow = (
  group: ConditionGroup,
  index: number,
  patch: ConditionFilterItem,
): ConditionGroup => ({
  ...group,
  items: group.items.map((item, itemIndex) => (itemIndex === index ? { ...item, ...patch } : item)),
});

/** 字段或枚举选项变化后丢掉失效字段，并清掉已经不在选项里的值。 */
export const reconcileConditionRows = (
  group: ConditionGroup,
  fields: ConditionFieldOption[],
): ConditionGroup => {
  const pruned = pruneConditionRows(group, fields);
  const fieldMap = new Map(fields.map((field) => [field.value, field]));
  return {
    logic: pruned.logic,
    items: pruned.items.map((item) => {
      const field = fieldMap.get(String(item.field || ''));
      if (!field || field.valueType !== 'enum' || !field.options?.length) return item;
      const allowed = new Set(field.options.map((option) => String(option.value)));
      if (Array.isArray(item.value)) {
        const next = item.value.filter((entry) => allowed.has(String(entry)));
        return next.length === item.value.length ? item : { ...item, value: next };
      }
      if (item.value !== undefined && item.value !== '' && !allowed.has(String(item.value))) {
        return { ...item, value: undefined };
      }
      return item;
    }),
  };
};

/** 字段列表变化后丢掉已经不存在的字段，保留空行和逻辑关系。 */
export const pruneConditionRows = (
  group: ConditionGroup,
  fields: ConditionFieldOption[],
): ConditionGroup => {
  const allowed = new Set(fields.map((field) => field.value));
  return {
    logic: group.logic,
    items: group.items.filter((item) => !item.field || allowed.has(item.field)),
  };
};

export const conditionGroupIsEmpty = (group: ConditionGroup): boolean =>
  group.items.every((item) => !item.field && !item.op && (item.value === undefined || item.value === ''));
