import React from 'react';
import { Button, ColorPicker, Input, InputNumber, Select } from 'antd';
import { MinusCircleOutlined, PlusCircleOutlined } from '@ant-design/icons';
import type {
  SpecialMatch,
  ValueMapping,
  ValueMappingType,
} from '@/app/ops-analysis/components/ops-analysis-config-sections/types';
import { normalizeValueMappingResult } from '@/app/ops-analysis/utils/valueMapping';

interface ValueMappingsConfigSectionProps {
  t: (key: string, defaultMessage?: string) => string;
  value?: ValueMapping[];
  onChange?: (next: ValueMapping[]) => void;
  readonly?: boolean;
}

const TYPE_OPTIONS: { value: ValueMappingType; label: string }[] = [
  { value: 'value', label: '精确值' },
  { value: 'range', label: '数值区间' },
  { value: 'regex', label: '正则' },
  { value: 'special', label: '特殊值' },
];

const SPECIAL_OPTIONS: { value: SpecialMatch; label: string }[] = [
  { value: 'null', label: '空(null)' },
  { value: 'empty', label: '空字符串' },
  { value: 'nan', label: '非数值(NaN)' },
  { value: 'true', label: '真(true)' },
  { value: 'false', label: '假(false)' },
];

export const ValueMappingsConfigSection: React.FC<
  ValueMappingsConfigSectionProps
> = ({ t, value, onChange, readonly = false }) => {
  const mappings = value || [];

  const emit = (next: ValueMapping[]) => {
    if (!readonly) onChange?.(next);
  };

  const updateAt = (index: number, patch: Partial<ValueMapping>) => {
    emit(mappings.map((m, i) => (i === index ? { ...m, ...patch } : m)));
  };

  const updateResult = (
    index: number,
    patch: Partial<ValueMapping['result']>,
  ) => {
    emit(
      mappings.map((m, i) => {
        if (i !== index) return m;
        return {
          ...m,
          result: normalizeValueMappingResult({ ...m.result, ...patch }),
        };
      }),
    );
  };

  const addRule = () => {
    emit([
      ...mappings,
      {
        type: 'value',
        value: '',
        result: {},
      },
    ]);
  };

  const removeAt = (index: number) => {
    emit(mappings.filter((_, i) => i !== index));
  };

  return (
    <div className="rounded-lg border border-(--color-border-1) bg-(--color-fill-1)/40 p-2.5 space-y-2">
      {mappings.length === 0 ? (
        <div className="py-2 text-center text-xs text-(--color-text-3)">
          {t('topology.nodeConfig.valueMappingsEmpty')}
        </div>
      ) : null}

      {mappings.map((m, index) => (
        <div
          key={index}
          className="flex flex-wrap items-center gap-2 rounded-md bg-(--color-bg) px-3 py-2 border border-(--color-border-1)/60 shadow-xs"
        >
          <Select<ValueMappingType>
            value={m.type}
            onChange={(type) =>
              updateAt(index, {
                type,
                value: undefined,
                from: undefined,
                to: undefined,
                pattern: undefined,
                match: type === 'special' ? 'null' : undefined,
              })
            }
            options={TYPE_OPTIONS}
            size="small"
            className="!w-24 shrink-0"
            disabled={readonly}
          />

          {m.type === 'value' && (
            <Input
              value={m.value}
              onChange={(e) => updateAt(index, { value: e.target.value })}
              placeholder={t('common.inputMsg')}
              size="small"
              className="!w-28 shrink-0"
              disabled={readonly}
            />
          )}
          {m.type === 'range' && (
            <div className="flex items-center gap-1 shrink-0">
              <InputNumber
                value={m.from}
                onChange={(v) => updateAt(index, { from: v ?? undefined })}
                placeholder="≥"
                size="small"
                className="!w-20"
                disabled={readonly}
              />
              <InputNumber
                value={m.to}
                onChange={(v) => updateAt(index, { to: v ?? undefined })}
                placeholder="≤"
                size="small"
                className="!w-20"
                disabled={readonly}
              />
            </div>
          )}
          {m.type === 'regex' && (
            <Input
              value={m.pattern}
              onChange={(e) => updateAt(index, { pattern: e.target.value })}
              placeholder="^prod-"
              size="small"
              className="!w-28 shrink-0"
              disabled={readonly}
            />
          )}
          {m.type === 'special' && (
            <Select<SpecialMatch>
              value={m.match}
              onChange={(match) => updateAt(index, { match })}
              options={SPECIAL_OPTIONS}
              size="small"
              className="!w-28 shrink-0"
              disabled={readonly}
            />
          )}

          <span className="text-xs text-(--color-text-3) shrink-0 font-medium">→</span>

          <Input
            value={m.result?.text ?? ''}
            onChange={(e) => updateResult(index, { text: e.target.value })}
            placeholder={t('topology.nodeConfig.valueMappingsResultText')}
            size="small"
            className="!w-28 shrink-0"
            disabled={readonly}
          />

          <ColorPicker
            value={m.result?.color ?? null}
            allowClear
            onChange={(c) =>
              updateResult(index, {
                color: c.cleared ? undefined : c.toHexString(),
              })
            }
            size="small"
            showText
            disabled={readonly}
          />

          {!readonly && (
            <Button
              type="text"
              size="small"
              icon={<MinusCircleOutlined className="text-(--color-text-3) hover:text-(--color-fail)" />}
              onClick={() => removeAt(index)}
              className="ml-auto"
            />
          )}
        </div>
      ))}

      {!readonly && (
        <div className="pt-1">
          <Button
            type="dashed"
            size="small"
            block
            icon={<PlusCircleOutlined />}
            onClick={addRule}
            className="text-xs text-(--color-primary)"
          >
            {t('topology.nodeConfig.valueMappingsAdd')}
          </Button>
        </div>
      )}
    </div>
  );
};
