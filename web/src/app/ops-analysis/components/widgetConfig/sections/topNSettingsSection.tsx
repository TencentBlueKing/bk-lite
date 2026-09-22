import React from 'react';
import { Button, Form, Select } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';

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

  const refreshFieldsButton = (
    <Button
      type="text"
      size="small"
      icon={<ReloadOutlined aria-hidden />}
      onClick={onRefreshFields}
      loading={loadingFields}
      disabled={!selectedDataSource}
      className="h-6 px-1.5 text-xs text-(--color-text-3) hover:text-(--color-primary)"
    >
      {t('dashboard.refreshFields')}
    </Button>
  );

  return (
    <div className="space-y-4">
      {resolvedSectionTitle ? (
        <div className="flex items-center gap-2 mb-2">
          <span className="text-[13px] font-semibold text-(--color-text-2)">
            {resolvedSectionTitle}
          </span>
        </div>
      ) : null}

      <div className="relative">
        <div className="absolute right-0 top-0 z-10">{refreshFieldsButton}</div>

        <Form.Item
          label={t('topology.nodeConfig.displayField')}
          name="topNLabelField"
          className="[&_.ant-form-item-label]:pr-24"
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
            disabled={fieldSelectorDisabled}
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
            disabled={fieldSelectorDisabled}
            showSearch
            optionFilterProp="value"
          />
        </Form.Item>
      </div>
    </div>
  );
};
