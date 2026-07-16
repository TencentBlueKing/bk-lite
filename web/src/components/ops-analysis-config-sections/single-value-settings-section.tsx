import React from 'react';
import { Form, Switch, Tooltip } from 'antd';
import { QuestionCircleOutlined } from '@ant-design/icons';
import type { ThresholdColorConfig } from '@/components/ops-analysis-config-sections/types';
import { MetricFieldSelectorFormItem } from './metric-field-selector-form-item';
import { ThresholdColorConfigSection } from './threshold-color-config-section';
import { ValueFormatConfigSection } from './value-format-config-section';
import { ValueMappingsConfigSection } from './value-mappings-config-section';

const TooltipSwitch: React.FC<{
  checked?: boolean;
  onChange?: (checked: boolean) => void;
  disabled?: boolean;
  tooltipTitle?: string;
}> = ({ checked, onChange, disabled, tooltipTitle }) => {
  const switchEl = (
    <Switch checked={checked} onChange={onChange} disabled={disabled} />
  );
  if (tooltipTitle) {
    return (
      <Tooltip title={tooltipTitle}>
        <span className="inline-flex">{switchEl}</span>
      </Tooltip>
    );
  }
  return switchEl;
};

interface SingleValueSettingsSectionProps {
  t: (key: string) => string;
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
  compareAvailable: boolean;
  readonly?: boolean;
}

export const SingleValueSettingsSection: React.FC<
  SingleValueSettingsSectionProps
> = ({
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
  compareAvailable,
  readonly = false,
}) => {
  const resolvedSectionTitle =
    sectionTitle || t('topology.nodeConfig.dataSettings');
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
          readonly={readonly}
          validationMessage={t('topology.nodeConfig.selectAtLeastOneField')}
        />
      </div>

      <Form.Item
        label={
          <span>
            {t('dashboard.compareLabel')}
            <Tooltip title={t('dashboard.comparePreviousPeriodTip')}>
              <QuestionCircleOutlined className="ml-1 text-gray-400 cursor-help" />
            </Tooltip>
          </span>
        }
        name="compare"
        valuePropName="checked"
      >
        <TooltipSwitch
          disabled={readonly || !compareAvailable}
          tooltipTitle={
            !readonly && !compareAvailable
              ? t('dashboard.compareUnavailableTip')
              : undefined
          }
        />
      </Form.Item>

      <ValueFormatConfigSection t={t} readonly={readonly} width={200} />

      <ThresholdColorConfigSection
        t={t}
        thresholdColors={thresholdColors}
        onThresholdChange={onThresholdChange}
        onThresholdBlur={onThresholdBlur}
        onAddThreshold={onAddThreshold}
        onRemoveThreshold={onRemoveThreshold}
        readonly={readonly}
      />

      <Form.Item
        label={t('topology.nodeConfig.valueMappings')}
        name="valueMappings"
      >
        <ValueMappingsConfigSection t={t} readonly={readonly} />
      </Form.Item>
    </div>
  );
};
