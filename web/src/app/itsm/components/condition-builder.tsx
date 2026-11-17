'use client';

import { Button, Input, InputNumber, Select } from 'antd';
import type { ConditionGroup, ConditionItem } from '../types';

const OPS = ['=', '!=', '>', '>=', '<', '<=', 'in', 'not_in', 'contains', 'is_empty', 'not_empty'];

interface ConditionBuilderProps {
  fields: string[];
  fieldTypes?: Record<string, string>;
  value?: ConditionGroup | ConditionItem;
  onChange: (value: ConditionGroup) => void;
}

const emptyItem = (field: string): ConditionItem => ({ field, op: '=', value: '' });

export function ConditionBuilder({ fields, fieldTypes = {}, value, onChange }: ConditionBuilderProps) {
  const group: ConditionGroup = value && 'logic' in value ? value : { logic: 'and', items: value ? [value] : [emptyItem(fields[0] || '')] };
  const items = group.items.filter((item): item is ConditionItem => 'op' in item);

  const update = (nextItems: ConditionItem[], logic = group.logic) => {
    onChange({ logic, items: nextItems });
  };

  return (
    <div className="flex flex-col gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-fill-1)] p-3">
      <div className="flex items-center justify-between gap-2">
        <Select
          size="small"
          className="w-24"
          value={group.logic}
          options={[{ value: 'and', label: '并且 (AND)' }, { value: 'or', label: '或者 (OR)' }]}
          onChange={(logic) => update(items, logic)}
        />
      </div>
      {items.map((item, index) => (
        <div key={`${item.field}-${index}`} className="grid grid-cols-[1fr_88px_1fr] gap-1.5">
          <Select
            size="small"
            placeholder="字段"
            value={item.field}
            options={fields.map((field) => ({ label: field, value: field }))}
            onChange={(field) => update(items.map((current, currentIndex) => currentIndex === index ? { ...current, field } : current))}
          />
          <Select
            size="small"
            value={item.op}
            options={OPS.map((op) => ({ label: op, value: op }))}
            onChange={(op) => update(items.map((current, currentIndex) => currentIndex === index ? { ...current, op } : current))}
          />
          {fieldTypes[item.field] === 'number' && ['=', '!=', '>', '>=', '<', '<='].includes(item.op) ? <InputNumber
            size="small" className="w-full" placeholder="比较值"
            value={item.value === '' || item.value == null ? null : Number(item.value)}
            onChange={value => update(items.map((current, currentIndex) => currentIndex === index ? { ...current, value } : current))}
          /> : <Input
            size="small"
            placeholder="比较值"
            value={String(item.value ?? '')}
            onChange={(event) => update(items.map((current, currentIndex) => (
              currentIndex === index ? { ...current, value: event.target.value } : current
            )))}
          />}
        </div>
      ))}
      <Button size="small" type="dashed" onClick={() => update([...items, emptyItem(fields[0] || '')])}>
        添加条件
      </Button>
    </div>
  );
}
