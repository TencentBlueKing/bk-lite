import React from 'react';
import { MinusCircleOutlined, PlusOutlined } from '@ant-design/icons';
import { Button, Form, Input, InputNumber, Select } from 'antd';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import { ConfigSectionTitle } from '../configTitles';
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

const hasScalarField = (fields: unknown): boolean => {
  if (!Array.isArray(fields)) {
    return false;
  }
  return fields.some((item) => {
    if (!item || typeof item !== 'object') {
      return false;
    }
    return String((item as { field?: string }).field || '').trim().length > 0;
  });
};

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
  const scalarFields = Form.useWatch('topNScalarFields');
  const barMode = Form.useWatch('barMode');
  const scalarActive = hasScalarField(scalarFields);
  const absolute = barMode === 'absolute';
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

      <ConfigSectionTitle
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
      </ConfigSectionTitle>

      <div>
        <Form.Item
          label={(
            <ChartRoleLabel
              text={t('topology.nodeConfig.displayField')}
              tip={t('dashboard.topNLabelFieldTip')}
            />
          )}
          name="topNLabelField"
          rules={scalarActive
            ? undefined
            : [
              {
                required: true,
                message: t('topology.nodeConfig.selectDisplayField'),
              },
            ]}
        >
          <Select
            placeholder={placeholder}
            options={topNLabelFieldOptions}
            disabled={fieldSelectorDisabled || scalarActive}
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
          rules={scalarActive
            ? undefined
            : [
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
            disabled={fieldSelectorDisabled || scalarActive}
            showSearch
            optionFilterProp="value"
          />
        </Form.Item>

        <Form.Item
          className="!mb-2"
          label={(
            <ChartRoleLabel
              text={t('dashboard.topNScalarFields')}
              tip={t('dashboard.topNScalarFieldsTip')}
            />
          )}
        >
          <Form.List name="topNScalarFields">
            {(fields, { add, remove }) => (
              <div className="space-y-2">
                {fields.map((field) => (
                  <div
                    key={field.key}
                    className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] items-start gap-2"
                  >
                    <Form.Item name={[field.name, 'field']} className="!mb-0">
                      <Select
                        allowClear
                        disabled={fieldSelectorDisabled}
                        showSearch
                        optionFilterProp="value"
                        options={topNValueFieldOptions}
                        placeholder={t('dashboard.topNScalarField')}
                      />
                    </Form.Item>
                    <Form.Item name={[field.name, 'label']} className="!mb-0">
                      <Input
                        disabled={fieldSelectorDisabled}
                        placeholder={t('dashboard.topNScalarLabel')}
                      />
                    </Form.Item>
                    <Button
                      type="text"
                      aria-label={t('dashboard.pieScalarRemove')}
                      icon={<MinusCircleOutlined />}
                      onClick={() => remove(field.name)}
                    />
                  </div>
                ))}
                <Button
                  type="dashed"
                  block
                  icon={<PlusOutlined />}
                  disabled={fieldSelectorDisabled}
                  onClick={() => add({})}
                >
                  {t('dashboard.topNScalarFields')}
                </Button>
              </div>
            )}
          </Form.List>
        </Form.Item>

        <Form.Item
          label={(
            <ChartRoleLabel
              text={t('dashboard.topNBarMode')}
              tip={t('dashboard.topNBarModeTip')}
            />
          )}
          name="barMode"
        >
          <Select
            allowClear
            placeholder={t('dashboard.topNBarModeRelative')}
            options={[
              { label: t('dashboard.topNBarModeRelative'), value: 'relative' },
              { label: t('dashboard.topNBarModeAbsolute'), value: 'absolute' },
            ]}
          />
        </Form.Item>

        {absolute ? (
          <Form.Item
            label={(
              <ChartRoleLabel
                text={t('dashboard.topNBarMax')}
                tip={t('dashboard.topNBarMaxTip')}
              />
            )}
            name="barMax"
          >
            <InputNumber className="w-full" min={0} placeholder="100" />
          </Form.Item>
        ) : null}
      </div>
    </div>
  );
};
