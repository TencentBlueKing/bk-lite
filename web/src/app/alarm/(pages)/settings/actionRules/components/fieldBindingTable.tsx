'use client';

import React, { useCallback } from 'react';
import { Select, Table } from 'antd';
import { useTranslation } from '@/utils/i18n';
import { ActionConfig } from '@/app/alarm/types/settings';
import { ruleList } from '@/app/alarm/constants/settings';

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

/**
 * 字段绑定表：把告警字段映射成作业脚本的参数。
 *
 * value 列从自由文本改为结构化 Select，选项与告警处理匹配规则共享同一份
 * `ruleList`（顶层 Alert 字段 + source_name + source_id 共 11 项）。
 * 后端 `action.resolver.resolve_params` 在 `from='field'` 时按 payload 路径取值，
 * 因此 ruleList 里的 name 直接可作 payload key 使用。
 *
 * `from` 字段统一写死为 'field'：UI 上不暴露常量模式，按用户当前意愿保留常量模式
 * 的能力到后端即可。
 */
const FieldBindingTable: React.FC<FieldBindingTableProps> = ({
  scriptParams,
  value = [],
  onChange,
}) => {
  const { t } = useTranslation();

  // 复用 constants/settings.ts 中的 ruleList 作为 value 选项，确保与 actionRules/components/matchRule
  // 同一 EditModal 内的"可选 Key"集合一致。本组件进一步：
  //   - 过滤 source_id（只剩 source_name，按"用 name 不用 ID"）
  //   - 把 source_name 的 verbose_name 简化为"告警源"
  const valueOptions = ruleList
    // 与 actionRules/components/matchRule 同口径：
    //   - 去掉 source_id（保留 source_name，按"用 name 不用 ID"）
    //   - 去掉 location / service（这两个字段只在 Event 模型上，Alert 模型上没有，
    //     是 event-only 的 ghost key，下拉里出现会导致 payload[key] 永远为 None）
    .filter(
      (item) =>
        item.name !== 'source_id' &&
        item.name !== 'location' &&
        item.name !== 'service'
    )
    .map((item) => ({
      label: item.name === 'source_name' ? '告警源' : item.verbose_name,
      value: item.name,
    }));

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
          <Select
            allowClear
            size="small"
            value={binding.value || undefined}
            placeholder={t('common.selectTip')}
            options={valueOptions}
            onChange={(v) => updateBinding(record.name, (v as string) ?? '')}
            style={{ minWidth: 160 }}
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
