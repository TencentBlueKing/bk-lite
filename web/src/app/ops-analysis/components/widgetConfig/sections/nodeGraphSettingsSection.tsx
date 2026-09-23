import React from 'react';
import { Form, Select } from 'antd';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import { ConfigGroupTitle } from '../configTitles';
import { ChartRoleLabel, RefreshFieldsButton } from './chartRoleLabel';

interface NodeGraphSettingsSectionProps {
  t: (key: string) => string;
  sectionTitle?: string;
  selectedDataSource?: DatasourceItem;
  fieldOptions: Array<{ label: React.ReactNode; value: string }>;
  valueFieldOptions: Array<{ label: React.ReactNode; value: string }>;
  loadingFields?: boolean;
  onRefreshFields?: () => void;
}

export const NodeGraphSettingsSection: React.FC<NodeGraphSettingsSectionProps> = ({
  t,
  sectionTitle,
  selectedDataSource,
  fieldOptions,
  valueFieldOptions,
  loadingFields = false,
  onRefreshFields,
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

        <ConfigGroupTitle
          actions={(
            <RefreshFieldsButton
              label={t('dashboard.refreshFields')}
              loading={loadingFields}
              disabled={!selectedDataSource}
              onClick={onRefreshFields}
            />
          )}
        >
          {t('dashboard.dataFields')}
        </ConfigGroupTitle>

        <Form.Item
          label={(
            <ChartRoleLabel
              text={t('topology.nodeConfig.nodeGraphSourceField')}
              tip={t('dashboard.nodeGraphSourceFieldTip')}
            />
          )}
          name="nodeGraphSourceField"
          rules={[
            {
              required: true,
              message: t('topology.nodeConfig.nodeGraphSourceField'),
            },
          ]}
        >
          <Select
            placeholder={fieldOptions.length === 0
              ? t('topology.nodeConfig.clickRefreshToGetFields')
              : t('topology.nodeConfig.nodeGraphSourceField')}
            options={fieldOptions}
            disabled={!selectedDataSource}
            showSearch
            optionFilterProp="value"
          />
        </Form.Item>

        <Form.Item
          label={(
            <ChartRoleLabel
              text={t('topology.nodeConfig.nodeGraphTargetField')}
              tip={t('dashboard.nodeGraphTargetFieldTip')}
            />
          )}
          name="nodeGraphTargetField"
          rules={[
            {
              required: true,
              message: t('topology.nodeConfig.nodeGraphTargetField'),
            },
          ]}
        >
          <Select
            placeholder={fieldOptions.length === 0
              ? t('topology.nodeConfig.clickRefreshToGetFields')
              : t('topology.nodeConfig.nodeGraphTargetField')}
            options={fieldOptions}
            disabled={!selectedDataSource}
            showSearch
            optionFilterProp="value"
          />
        </Form.Item>

        {identityMode === 'service' ? (
          <Form.Item
            label={(
              <ChartRoleLabel
                text={t('topology.nodeConfig.nodeGraphTargetPortField')}
                tip={t('dashboard.nodeGraphTargetPortFieldTip')}
              />
            )}
            name="nodeGraphTargetPortField"
            rules={[
              {
                required: true,
                message: t('topology.nodeConfig.nodeGraphTargetPortField'),
              },
            ]}
          >
            <Select
              placeholder={fieldOptions.length === 0
                ? t('topology.nodeConfig.clickRefreshToGetFields')
                : t('topology.nodeConfig.nodeGraphTargetPortField')}
              options={fieldOptions}
              disabled={!selectedDataSource}
              showSearch
              optionFilterProp="value"
            />
          </Form.Item>
        ) : null}

        <Form.Item
          label={(
            <ChartRoleLabel
              text={t('topology.nodeConfig.nodeGraphValueField')}
              tip={t('dashboard.nodeGraphValueFieldTip')}
            />
          )}
          name="nodeGraphValueField"
          rules={[
            {
              required: true,
              message: t('topology.nodeConfig.nodeGraphValueField'),
            },
          ]}
        >
          <Select
            placeholder={valueFieldOptions.length === 0
              ? t('topology.nodeConfig.clickRefreshToGetFields')
              : t('topology.nodeConfig.nodeGraphValueField')}
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
