'use client';

import React, { useMemo, useState } from 'react';
import { Input, Modal, Select, Table } from 'antd';
import type { InputOption } from '@/app/ops-analysis/types/dataSource';
import { useTranslation } from '@/utils/i18n';

interface ParamInputTableSelectProps {
  options: InputOption[];
  value?: string | number | Array<string | number>;
  onChange?: (value: string | number | Array<string | number> | null) => void;
  disabled?: boolean;
  placeholder?: string;
  allowClear?: boolean;
  multiple?: boolean;
  maxCount?: number;
  style?: React.CSSProperties;
}

const toKeyList = (value?: string | number | Array<string | number>): string[] => {
  if (Array.isArray(value)) {
    return value.map((item) => String(item));
  }
  if (value === undefined || value === null || value === '') {
    return [];
  }
  return [String(value)];
};

const ParamInputTableSelect: React.FC<ParamInputTableSelectProps> = ({
  options,
  value,
  onChange,
  disabled,
  placeholder,
  allowClear = true,
  multiple = false,
  maxCount,
  style,
}) => {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [keyword, setKeyword] = useState('');
  const [draftKeys, setDraftKeys] = useState<string[]>([]);

  const optionByKey = useMemo(
    () => new Map(options.map((item) => [String(item.value), item])),
    [options],
  );

  const filteredOptions = useMemo(() => {
    const query = keyword.trim().toLowerCase();
    if (!query) {
      return options;
    }
    return options.filter((item) => {
      const label = String(item.label ?? '').toLowerCase();
      const optionValue = String(item.value).toLowerCase();
      return label.includes(query) || optionValue.includes(query);
    });
  }, [keyword, options]);

  const commitKeys = (keys: string[]) => {
    const nextValues = keys
      .map((key) => optionByKey.get(key)?.value)
      .filter((item): item is string | number => item !== undefined);
    if (multiple) {
      onChange?.(nextValues);
      return;
    }
    onChange?.(nextValues[0] ?? null);
  };

  const openModal = () => {
    if (disabled) {
      return;
    }
    setKeyword('');
    setDraftKeys(toKeyList(value));
    setOpen(true);
  };

  const handleOk = () => {
    commitKeys(draftKeys);
    setOpen(false);
  };

  const handleSelectChange = (nextValue: string | number | Array<string | number> | null) => {
    onChange?.(nextValue ?? null);
  };

  return (
    <>
      <Select
        value={value}
        disabled={disabled}
        placeholder={placeholder}
        allowClear={allowClear}
        mode={multiple ? 'multiple' : undefined}
        maxCount={multiple ? maxCount : undefined}
        maxTagCount={multiple ? 0 : undefined}
        maxTagPlaceholder={
          multiple
            ? () => t('paramInput.tableSelect.selected', undefined, {
              count: toKeyList(value).length,
            })
            : undefined
        }
        open={false}
        showSearch={false}
        style={{ width: '100%', ...style }}
        options={options}
        onOpenChange={(nextOpen) => {
          if (nextOpen) {
            openModal();
          }
        }}
        onChange={(nextValue) => handleSelectChange(nextValue ?? null)}
      />
      <Modal
        title={placeholder || t('paramInput.tableSelect.title')}
        open={open}
        onCancel={() => setOpen(false)}
        onOk={handleOk}
        okText={t('common.confirm')}
        cancelText={t('common.cancel')}
        width={640}
        destroyOnHidden
        centered
      >
        <div className="mb-3 flex items-center justify-between gap-3">
          <Input.Search
            allowClear
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
            placeholder={t('paramInput.tableSelect.search')}
            className="max-w-xs"
          />
          <span className="shrink-0 text-xs text-[var(--color-text-3)]">
            {t('paramInput.tableSelect.selected', undefined, { count: draftKeys.length })}
          </span>
        </div>
        <Table
          size="small"
          rowKey={(record) => String(record.value)}
          pagination={filteredOptions.length > 8 ? { pageSize: 8, size: 'small' } : false}
          dataSource={filteredOptions}
          columns={[
            {
              title: t('paramInput.tableSelect.label'),
              dataIndex: 'label',
              ellipsis: true,
            },
            {
              title: t('paramInput.tableSelect.value'),
              dataIndex: 'value',
              width: 220,
              ellipsis: true,
              render: (cell: string | number) => String(cell),
            },
          ]}
          rowSelection={{
            type: multiple ? 'checkbox' : 'radio',
            selectedRowKeys: draftKeys,
            preserveSelectedRowKeys: true,
            onChange: (keys) => {
              const nextKeys = keys.map((key) => String(key));
              if (multiple && typeof maxCount === 'number' && nextKeys.length > maxCount) {
                setDraftKeys(nextKeys.slice(0, maxCount));
                return;
              }
              setDraftKeys(nextKeys);
            },
            getCheckboxProps: (record) => {
              if (!multiple || typeof maxCount !== 'number') {
                return {};
              }
              const key = String(record.value);
              const reached = draftKeys.length >= maxCount && !draftKeys.includes(key);
              return { disabled: reached };
            },
          }}
        />
      </Modal>
    </>
  );
};

export default ParamInputTableSelect;
