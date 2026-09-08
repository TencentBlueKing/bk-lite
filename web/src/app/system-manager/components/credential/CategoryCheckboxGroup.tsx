'use client';

import React from 'react';
import { Checkbox } from 'antd';
import { CREDENTIAL_CATEGORIES, CREDENTIAL_CATEGORY_ZH_LABELS } from '@/components/credential-picker/types';

interface CategoryCheckboxGroupProps {
  disabled?: boolean;
  layout?: 'grid' | 'inline' | 'boxed';
  value?: string[];
  onChange?: (value: string[]) => void;
}

const CategoryCheckboxGroup: React.FC<CategoryCheckboxGroupProps> = ({
  disabled,
  layout = 'grid',
  value,
  onChange,
}) => {
  const items = CREDENTIAL_CATEGORIES.map((id) => (
    <Checkbox key={id} value={id} className="!mr-0">
      <span className="text-[13px] text-[var(--color-text-1)]">
        {CREDENTIAL_CATEGORY_ZH_LABELS[id]}（{id}）
      </span>
    </Checkbox>
  ));
  if (layout === 'inline' || layout === 'boxed') {
    return (
      <Checkbox.Group disabled={disabled} value={value} onChange={onChange} className="w-full">
        <div
          className={
            layout === 'boxed'
              ? 'flex flex-wrap gap-x-[18px] gap-y-2 rounded-[4px] border border-[var(--color-border)] bg-[var(--color-bg-container)] px-3 py-2.5'
              : 'flex flex-wrap gap-x-4 gap-y-2'
          }
        >
          {items}
        </div>
      </Checkbox.Group>
    );
  }
  return (
    <Checkbox.Group disabled={disabled} value={value} onChange={onChange} className="w-full rounded-md border border-[var(--color-border)] bg-[var(--color-bg)] p-3">
      <div className="grid grid-cols-2 gap-x-6 gap-y-2">{items}</div>
    </Checkbox.Group>
  );
};

export default CategoryCheckboxGroup;
