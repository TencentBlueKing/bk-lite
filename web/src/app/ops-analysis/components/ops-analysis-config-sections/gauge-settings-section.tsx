import React from 'react';
import { Form, InputNumber, Radio } from 'antd';
import type { ThresholdColorConfig } from '@/app/ops-analysis/components/ops-analysis-config-sections/types';
import { MetricFieldSelectorFormItem } from './metric-field-selector-form-item';
import { ThresholdColorConfigSection } from './threshold-color-config-section';
import { ValueFormatConfigSection } from './value-format-config-section';
import { ValueMappingsConfigSection } from './value-mappings-config-section';

interface GaugeSettingsSectionProps {
  t: (key: string, defaultMessage?: string) => string;
  sectionTitle?: string;
  selectedDataSource: any;
  singleValueTreeData: any[];
  selectedFields: string[];
  loadingSingleValueData: boolean;
  thresholdColors: ThresholdColorConfig[];
  onFetchSingleValueDataFields: () => void;
  onSingleValueFieldChange: (checkedKeys: any) => void;
  onThresholdChange: (
    index: number,
    field: 'value' | 'color',
    value: string | number,
  ) => void;
  onThresholdBlur: (index: number, value: number | null) => void;
  onAddThreshold: (afterIndex?: number) => void;
  onRemoveThreshold: (index: number) => void;
}

export const GaugeSettingsSection: React.FC<GaugeSettingsSectionProps> = ({
  t,
  sectionTitle,
  selectedDataSource,
  singleValueTreeData,
  selectedFields,
  loadingSingleValueData,
  thresholdColors,
  onFetchSingleValueDataFields,
  onSingleValueFieldChange,
  onThresholdChange,
  onThresholdBlur,
  onAddThreshold,
  onRemoveThreshold,
}) => {
  const resolvedSectionTitle = sectionTitle || t('dashboard.gaugeSettings');
  return (
    <div className="mb-6 space-y-4">
      <div>
        <div className="flex items-center gap-2 mb-4 pb-2 border-b border-(--color-border-1)">
          <span className="w-1 h-3.5 bg-(--color-primary) rounded-full shrink-0" />
          <span className="text-[14px] font-semibold text-(--color-text-1)">
            {resolvedSectionTitle}
          </span>
        </div>

        <MetricFieldSelectorFormItem
          t={t}
          selectedDataSource={selectedDataSource}
          singleValueTreeData={singleValueTreeData}
          selectedField={selectedFields[0]}
          loadingSingleValueData={loadingSingleValueData}
          onFetchSingleValueDataFields={onFetchSingleValueDataFields}
          onSingleValueFieldChange={onSingleValueFieldChange}
          validationMessage={t('topology.nodeConfig.selectDisplayField')}
        />

        <div className="grid grid-cols-2 gap-4">
          <Form.Item
            label={t('dashboard.gaugeMin')}
            name="gaugeMin"
            rules={[
              {
                required: true,
                message: t('common.inputMsg'),
              },
            ]}
            initialValue={0}
            className="!mb-0"
          >
            <InputNumber className="w-full" />
          </Form.Item>

          <Form.Item
            label={t('dashboard.gaugeMax')}
            name="gaugeMax"
            rules={[
              {
                required: true,
                message: t('common.inputMsg'),
              },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  const min = Number(getFieldValue('gaugeMin'));
                  const max = Number(value);
                  if (
                    !Number.isFinite(min) ||
                    !Number.isFinite(max) ||
                    max <= min
                  ) {
                    return Promise.reject(
                      new Error(t('dashboard.gaugeMaxMustGreaterMin')),
                    );
                  }
                  return Promise.resolve();
                },
              }),
            ]}
            initialValue={100}
            className="!mb-0"
          >
            <InputNumber className="w-full" />
          </Form.Item>
        </div>

        <Form.Item
          label={t('dashboard.gaugeShape')}
          name="gaugeShape"
          initialValue="semicircle"
          className="mt-4"
        >
          <Radio.Group>
            <Radio.Button value="semicircle">
              {t('dashboard.gaugeShapeSemicircle')}
            </Radio.Button>
            <Radio.Button value="circle">
              {t('dashboard.gaugeShapeCircle')}
            </Radio.Button>
          </Radio.Group>
        </Form.Item>

        <ValueFormatConfigSection t={t} />

        <ThresholdColorConfigSection
          t={t}
          thresholdColors={thresholdColors}
          onThresholdChange={onThresholdChange}
          onThresholdBlur={onThresholdBlur}
          onAddThreshold={onAddThreshold}
          onRemoveThreshold={onRemoveThreshold}
        />

        <Form.Item
          label={t('topology.nodeConfig.valueMappings')}
          name="valueMappings"
        >
          <ValueMappingsConfigSection t={t} />
        </Form.Item>
      </div>
    </div>
  );
};
