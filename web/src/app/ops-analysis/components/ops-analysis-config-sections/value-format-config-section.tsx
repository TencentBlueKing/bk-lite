import React from 'react';
import { Form, Input, InputNumber, Select } from 'antd';
import { getUnitCategories } from '@/app/ops-analysis/components/ops-analysis-config-sections/runtime';

interface ValueFormatConfigSectionProps {
  t: (key: string, defaultMessage?: string) => string;
  readonly?: boolean;
  width?: number;
}

export const ValueFormatConfigSection: React.FC<
  ValueFormatConfigSectionProps
> = ({ t, readonly = false }) => {
  return (
    <div className="grid grid-cols-2 gap-x-4 gap-y-4 [&_.ant-form-item]:!mb-0">
      <Form.Item
        label={t('topology.nodeConfig.conversionFactor')}
        name="conversionFactor"
        className="min-w-0"
      >
        <InputNumber
          min={0}
          max={100000}
          step={0.01}
          placeholder={t('common.inputMsg')}
          disabled={readonly}
          className="w-full"
        />
      </Form.Item>

      <Form.Item
        label={t('topology.nodeConfig.decimalPlaces')}
        name="decimalPlaces"
        className="min-w-0"
      >
        <InputNumber
          min={0}
          max={10}
          step={1}
          placeholder={t('common.inputMsg')}
          disabled={readonly}
          className="w-full"
        />
      </Form.Item>

      <Form.Item
        label={t('topology.nodeConfig.unit')}
        name="unitId"
        className="min-w-0"
      >
        <Select
          allowClear
          placeholder={t('common.selectMsg')}
          disabled={readonly}
          className="w-full"
          options={[
            { value: '', label: t('topology.nodeConfig.customSuffix') },
            ...getUnitCategories(t).map((cat) => ({
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
              className="min-w-0"
            >
              <Input
                placeholder={t('common.inputMsg')}
                disabled={readonly}
                className="w-full"
              />
            </Form.Item>
          ) : null
        }
      </Form.Item>
    </div>
  );
};
