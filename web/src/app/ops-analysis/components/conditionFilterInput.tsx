'use client';

import React, { useMemo } from 'react';
import { Button, Input, InputNumber, Select } from 'antd';
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons';
import type { ConditionFieldOption } from '@/app/ops-analysis/types/dataSource';
import {
  addConditionRow,
  operatorsForFieldType,
  parseConditionGroup,
  removeConditionRow,
  setConditionLogic,
  updateConditionRow,
  type ConditionGroup,
} from '@/app/ops-analysis/utils/conditionFilter';
import { useTranslation } from '@/utils/i18n';

interface ConditionFilterInputProps {
  value?: unknown;
  onChange?: (value: ConditionGroup) => void;
  fields: ConditionFieldOption[];
  queryObject?: string;
  disabled?: boolean;
}

const operatorLabel = (op: string, t: (key: string) => string) => {
  if (op === 'eq') return t('dashboard.conditionFilter.eq');
  if (op === 'ne') return t('dashboard.conditionFilter.ne');
  if (op === 'regex') return t('dashboard.conditionFilter.regex');
  if (op === 'notRegex') return t('dashboard.conditionFilter.notRegex');
  if (op === 'contains') return t('dashboard.conditionFilter.contains');
  if (op === 'empty') return t('dashboard.conditionFilter.empty');
  if (op === 'gt') return t('dashboard.conditionFilter.gt');
  if (op === 'gte') return t('dashboard.conditionFilter.gte');
  if (op === 'lt') return t('dashboard.conditionFilter.lt');
  if (op === 'lte') return t('dashboard.conditionFilter.lte');
  if (op === 'in') return t('dashboard.conditionFilter.in');
  return op;
};

/**
 * 槽位负责行宽。Form.Item 里的 Select 会带上 ant-select-in-form-item { width:100% }，
 * 直接当作 flex 子项时，运算符会占满整行，字段和值被挤到 0 宽。
 */
const FieldSlot = ({ children }: { children: React.ReactNode }) => (
  <div data-slot="field" className="min-w-[72px] flex-1 basis-0">
    {children}
  </div>
);

const OperatorSlot = ({ children }: { children: React.ReactNode }) => (
  <div data-slot="operator" className="w-[108px] shrink-0">
    {children}
  </div>
);

const ValueSlot = ({ children }: { children: React.ReactNode }) => (
  <div data-slot="value" className="min-w-[72px] flex-1 basis-0">
    {children}
  </div>
);

const ConditionFilterInput: React.FC<ConditionFilterInputProps> = ({
  value,
  onChange,
  fields,
  queryObject = '',
  disabled = false,
}) => {
  const { t } = useTranslation();
  const group = useMemo(() => parseConditionGroup(value), [value]);
  const fieldMap = useMemo(
    () => new Map(fields.map((field) => [field.value, field])),
    [fields],
  );
  const emit = (next: ConditionGroup) => onChange?.(next);
  const fieldLocked = fields.length <= 1;

  return (
    <div className="flex w-full min-w-0 flex-col gap-2">
      {group.items.length > 0 ? (
        <Select
          aria-label={t('dashboard.conditionFilter.logic')}
          data-testid="condition-logic"
          className="w-full"
          style={{ width: '100%' }}
          disabled={disabled}
          value={group.logic}
          options={[
            { value: 'AND', label: t('dashboard.conditionFilter.matchAll') },
            { value: 'OR', label: t('dashboard.conditionFilter.matchAny') },
          ]}
          onChange={(logic) => emit(setConditionLogic(group, logic === 'OR' ? 'OR' : 'AND'))}
        />
      ) : null}
      {group.items.map((item, index) => {
        const field = fieldMap.get(String(item.field || ''));
        const valueType = field?.valueType || 'string';
        const operators = operatorsForFieldType(valueType);
        const multiple = item.op === 'in';
        return (
          <div
            key={`${item.field || 'row'}-${index}`}
            data-testid={`condition-row-${index}`}
            className="flex w-full min-w-0 items-center gap-2"
          >
            <FieldSlot>
              <Select
                aria-label={t('dashboard.conditionFilter.field')}
                data-testid="condition-field"
                className="w-full"
                style={{ width: '100%' }}
                disabled={disabled || fieldLocked}
                placeholder={t('dashboard.conditionFilter.field')}
                value={item.field || undefined}
                options={fields.map((option) => ({ label: option.label, value: option.value }))}
                onChange={(nextField) => {
                  const next = fieldMap.get(String(nextField));
                  const nextOps = operatorsForFieldType(next?.valueType);
                  emit(updateConditionRow(group, index, {
                    field: String(nextField),
                    op: nextOps[0],
                    value: undefined,
                  }));
                }}
              />
            </FieldSlot>
            <OperatorSlot>
              <Select
                aria-label={t('dashboard.conditionFilter.op')}
                data-testid="condition-operator"
                className="w-full"
                style={{ width: '100%' }}
                disabled={disabled}
                value={item.op || undefined}
                options={operators.map((op) => ({ label: operatorLabel(op, t), value: op }))}
                onChange={(op) => emit(updateConditionRow(group, index, { op, value: undefined }))}
              />
            </OperatorSlot>
            <ValueSlot>
              {item.op === 'empty' ? <div className="min-h-8" /> : null}
              {item.op !== 'empty' && valueType === 'number' ? (
                <InputNumber
                  aria-label={t('dashboard.conditionFilter.value')}
                  data-testid="condition-value"
                  className="w-full"
                  style={{ width: '100%' }}
                  disabled={disabled}
                  value={typeof item.value === 'number' ? item.value : undefined}
                  onChange={(next) => emit(updateConditionRow(group, index, { value: next }))}
                />
              ) : null}
              {item.op !== 'empty' && valueType === 'enum' ? (
                <Select
                  aria-label={t('dashboard.conditionFilter.value')}
                  data-testid="condition-value"
                  className="w-full"
                  style={{ width: '100%' }}
                  disabled={disabled}
                  mode={multiple ? 'multiple' : undefined}
                  value={multiple ? (Array.isArray(item.value) ? item.value : []) : item.value}
                  options={(field?.options || []).filter((option) => (
                    !queryObject || !option.query_objects?.length || option.query_objects.includes(queryObject)
                  )).map((option) => ({
                    label: option.label,
                    value: option.value,
                  }))}
                  onChange={(next) => emit(updateConditionRow(group, index, { value: next }))}
                />
              ) : null}
              {item.op !== 'empty' && valueType === 'string' ? (
                <Input
                  aria-label={t('dashboard.conditionFilter.value')}
                  data-testid="condition-value"
                  className="w-full"
                  style={{ width: '100%' }}
                  disabled={disabled}
                  value={item.value === undefined || item.value === null ? '' : String(item.value)}
                  onChange={(event) => emit(updateConditionRow(group, index, { value: event.target.value }))}
                />
              ) : null}
            </ValueSlot>
            <Button
              type="text"
              className="shrink-0"
              aria-label={t('dashboard.conditionFilter.delete')}
              icon={<DeleteOutlined />}
              disabled={disabled}
              onClick={() => emit(removeConditionRow(group, index))}
            />
          </div>
        );
      })}
      <Button
        type="dashed"
        className="self-start"
        aria-label={t('dashboard.conditionFilter.add')}
        icon={<PlusOutlined />}
        disabled={disabled}
        onClick={() => emit(addConditionRow(group, fields.length === 1 ? fields[0] : undefined))}
      >
        {t('dashboard.conditionFilter.add')}
      </Button>
    </div>
  );
};

export default ConditionFilterInput;
