'use client';

import { Input, Select } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { TRIGGER_OPERATORS, triggerValueModes, type ConditionRow, type TriggerFieldOption } from './trigger-config';
import { conditionField, fieldOperators, initialValueType, listOperators, type CatalogField, type ConditionFieldCatalog } from './trigger-condition-fields';

const MANUAL_FIELD = '.manual-field';
const valueLabels = {
  text: 'triggerValueText', number: 'triggerNumber', boolean: 'triggerBoolean', json: 'triggerJson',
};

interface ConditionProps {
  row: ConditionRow;
  position: string;
  change: (row: ConditionRow) => void;
  catalog: ConditionFieldCatalog;
}

interface FieldOption {
  value: string;
  label: string;
  detail?: string;
}

function FieldPicker({ row, position, change, catalog }: ConditionProps) {
  const { t } = useTranslation();
  const option = (field: CatalogField, value = field.key): FieldOption => ({
    value,
    label: field.key.startsWith('$ticket.') ? t(`itsm.rule.triggerField_${field.key.slice(8)}`, field.label) : field.label,
    detail: [...field.source, field.key].join(' · '),
  });
  const groups = [
    { label: t('itsm.rule.triggerSystemFields'), options: catalog.systemFields.map(field => option(field)) },
    { label: t('itsm.rule.triggerFormFields'), options: catalog.formFields.map(field => option(field)) },
  ].filter(group => group.options.length);
  const currentField = conditionField(catalog, row.field);
  const selected = row.manualField ? MANUAL_FIELD : row.field || undefined;
  if (row.field && !row.manualField && !groups.some(group => group.options.some(item => item.value === row.field))) {
    groups.unshift({
      label: t('itsm.rule.triggerCurrentField'),
      options: [currentField ? option(currentField, row.field) : { value: row.field, label: row.field }],
    });
  }

  const fieldLabel = t('itsm.rule.field');
  return <div className="min-w-0 space-y-1">
    <span className="text-xs text-[var(--color-text-2)]">{fieldLabel}</span>
    <Select<string, FieldOption | { label: string; options: FieldOption[] }> className="w-full"
      aria-label={`${fieldLabel} ${position}`} value={selected} showSearch popupMatchSelectWidth={false}
      placeholder={t('itsm.rule.triggerFieldSelect')}
      filterOption={(input, item) => !!item && 'value' in item
        && [item.label, item.value, item.detail].some(text => text?.toLowerCase().includes(input.trim().toLowerCase()))}
      options={[...groups, { value: MANUAL_FIELD, label: t('itsm.rule.triggerManualField') }]}
      optionRender={({ data }) => 'value' in data
        ? <div className="max-w-96">
          <div>{data.label}</div>
          {data.detail && <div className="truncate text-xs text-[var(--color-text-3)]" title={data.detail}>{data.detail}</div>}
        </div>
        : data.label}
      onChange={key => {
        if (key === MANUAL_FIELD) {
          const retain = row.field && !catalog.byKey.has(row.field);
          change(retain ? { ...row, manualField: true } : { ...row, manualField: true, field: '', op: '=', valueType: 'text', input: '' });
          return;
        }
        if (key === row.field) return;
        const field = catalog.byKey.get(key);
        const op = field?.type === 'list' ? 'contains' : '=';
        change({ ...row, field: key, manualField: false, op, valueType: initialValueType(field, op), input: '' });
      }} />
    {row.manualField && <Input aria-label={`${t('itsm.rule.triggerFieldKey')} ${position}`} value={row.field}
      placeholder={t('itsm.rule.triggerFieldHint')} onChange={event => change({ ...row, field: event.target.value })} />}
  </div>;
}

function valueOptions(field: CatalogField | undefined, t: ReturnType<typeof useTranslation>['t']): TriggerFieldOption[] {
  if (field?.type === 'boolean') {
    return [{ value: true, label: t('itsm.rule.triggerTrue') }, { value: false, label: t('itsm.rule.triggerFalse') }];
  }
  return field?.options ?? [];
}

function parsedList(input: string): unknown[] | undefined {
  if (!input) return [];
  try {
    const value = JSON.parse(input);
    return Array.isArray(value) ? value : undefined;
  } catch {
    return undefined;
  }
}

function isOptionValue(value: unknown): value is TriggerFieldOption['value'] {
  return typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean';
}

function ConditionValue({ row, position, change, field }: Omit<ConditionProps, 'catalog'> & { field?: CatalogField }) {
  const { t } = useTranslation();
  const label = `${t('itsm.rule.value')} ${position}`;
  const choices = valueOptions(field, t);
  const isMembership = listOperators.includes(row.op);
  const selectedItems = isMembership && field?.type ? parsedList(row.input) : undefined;
  if (choices.length > 0 && selectedItems?.every(isOptionValue)) {
    const values = selectedItems.map(item => JSON.stringify(item));
    const options = choices.map(item => ({ value: JSON.stringify(item.value), label: item.label }));
    for (const value of values) {
      if (!options.some(item => item.value === value)) options.push({ value, label: String(JSON.parse(value)) });
    }
    return <Select className="w-full" mode="multiple" showSearch optionFilterProp="label" aria-label={label}
      placeholder={t('itsm.rule.triggerValueSelect')} value={values} options={options}
      onChange={items => change({ ...row, valueType: 'json', input: JSON.stringify(items.map((item: string) => JSON.parse(item))) })} />;
  }
  if (selectedItems?.every(item => typeof item === 'string') && (field?.type === 'text' || field?.type === 'list')) {
    return <Select className="w-full" mode="tags" aria-label={label} value={selectedItems}
      placeholder={t('itsm.rule.triggerValueTagsHint')} open={false}
      onChange={items => change({ ...row, valueType: 'json', input: JSON.stringify(items) })} />;
  }

  if (choices.length > 0 && !isMembership && ['=', '!=', 'contains'].includes(row.op) && row.valueType !== 'json') {
    const value = choices.find(item => typeof item.value === (row.valueType === 'text' ? 'string' : row.valueType)
      && String(item.value) === row.input);
    const options = choices.map(item => ({ value: JSON.stringify(item.value), label: item.label }));
    const selected = value ? JSON.stringify(value.value) : undefined;
    if (selected || !row.input) {
      return <Select className="w-full" showSearch optionFilterProp="label" aria-label={label}
        placeholder={t('itsm.rule.triggerValueSelect')} value={selected} options={options}
        onChange={id => {
          const value = JSON.parse(id) as TriggerFieldOption['value'];
          const valueType = typeof value === 'number' ? 'number' : typeof value === 'boolean' ? 'boolean' : 'text';
          change({ ...row, valueType, input: String(value) });
        }} />;
    }
  }

  const modes = triggerValueModes(row.op);
  const valueModes = field?.type ? [row.valueType] : modes;
  return <div className="flex flex-wrap items-start gap-1">
    {valueModes.length > 1 && <Select className="w-24" aria-label={`${t('itsm.rule.triggerValueType')} ${position}`}
      value={row.valueType} options={valueModes.map(mode => ({ value: mode, label: t(`itsm.rule.${valueLabels[mode]}`) }))}
      onChange={valueType => change({ ...row, valueType, input: '' })} />}
    <div className="min-w-24 flex-1">
      {row.valueType === 'boolean'
        ? <Select className="w-full" aria-label={label} value={row.input || undefined}
          options={[{ value: 'true', label: t('itsm.rule.triggerTrue') }, { value: 'false', label: t('itsm.rule.triggerFalse') }]}
          onChange={input => change({ ...row, input })} />
        : <Input aria-label={label} type={row.valueType === 'number' ? 'number' : 'text'}
          value={row.input} placeholder={row.valueType === 'json' ? t('itsm.rule.triggerJsonHint') : undefined}
          onChange={event => change({ ...row, input: event.target.value })} />}
    </div>
  </div>;
}

export function ConditionFields({ row, position, change, catalog }: ConditionProps) {
  const { t } = useTranslation();
  const field = row.manualField ? undefined : conditionField(catalog, row.field);
  const operators = fieldOperators(field);
  const operatorLabel = t('itsm.rule.triggerOperator');
  return <div className="grid min-w-0 flex-1 grid-cols-1 gap-2 sm:grid-cols-[minmax(0,1fr)_9rem_minmax(0,1.4fr)]">
    <FieldPicker row={row} position={position} change={change} catalog={catalog} />
    <div className="min-w-0 space-y-1">
      <span className="text-xs text-[var(--color-text-2)]">{operatorLabel}</span>
      <Select className="w-full" aria-label={`${operatorLabel} ${position}`} value={row.op} disabled={!row.field}
        options={TRIGGER_OPERATORS.filter(option => !operators || option.value === row.op || operators.includes(option.value))
          .map(option => ({
            value: option.value,
            label: t(`itsm.rule.${field?.type === 'list' && option.value === 'in' ? 'triggerListContainsAny' : option.labelKey}`),
          }))}
        onChange={op => {
          const modes = triggerValueModes(op);
          const valueType = field?.type || !modes.includes(row.valueType) ? initialValueType(field, op) : row.valueType;
          change({ ...row, op, valueType, input: valueType === row.valueType && modes.length ? row.input : '' });
        }} />
    </div>
    {row.field && triggerValueModes(row.op).length > 0 && <div className="min-w-0 space-y-1">
      <span className="text-xs text-[var(--color-text-2)]">{t('itsm.rule.value')}</span>
      <ConditionValue row={row} position={position} change={change} field={field} />
    </div>}
  </div>;
}
