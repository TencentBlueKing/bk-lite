'use client';

import React, { useCallback } from 'react';
import { Input, Select, Table } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { ActionConfig } from '@/app/alarm/types/settings';

export interface ScriptParam {
  name: string;
  label?: string;
  default?: string;
}

type ParamBinding = ActionConfig['param_bindings'][number];

interface FieldBindingTableProps {
  scriptParams: ScriptParam[];
  value?: ActionConfig['param_bindings'];
  onChange?: (bindings: ActionConfig['param_bindings']) => void;
}

const FROM_OPTIONS = (t: (key: string) => string) => [
  { value: 'field', label: t('settings.actionParamField') },
  { value: 'const', label: t('settings.actionParamConst') },
];

const FieldBindingTable: React.FC<FieldBindingTableProps> = ({
  scriptParams,
  value = [],
  onChange,
}) => {
  const { t } = useTranslation();

  const getBinding = useCallback(
    (name: string): ParamBinding =>
      value.find((b) => b.name === name) ?? { name, from: 'field', value: '' },
    [value]
  );

  const updateBinding = useCallback(
    (name: string, patch: Partial<Omit<ParamBinding, 'name'>>) => {
      const existing = getBinding(name);
      const updated: ParamBinding = { ...existing, ...patch };
      const rest = value.filter((b) => b.name !== name);
      onChange?.([...rest, updated]);
    },
    [value, getBinding, onChange]
  );

  const columns = [
    {
      title: t('settings.actionSelectJob'),
      dataIndex: 'label',
      key: 'label',
      width: 140,
      render: (_: unknown, record: ScriptParam) => record.label || record.name,
    },
    {
      title: t('settings.actionParamFrom'),
      key: 'from',
      width: 130,
      render: (_: unknown, record: ScriptParam) => {
        const binding = getBinding(record.name);
        return (
          <Select
            size="small"
            value={binding.from}
            options={FROM_OPTIONS(t)}
            style={{ width: '100%' }}
            onChange={(v: 'field' | 'const') =>
              updateBinding(record.name, { from: v, value: '' })
            }
          />
        );
      },
    },
    {
      title: t('common.value'),
      key: 'value',
      render: (_: unknown, record: ScriptParam) => {
        const binding = getBinding(record.name);
        return (
          <Input
            size="small"
            value={binding.value}
            placeholder={
              binding.from === 'field' ? 'labels.service' : t('common.inputTip')
            }
            onChange={(e) => updateBinding(record.name, { value: e.target.value })}
          />
        );
      },
    },
  ];

  return (
    <Table<ScriptParam>
      size="small"
      rowKey="name"
      dataSource={scriptParams}
      columns={columns}
      pagination={false}
      bordered
    />
  );
};

export default FieldBindingTable;
