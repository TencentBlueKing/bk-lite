import React from 'react';
import { Form, Select } from 'antd';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import { ConfigGroupTitle } from '../configTitles';
import { ChartRoleLabel, RefreshFieldsButton } from './chartRoleLabel';

interface TopNSettingsSectionProps {
  t: (key: string) => string;
  sectionTitle?: string;
  selectedDataSource?: DatasourceItem;
  topNLabelFieldOptions: Array<{ label: React.ReactNode; value: string }>;
  topNValueFieldOptions: Array<{ label: React.ReactNode; value: string }>;
  loadingFields?: boolean;
  onRefreshFields?: () => void;
}

export const TopNSettingsSection: React.FC<TopNSettingsSectionProps> = ({
  t,
  sectionTitle,
  selectedDataSource,
  topNLabelFieldOptions,
  topNValueFieldOptions,
  loadingFields = false,
  onRefreshFields,
}) => {
  const resolvedSectionTitle =
    sectionTitle !== undefined ? sectionTitle : t('topology.nodeConfig.dataSettings');
  const fieldSelectorDisabled = !selectedDataSource || loadingFields;
  const placeholder = topNLabelFieldOptions.length === 0
    ? t('topology.nodeConfig.clickRefreshToGetFields')
    : t('topology.nodeConfig.selectDisplayField');

  return (
    <div>
      {resolvedSectionTitle ? (
        <div className="mb-2 flex items-center gap-2">
          <span className="text-[13px] font-semibold text-(--color-text-2)">
            {resolvedSectionTitle}
          </span>
        </div>
      ) : null}

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

      <div>
        <Form.Item
          label={(
            <ChartRoleLabel
              text={t('topology.nodeConfig.displayField')}
              tip={t('dashboard.topNLabelFieldTip')}
            />
          )}
          name="topNLabelField"
          rules={[
            {
              required: true,
              message: t('topology.nodeConfig.selectDisplayField'),
            },
          ]}
        >
          <Select
            placeholder={placeholder}
            options={topNLabelFieldOptions}
            disabled={fieldSelectorDisabled}
            showSearch
            optionFilterProp="value"
          />
        </Form.Item>

        <Form.Item
          label={(
            <ChartRoleLabel
              text={t('topology.nodeConfig.valueField')}
              tip={t('dashboard.topNValueFieldTip')}
            />
          )}
          name="topNValueField"
          rules={[
            {
              required: true,
              message: t('topology.nodeConfig.selectValueField'),
            },
          ]}
        >
          <Select
            placeholder={topNValueFieldOptions.length === 0
              ? t('topology.nodeConfig.clickRefreshToGetFields')
              : t('topology.nodeConfig.selectValueField')}
            options={topNValueFieldOptions}
            disabled={fieldSelectorDisabled}
            showSearch
            optionFilterProp="value"
          />
        </Form.Item>
      </div>
    </div>
  );
};
