import React from 'react';
import { Form, Select } from 'antd';

interface TopNSettingsSectionProps {
  t: (key: string) => string;
  selectedDataSource: any;
  topNFieldOptions: Array<{ label: React.ReactNode; value: string }>;
}

export const TopNSettingsSection: React.FC<TopNSettingsSectionProps> = ({
  t,
  selectedDataSource,
  topNFieldOptions,
}) => {
  return (
    <div className="mb-6">
      <div className="mb-6">
        <div className="font-medium mb-4">{t('topology.nodeConfig.dataSettings')}</div>

        {!selectedDataSource ? (
          <div className="text-center py-4 text-gray-500">
            {t('topology.nodeConfig.selectDataSourceFirst')}
          </div>
        ) : null}

        {selectedDataSource && topNFieldOptions.length === 0 ? (
          <div className="text-center py-4 text-gray-500">
            {t('topology.nodeConfig.noAvailableFields')}
          </div>
        ) : null}

        <Form.Item
          label={t('topology.nodeConfig.displayField')}
          name="topNLabelField"
          rules={[{ required: true, message: t('topology.nodeConfig.selectDisplayField') }]}
        >
          <Select
            placeholder={t('topology.nodeConfig.selectDisplayField')}
            options={topNFieldOptions}
            disabled={!selectedDataSource}
            showSearch
            optionFilterProp="value"
          />
        </Form.Item>

        <Form.Item
          label={t('topology.nodeConfig.valueField')}
          name="topNValueField"
          rules={[{ required: true, message: t('topology.nodeConfig.selectValueField') }]}
        >
          <Select
            placeholder={t('topology.nodeConfig.selectValueField')}
            options={topNFieldOptions}
            disabled={!selectedDataSource}
            showSearch
            optionFilterProp="value"
          />
        </Form.Item>
      </div>
    </div>
  );
};
