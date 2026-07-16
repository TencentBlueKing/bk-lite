import React from 'react';
import { Form, InputNumber, Radio } from 'antd';
import type { ThresholdColorConfig } from '@/components/ops-analysis-config-sections/types';
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
    <div className="mb-6">
      <div className="mb-6">
        <div className="font-medium mb-4">{resolvedSectionTitle}</div>

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
        >
          <InputNumber style={{ width: '100%' }} />
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
        >
          <InputNumber style={{ width: '100%' }} />
        </Form.Item>

        <Form.Item
          label={t('dashboard.gaugeShape')}
          name="gaugeShape"
          initialValue="semicircle"
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

        <ValueFormatConfigSection t={t} width={240} />

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
