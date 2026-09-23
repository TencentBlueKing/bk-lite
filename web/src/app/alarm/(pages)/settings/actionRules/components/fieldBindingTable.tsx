'use client';

import React, { useCallback } from 'react';
import { Input, Select, Switch, Table, Tooltip } from 'antd';
import { QuestionCircleOutlined } from '@ant-design/icons';
import { useTranslation } from '@/utils/i18n';
import { ACTION_TRIGGER_EVENTS, ruleList } from '@/app/alarm/constants/settings';
import {
  ParamBinding,
  ScriptParam,
  TRIGGER_EVENT_FIELD,
  plainScriptDefault,
} from '@/app/alarm/utils/actionParamBindings';

export type { ScriptParam };

interface FieldBindingTableProps {
  scriptParams: ScriptParam[];
  value?: ParamBinding[];
  onChange?: (bindings: ParamBinding[]) => void;
}

/**
 * 脚本参数绑定表：每行一个脚本参数，可选手填常量或从告警字段取值。
 *
 * 变量列选项与告警处理匹配规则共用 `ruleList`，并额外提供 `alert_id`
 * 与触发事件类型 `trigger_event`（不在 ruleList 内）。过滤 source_id / location / service。
 */
const alertFieldOptions = [
  { label: '告警ID', value: 'alert_id' },
  ...ruleList
    .filter(
      (item) =>
        item.name !== 'source_id' &&
        item.name !== 'location' &&
        item.name !== 'service'
    )
    .map((item) => ({
      label: item.name === 'source_name' ? '集成源' : item.verbose_name,
      value: item.name,
    })),
];

const FieldBindingTable: React.FC<FieldBindingTableProps> = ({
  scriptParams,
  value = [],
  onChange,
}) => {
  const { t } = useTranslation();

  const getBinding = useCallback(
    (name: string): ParamBinding =>
      value.find((b) => b.name === name) ?? {
        name,
        from: 'const',
        value: '',
        allow_adjust: false,
      },
    [value]
  );

  const updateBinding = useCallback(
    (name: string, patch: Partial<Omit<ParamBinding, 'name'>>) => {
      const existing = getBinding(name);
      const from = patch.from ?? existing.from;
      const nextValue = patch.value !== undefined ? patch.value : existing.value;
      const updated: ParamBinding =
        from === 'field'
          ? { name, from: 'field', value: nextValue }
          : {
            name,
            from: 'const',
            value: nextValue,
            allow_adjust: (patch.allow_adjust ?? existing.allow_adjust) === true,
          };
      const hasExisting = value.some((b) => b.name === name);
      onChange?.(
        hasExisting
          ? value.map((b) => (b.name === name ? updated : b))
          : [...value, updated]
      );
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
      title: t('settings.actionParamFrom'),
      key: 'from',
      width: 140,
      render: (_: unknown, record: ScriptParam) => {
        const binding = getBinding(record.name);
        return (
          <Select
            size="small"
            value={binding.from}
            options={[
              { label: t('settings.actionParamConst'), value: 'const' },
              { label: t('settings.actionParamVariable'), value: 'field' },
            ]}
            onChange={(from: ParamBinding['from']) => {
              if (from === 'const') {
                updateBinding(record.name, {
                  from: 'const',
                  value: plainScriptDefault(record),
                  allow_adjust: false,
                });
                return;
              }
              updateBinding(record.name, { from: 'field', value: '' });
            }}
            style={{ minWidth: 160 }}
          />
        );
      },
    },
    {
      title: t('settings.actionParamValue'),
      key: 'value',
      render: (_: unknown, record: ScriptParam) => {
        const binding = getBinding(record.name);
        if (binding.from === 'const') {
          return (
            <Input
              size="small"
              value={binding.value}
              placeholder={t('common.inputTip')}
              onChange={(e) =>
                updateBinding(record.name, {
                  from: 'const',
                  value: e.target.value,
                })
              }
              style={{ minWidth: 160 }}
            />
          );
        }
        return (
          <div className="flex items-center gap-1">
            <Select
              allowClear
              size="small"
              value={binding.value || undefined}
              placeholder={t('common.selectTip')}
              options={[
                {
                  label: t('settings.actionParamTriggerEvent'),
                  value: TRIGGER_EVENT_FIELD,
                },
                ...alertFieldOptions,
              ]}
              onChange={(v) =>
                updateBinding(record.name, {
                  from: 'field',
                  value: (v as string) ?? '',
                })
              }
              style={{ minWidth: 160 }}
            />
            <Tooltip
              title={
                <div>
                  <div>{t('settings.actionParamTriggerEventTip')}</div>
                  {ACTION_TRIGGER_EVENTS.map(({ value, label }) => (
                    <div key={value}>{`${label} → ${value}`}</div>
                  ))}
                  <div>{t('settings.actionParamTriggerEventManual')}</div>
                </div>
              }
            >
              <QuestionCircleOutlined className="text-[var(--color-text-3)]" />
            </Tooltip>
          </div>
        );
      },
    },
    {
      title: t('settings.actionParamAllowAdjust'),
      key: 'allow_adjust',
      width: 120,
      render: (_: unknown, record: ScriptParam) => {
        const binding = getBinding(record.name);
        if (binding.from !== 'const') {
          return null;
        }
        return (
          <Switch
            size="small"
            checked={binding.allow_adjust === true}
            onChange={(checked) =>
              updateBinding(record.name, {
                from: 'const',
                allow_adjust: checked,
              })
            }
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
