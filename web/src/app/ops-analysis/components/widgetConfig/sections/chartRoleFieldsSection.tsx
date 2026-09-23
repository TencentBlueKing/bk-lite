import React from 'react';
import { Form, Select } from 'antd';
import type { NamePath } from 'antd/es/form/interface';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import { ConfigGroupTitle } from '../configTitles';
import { ChartRoleLabel, RefreshFieldsButton } from './chartRoleLabel';

export interface ChartRoleField {
  name: NamePath;
  label: string;
  tip: string;
  required?: boolean;
  requiredMessage?: string;
}

interface ChartRoleFieldsSectionProps {
  t: (key: string) => string;
  selectedDataSource?: DatasourceItem;
  options: Array<{ label: React.ReactNode; value: string }>;
  roles: ChartRoleField[];
  loadingFields?: boolean;
  onRefreshFields?: () => void;
}

export const buildChartRoleFields = (
  chartType: string,
  t: (key: string) => string,
  radarArrayRequired: boolean,
): ChartRoleField[] => {
  const requiredMessage = t('dashboard.chartRoleFieldsRequired');
  if (chartType === 'line' || chartType === 'bar' || chartType === 'pie') {
    const tipSuffix = chartType === 'line' ? 'Line' : chartType === 'bar' ? 'Bar' : 'Pie';
    return [
      {
        name: 'dimensionField',
        label: t('dashboard.dimensionField'),
        tip: t(`dashboard.dimensionFieldTip${tipSuffix}`),
      },
      {
        name: 'valueField',
        label: t('dashboard.valueField'),
        tip: t(`dashboard.valueFieldTip${tipSuffix}`),
      },
    ];
  }
  if (chartType === 'multiValue') {
    return [
      {
        name: 'multiValueLabelField',
        label: t('dashboard.multiValueLabelField'),
        tip: t('dashboard.multiValueLabelFieldTip'),
        required: true,
        requiredMessage,
      },
      {
        name: 'multiValueValueField',
        label: t('dashboard.multiValueValueField'),
        tip: t('dashboard.multiValueValueFieldTip'),
        required: true,
        requiredMessage,
      },
    ];
  }
  if (chartType === 'radar') {
    return [
      {
        name: ['radar', 'arrayNameField'],
        label: t('dashboard.radarArrayNameField'),
        tip: t('dashboard.radarArrayNameFieldTip'),
        required: radarArrayRequired,
        requiredMessage,
      },
      {
        name: ['radar', 'arrayValueField'],
        label: t('dashboard.radarArrayValueField'),
        tip: t('dashboard.radarArrayValueFieldTip'),
        required: radarArrayRequired,
        requiredMessage,
      },
    ];
  }
  if (chartType === 'eventTimeline') {
    const timelineRole = (
      field: string,
      labelKey: string,
      tipKey: string,
      required: boolean,
    ): ChartRoleField => ({
      name: ['eventTimeline', field],
      label: t(`dashboard.${labelKey}`),
      tip: t(`dashboard.${tipKey}`),
      required,
      requiredMessage,
    });
    return [
      timelineRole('timeField', 'eventTimelineTimeField', 'eventTimelineTimeFieldTip', true),
      timelineRole('titleField', 'eventTimelineTitleField', 'eventTimelineTitleFieldTip', true),
      timelineRole('descriptionField', 'eventTimelineDescriptionField', 'eventTimelineDescriptionFieldTip', false),
      timelineRole('categoryField', 'eventTimelineCategoryField', 'eventTimelineCategoryFieldTip', false),
      timelineRole('statusField', 'eventTimelineStatusField', 'eventTimelineStatusFieldTip', false),
      timelineRole('linkField', 'eventTimelineLinkField', 'eventTimelineLinkFieldTip', false),
    ];
  }
  return [];
};

export const chartRoleValuePaths = (
  chartType: string,
): Array<string | string[]> => {
  const configured = buildChartRoleFields(chartType, (key) => key, true);
  if (configured.length > 0) {
    return configured.map((role) => role.name);
  }
  if (chartType === 'topN') {
    return ['topNLabelField', 'topNValueField'];
  }
  if (chartType === 'nodeGraph') {
    return [
      'nodeGraphSourceField',
      'nodeGraphTargetField',
      'nodeGraphValueField',
      'nodeGraphTargetPortField',
    ];
  }
  if (chartType === 'cardList') {
    return [
      ['cardList', 'titleField'],
      ['cardList', 'descriptionField'],
      ['cardList', 'badgeField'],
      ['cardList', 'trailingPrimaryField'],
      ['cardList', 'trailingSecondaryField'],
      ['cardList', 'leading', 'field'],
    ];
  }
  return [];
};

export const ChartRoleFieldsSection: React.FC<ChartRoleFieldsSectionProps> = ({
  t,
  selectedDataSource,
  options,
  roles,
  loadingFields = false,
  onRefreshFields,
}) => {
  const fieldSelectorDisabled = !selectedDataSource || loadingFields;
  const placeholder = options.length === 0
    ? t('topology.nodeConfig.clickRefreshToGetFields')
    : t('common.select');

  return (
    <div className="mb-4">
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
      {roles.map((role) => (
        <Form.Item
          key={Array.isArray(role.name) ? role.name.join('.') : String(role.name)}
          name={role.name}
          label={<ChartRoleLabel text={role.label} tip={role.tip} />}
          rules={role.required
            ? [{ required: true, message: role.requiredMessage }]
            : undefined}
        >
          <Select
            allowClear={!role.required}
            disabled={fieldSelectorDisabled}
            optionFilterProp="value"
            options={options}
            placeholder={placeholder}
            showSearch
          />
        </Form.Item>
      ))}
    </div>
  );
};
