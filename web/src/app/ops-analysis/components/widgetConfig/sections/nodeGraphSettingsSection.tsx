import React from 'react';
import { Form, Select } from 'antd';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';

interface NodeGraphSettingsSectionProps {
  t: (key: string) => string;
  sectionTitle?: string;
  selectedDataSource?: DatasourceItem;
  fieldOptions: Array<{ label: React.ReactNode; value: string }>;
  valueFieldOptions: Array<{ label: React.ReactNode; value: string }>;
}

export const NodeGraphSettingsSection: React.FC<NodeGraphSettingsSectionProps> = ({
  t,
  sectionTitle,
  selectedDataSource,
  fieldOptions,
  valueFieldOptions,
}) => {
  const identityMode = Form.useWatch('nodeGraphIdentityMode') || 'ip';
  const resolvedSectionTitle =
    sectionTitle !== undefined
      ? sectionTitle
      : t('topology.nodeConfig.dataSettings');

  return (
    <div className="mb-6">
      <div className="mb-6">
        {resolvedSectionTitle ? (
          <div className="font-medium mb-4">{resolvedSectionTitle}</div>
        ) : null}

        {!selectedDataSource ? (
          <div className="text-center py-4 text-xs text-(--color-text-3)">
            {t('topology.nodeConfig.selectDataSourceFirst')}
          </div>
        ) : null}

        {selectedDataSource && fieldOptions.length === 0 ? (
          <div className="text-center py-4 text-xs text-(--color-text-3)">
            {t('topology.nodeConfig.noAvailableFields')}
          </div>
        ) : null}

        <Form.Item
          label={t('topology.nodeConfig.nodeGraphIdentity')}
          name="nodeGraphIdentityMode"
          initialValue="ip"
          rules={[{ required: true }]}
        >
          <Select
            options={[
              {
                label: t('topology.nodeConfig.nodeGraphIdentityIp'),
                value: 'ip',
              },
              {
                label: t('topology.nodeConfig.nodeGraphIdentityService'),
                value: 'service',
              },
            ]}
          />
        </Form.Item>

        <Form.Item
          label={t('topology.nodeConfig.nodeGraphSourceField')}
          name="nodeGraphSourceField"
          rules={[
            {
              required: true,
              message: t('topology.nodeConfig.nodeGraphSourceField'),
            },
          ]}
        >
          <Select
            placeholder={t('topology.nodeConfig.nodeGraphSourceField')}
            options={fieldOptions}
            disabled={!selectedDataSource}
            showSearch
            optionFilterProp="value"
          />
        </Form.Item>

        <Form.Item
          label={t('topology.nodeConfig.nodeGraphTargetField')}
          name="nodeGraphTargetField"
          rules={[
            {
              required: true,
              message: t('topology.nodeConfig.nodeGraphTargetField'),
            },
          ]}
        >
          <Select
            placeholder={t('topology.nodeConfig.nodeGraphTargetField')}
            options={fieldOptions}
            disabled={!selectedDataSource}
            showSearch
            optionFilterProp="value"
          />
        </Form.Item>

        {identityMode === 'service' ? (
          <Form.Item
            label={t('topology.nodeConfig.nodeGraphTargetPortField')}
            name="nodeGraphTargetPortField"
            rules={[
              {
                required: true,
                message: t('topology.nodeConfig.nodeGraphTargetPortField'),
              },
            ]}
          >
            <Select
              placeholder={t('topology.nodeConfig.nodeGraphTargetPortField')}
              options={fieldOptions}
              disabled={!selectedDataSource}
              showSearch
              optionFilterProp="value"
            />
          </Form.Item>
        ) : null}

        <Form.Item
          label={t('topology.nodeConfig.nodeGraphValueField')}
          name="nodeGraphValueField"
          rules={[
            {
              required: true,
              message: t('topology.nodeConfig.nodeGraphValueField'),
            },
          ]}
        >
          <Select
            placeholder={t('topology.nodeConfig.nodeGraphValueField')}
            options={valueFieldOptions}
            disabled={!selectedDataSource}
            showSearch
            optionFilterProp="value"
          />
        </Form.Item>
      </div>
    </div>
  );
};
