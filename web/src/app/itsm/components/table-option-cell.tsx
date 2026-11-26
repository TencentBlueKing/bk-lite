'use client';

import { useEffect, useEffectEvent } from 'react';
import { Select } from 'antd';
import type { FormFieldSchema } from '../types';

export interface CellOption { value: string | number; label: string }

export function TableOptionCell({ column, row, index, onChange }: {
  column: FormFieldSchema; row: Record<string, unknown>; index: number; onChange: (choice: CellOption) => void;
}) {
  const options = column.source?.options || [];
  const value = row[column.key] as CellOption['value'] | undefined;
  const first = options[0];
  const defaultFirst = !column.fetch && column.props?.defaultFirstOption === true && (value == null || value === '');
  const selectDefault = useEffectEvent((choice: CellOption) => onChange(choice));
  useEffect(() => {
    if (defaultFirst && first) selectDefault(first);
  }, [defaultFirst, first]);
  return <Select aria-label={column.label + ' ' + (index + 1)} className="w-full" options={options}
    disabled={Boolean(column.fetch)} value={value === '' ? undefined : value} showSearch optionFilterProp="label"
    placeholder={column.placeholder || '请选择'} onChange={value => {
      const option = options.find(item => item.value === value);
      if (option) onChange(option);
    }} />;
}
