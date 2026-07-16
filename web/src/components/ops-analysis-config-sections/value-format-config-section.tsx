import React from 'react';
import { Form, Input, InputNumber, Select } from 'antd';
import { getUnitCategories } from '@/components/ops-analysis-config-sections/runtime';

interface ValueFormatConfigSectionProps {
  t: (key: string, defaultMessage?: string) => string;
  readonly?: boolean;
  width?: number;
}

export const ValueFormatConfigSection: React.FC<
  ValueFormatConfigSectionProps
> = ({ t, readonly = false, width = 200 }) => {
  const numberWidth = Math.max(120, Math.round(width * 0.6));

  return (
    <>
      <Form.Item label={t('topology.nodeConfig.unit')} name="unitId">
        <Select
          allowClear
          placeholder={t('common.selectMsg')}
          disabled={readonly}
          style={{ width }}
          options={[
            { value: '', label: t('topology.nodeConfig.customSuffix') },
            ...getUnitCategories().map((cat) => ({
              label: cat.label,
              options: cat.units.map((u) => ({ value: u.id, label: u.label })),
            })),
          ]}
        />
      </Form.Item>

      <Form.Item
        noStyle
        shouldUpdate={(prev, cur) => prev.unitId !== cur.unitId}
      >
        {({ getFieldValue }) =>
          !getFieldValue('unitId') ? (
            <Form.Item
              label={t('topology.nodeConfig.customSuffix')}
              name="unit"
            >
              <Input
                placeholder={t('common.inputMsg')}
                disabled={readonly}
                style={{ width }}
              />
            </Form.Item>
          ) : null
        }
      </Form.Item>

      <Form.Item
        label={t('topology.nodeConfig.conversionFactor')}
        name="conversionFactor"
      >
        <InputNumber
          min={0}
          max={100000}
          step={0.01}
          placeholder={t('common.inputMsg')}
          disabled={readonly}
          style={{ width: numberWidth }}
        />
      </Form.Item>

      <Form.Item
        label={t('topology.nodeConfig.decimalPlaces')}
        name="decimalPlaces"
      >
        <InputNumber
          min={0}
          max={10}
          step={1}
          placeholder={t('common.inputMsg')}
          disabled={readonly}
          style={{ width: numberWidth }}
        />
      </Form.Item>
    </>
  );
};
