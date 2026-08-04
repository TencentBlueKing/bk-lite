'use client';

import React from 'react';
import { Select } from 'antd';

export interface InstanceSelectorOption {
  label: string;
  value: string;
  searchTokens?: string[];
}

export interface InstanceSelectorStyles {
  readonly inlineInstanceSelector?: string;
  readonly instanceSelectorLabel?: string;
  readonly instanceSelectorField?: string;
  readonly [key: string]: string | undefined;
}

export interface InstanceSelectorProps {
  value?: string;
  options: readonly { label: string; value: string; searchTokens?: string[] }[];
  onChange: (value: string) => void;
  loading?: boolean;
  placeholder?: string;
  title?: string;
  label?: string;
  popupWidth?: number;
  styles: InstanceSelectorStyles;
}

export function InstanceSelector({
  value,
  options,
  onChange,
  loading = false,
  placeholder = '选择实例',
  title,
  label = '实例',
  popupWidth = 360,
  styles
}: InstanceSelectorProps) {
  return (
    <div className={styles.instanceSelectorField}>
      {label ? <span className={styles.instanceSelectorLabel}>{label}</span> : null}
      <Select
        className={styles.inlineInstanceSelector}
        value={value}
        loading={loading}
        options={options as { label: string; value: string }[]}
        onChange={onChange}
        placeholder={placeholder}
        title={title}
        showSearch
        optionFilterProp="label"
        optionLabelProp="label"
        popupMatchSelectWidth={popupWidth}
        filterOption={(input, option) => {
          const searchText = input.trim().toLowerCase();
          if (!searchText) return true;
          const tokens = (option as { searchTokens?: string[] } | undefined)?.searchTokens || [];
          return tokens.some((token) => token.toLowerCase().includes(searchText));
        }}
        variant="borderless"
      />
    </div>
  );
}
