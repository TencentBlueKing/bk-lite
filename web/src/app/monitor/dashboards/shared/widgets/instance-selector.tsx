'use client';

import React from 'react';
import { Select } from 'antd';

export interface InstanceSelectorOption {
  label: string;
  value: string;
  searchTokens?: string[];
  ip?: string;
  port?: string;
}

const instanceEndpoint = (ip?: string, port?: string) => {
  const host = String(ip ?? '').trim();
  const service = String(port ?? '').trim();
  if (host && service) return `${host}:${service}`;
  return host || service;
};

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
  /** 实例选择：最小 320、最大 480，下拉不跟框宽，选项换行并带地址行。 */
  wide?: boolean;
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
  wide = false,
  styles
}: InstanceSelectorProps) {
  const selected = options.find((item) => item.value === value);
  const selectedLabel = selected?.label || title || '';
  return (
    <div className={styles.instanceSelectorField}>
      {label ? <span className={styles.instanceSelectorLabel}>{label}</span> : null}
      <Select
        className={styles.inlineInstanceSelector}
        style={wide ? { width: 360, minWidth: 320, maxWidth: 480 } : undefined}
        value={value}
        loading={loading}
        options={options as { label: string; value: string }[]}
        onChange={onChange}
        placeholder={placeholder}
        title={wide ? selectedLabel : title}
        showSearch
        optionFilterProp="label"
        optionLabelProp="label"
        popupMatchSelectWidth={wide ? false : popupWidth}
        styles={wide ? { popup: { root: { minWidth: 320 } } } : undefined}
        optionRender={wide ? (option) => {
          const data = option.data as InstanceSelectorOption;
          const endpoint = instanceEndpoint(data.ip, data.port);
          return (
            <span className="block whitespace-normal break-words py-0.5">
              <span className="block text-[13px] text-[var(--color-text-1)]">{option.label}</span>
              {endpoint ? (
                <span className="block text-[12px] leading-4 text-[var(--color-text-3)]">{endpoint}</span>
              ) : null}
            </span>
          );
        } : undefined}
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
