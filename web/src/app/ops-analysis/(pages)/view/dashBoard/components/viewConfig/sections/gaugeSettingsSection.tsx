import React from 'react';
import { Form, Input, InputNumber, Radio, Select } from 'antd';
import type { ThresholdColorConfig } from '@/app/ops-analysis/utils/thresholdUtils';
import { ThresholdColorConfigSection } from '@/app/ops-analysis/components/thresholdColorConfigSection';

interface GaugeSettingsSectionProps {
  t: (key: string, defaultMessage?: string) => string;
  sectionTitle?: string;
  selectedDataSource: any;
  fieldOptions: Array<{ label: React.ReactNode; value: string }>;
  thresholdColors: ThresholdColorConfig[];
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
  fieldOptions,
  thresholdColors,
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

        <Form.Item
          label={t('topology.nodeConfig.displayField')}
          name="selectedFields"
          rules={[
            {
              required: true,
              validator: (_, value) => {
                if (!value || value.length === 0) {
                  return Promise.reject(
                    new Error(t('topology.nodeConfig.selectDisplayField')),
                  );
                }
                return Promise.resolve();
              },
            },
          ]}
        >
          <Select
            mode="multiple"
            maxCount={1}
            placeholder={t('topology.nodeConfig.selectDisplayField')}
            options={fieldOptions}
            disabled={!selectedDataSource}
            showSearch
            optionFilterProp="label"
          />
        </Form.Item>

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

        <Form.Item label={t('topology.nodeConfig.unit')} name="unit">
          <Input
            placeholder={t('common.inputMsg')}
            style={{ width: '240px' }}
          />
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
            style={{ width: '140px' }}
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
            style={{ width: '140px' }}
          />
        </Form.Item>

        <ThresholdColorConfigSection
          t={t}
          thresholdColors={thresholdColors}
          onThresholdChange={onThresholdChange}
          onThresholdBlur={onThresholdBlur}
          onAddThreshold={onAddThreshold}
          onRemoveThreshold={onRemoveThreshold}
        />
      </div>
    </div>
  );
};
