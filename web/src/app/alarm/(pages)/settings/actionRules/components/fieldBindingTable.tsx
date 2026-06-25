'use client';

import React, { useCallback } from 'react';
import { Input, Table } from 'antd';
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
    (name: string, nextValue: string) => {
      const existing = getBinding(name);
      // 统一按「告警字段」解析（后端 resolve_params 在 from!=='const' 时按字段路径取值）
      const updated: ParamBinding = { ...existing, from: 'field', value: nextValue };
      const rest = value.filter((b) => b.name !== name);
      onChange?.([...rest, updated]);
    },
    [value, getBinding, onChange]
  );

  const columns = [
    {
      title: t('settings.actionBindingField'),
      dataIndex: 'label',
      key: 'label',
      width: 160,
      render: (_: unknown, record: ScriptParam) => record.label || record.name,
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
            placeholder="labels.service"
            onChange={(e) => updateBinding(record.name, e.target.value)}
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
