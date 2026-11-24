import { scopedFormFieldGroups, triggerValueModes, type ConditionRow, type TriggerDraft, type TriggerField, type TriggerOptions } from './trigger-config';

export type CatalogField = Omit<TriggerField, 'type'> & {
  type?: TriggerField['type'];
  source: string[];
};

export interface ConditionFieldCatalog {
  systemFields: CatalogField[];
  formFields: CatalogField[];
  byKey: Map<string, CatalogField>;
}

function collectFormFields(groups: NonNullable<TriggerOptions['form_field_groups']>) {
  const fields = new Map<string, CatalogField>();
  for (const group of groups) {
    for (const field of group.fields) {
      const current = fields.get(field.key);
      if (!current) {
        fields.set(field.key, { ...field, source: [group.name] });
        continue;
      }
      if (!current.source.includes(group.name)) current.source.push(group.name);
      if (current.type !== field.type) current.type = undefined;
      if (JSON.stringify(current.options) !== JSON.stringify(field.options)) current.options = undefined;
    }
  }
  return [...fields.values()];
}

export function conditionFieldCatalog(options: TriggerOptions | null, scope: TriggerDraft['scope']): ConditionFieldCatalog {
  const systemFields: CatalogField[] = (options?.system_fields ?? []).map(field => ({ ...field, source: [] }));
  const groups = options?.form_field_groups ?? [];
  const visibleGroups = scopedFormFieldGroups(groups, scope);
  const formFields = collectFormFields(visibleGroups);
  const byKey = new Map([...collectFormFields(groups), ...formFields, ...systemFields].map(field => [field.key, field]));
  return { systemFields, formFields, byKey };
}

export function conditionField(catalog: ConditionFieldCatalog, key: string): CatalogField | undefined {
  return catalog.byKey.get(key)
    ?? catalog.byKey.get(key === 'status' ? '$ticket.status' : `$form.${key}`);
}

export const emptyOperators = ['is_empty', 'not_empty'];
export const listOperators = ['in', 'not_in'];
const equalityOperators = ['=', '!='];
const orderedOperators = ['>', '>=', '<', '<='];

export function fieldOperators(field: CatalogField | undefined) {
  if (!field?.type) return undefined;
  if (field.type === 'list') return ['contains', 'in', ...emptyOperators];
  if (field.options?.length) return [...equalityOperators, ...listOperators, ...emptyOperators];
  if (field.type === 'number') return [...equalityOperators, ...orderedOperators, ...emptyOperators];
  if (field.type === 'boolean') return [...equalityOperators, ...emptyOperators];
  return [...equalityOperators, 'contains', ...listOperators, ...emptyOperators];
}

export function initialValueType(field: CatalogField | undefined, op: string): ConditionRow['valueType'] {
  const modes = triggerValueModes(op);
  if (modes.length < 2) return modes[0] ?? 'text';
  if (field?.type === 'number' || field?.type === 'boolean') return field.type;
  return modes[0];
}
