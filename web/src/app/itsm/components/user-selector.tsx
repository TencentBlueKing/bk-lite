'use client';

import { Select } from 'antd';
import { useState } from 'react';

interface UserSelectorProps {
  value?: string[];
  onChange?: (value: string[]) => void;
}

export function UserSelector({ value, onChange }: UserSelectorProps) {
  const [options, setOptions] = useState<Array<{ label: string; value: string }>>([]);
  return (
    <Select
      mode="multiple"
      value={value}
      options={options}
      onSearch={(text) => setOptions(text ? [{ label: text, value: text }] : [])}
      onChange={onChange}
      filterOption={false}
    />
  );
}
