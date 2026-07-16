import React from 'react';
import { Form, Select } from 'antd';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';

interface TopNSettingsSectionProps {
  t: (key: string) => string;
  sectionTitle?: string;
  selectedDataSource?: DatasourceItem;
  topNLabelFieldOptions: Array<{ label: React.ReactNode; value: string }>;
  topNValueFieldOptions: Array<{ label: React.ReactNode; value: string }>;
}

export const TopNSettingsSection: React.FC<TopNSettingsSectionProps> = ({
  t,
  sectionTitle,
  selectedDataSource,
  topNLabelFieldOptions,
  topNValueFieldOptions,
}) => {
  const resolvedSectionTitle =
    sectionTitle || t('topology.nodeConfig.dataSettings');

  return (
    <div className="mb-6">
      <div className="mb-6">
        <div className="font-medium mb-4">{resolvedSectionTitle}</div>

        {!selectedDataSource ? (
          <div className="text-center py-4 text-gray-500">
            {t('topology.nodeConfig.selectDataSourceFirst')}
          </div>
        ) : null}

        {selectedDataSource && topNLabelFieldOptions.length === 0 ? (
          <div className="text-center py-4 text-gray-500">
            {t('topology.nodeConfig.noAvailableFields')}
          </div>
        ) : null}

        <Form.Item
          label={t('topology.nodeConfig.displayField')}
          name="topNLabelField"
          rules={[
            {
              required: true,
              message: t('topology.nodeConfig.selectDisplayField'),
            },
          ]}
        >
          <Select
            placeholder={t('topology.nodeConfig.selectDisplayField')}
            options={topNLabelFieldOptions}
            disabled={!selectedDataSource}
            showSearch
            optionFilterProp="value"
          />
        </Form.Item>

        <Form.Item
          label={t('topology.nodeConfig.valueField')}
          name="topNValueField"
          rules={[
            {
              required: true,
              message: t('topology.nodeConfig.selectValueField'),
            },
          ]}
        >
          <Select
            placeholder={t('topology.nodeConfig.selectValueField')}
            options={topNValueFieldOptions}
            disabled={!selectedDataSource}
            showSearch
            optionFilterProp="value"
          />
        </Form.Item>
      </div>
    </div>
  );
};
