import React, { useEffect } from 'react';
import { Form, Select } from 'antd';
import type { NamePath } from 'antd/es/form/interface';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import {
  normalizeLineBarFieldList,
  trimLineBarField,
} from '@/app/ops-analysis/utils/lineBarFieldMapping';
import { ConfigSectionTitle } from '../configTitles';
import { ChartRoleLabel, RefreshFieldsButton } from './chartRoleLabel';

export interface ChartRoleField {
  name: NamePath;
  label: string;
  tip: string;
  required?: boolean;
  requiredMessage?: string;
  multiple?: boolean;
  /** 折线/柱状：数值只列数值列，系列排除分类和已选数值。 */
  optionScope?: 'all' | 'values' | 'series';
}

interface ChartRoleFieldsSectionProps {
  t: (key: string) => string;
  selectedDataSource?: DatasourceItem;
  options: Array<{ label: React.ReactNode; value: string }>;
  /** 数值字段选项。缺省时与 options 相同。 */
  valueOptions?: Array<{ label: React.ReactNode; value: string }>;
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
  if (chartType === 'line' || chartType === 'bar') {
    return [
      {
        name: 'dimensionField',
        label: t('dashboard.lineBarCategoryField'),
        tip: t('dashboard.lineBarCategoryFieldTip'),
        optionScope: 'all',
      },
      {
        name: 'valueFields',
        label: t('dashboard.lineBarValueFields'),
        tip: t('dashboard.lineBarValueFieldsTip'),
        multiple: true,
        optionScope: 'values',
      },
      {
        name: 'seriesField',
        label: t('dashboard.lineBarSeriesField'),
        tip: t('dashboard.lineBarSeriesFieldTip'),
        optionScope: 'series',
      },
    ];
  }
  if (chartType === 'pie') {
    return [
      {
        name: 'dimensionField',
        label: t('dashboard.dimensionField'),
        tip: t('dashboard.dimensionFieldTipPie'),
      },
      {
        name: 'valueField',
        label: t('dashboard.valueField'),
        tip: t('dashboard.valueFieldTipPie'),
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
  valueOptions,
  roles,
  loadingFields = false,
  onRefreshFields,
}) => {
  const form = Form.useFormInstance();
  const lineBar = roles.some((role) => role.optionScope === 'series');
  const dimensionValue = Form.useWatch('dimensionField', form);
  const watchedValues = Form.useWatch('valueFields', form);
  const watchedSeries = Form.useWatch('seriesField', form);
  const dimension = trimLineBarField(
    typeof dimensionValue === 'string' ? dimensionValue : undefined,
  );
  const selectedValues = normalizeLineBarFieldList(
    Array.isArray(watchedValues) ? watchedValues : [],
  );
  const selectedValueKey = selectedValues.join('\0');
  const seriesValue = trimLineBarField(
    typeof watchedSeries === 'string' ? watchedSeries : undefined,
  );
  const seriesLocked = selectedValues.length >= 2;
  const fieldSelectorDisabled = !selectedDataSource || loadingFields;
  const placeholder = options.length === 0
    ? t('topology.nodeConfig.clickRefreshToGetFields')
    : t('common.select');
  const numericOptions = valueOptions ?? options;

  useEffect(() => {
    if (!lineBar || numericOptions.length === 0 || numericOptions.length === options.length) {
      return;
    }
    const allowed = new Set(numericOptions.map((option) => String(option.value)));
    const current = normalizeLineBarFieldList(
      Array.isArray(form.getFieldValue('valueFields'))
        ? form.getFieldValue('valueFields')
        : [],
    );
    const next = current.filter((field) => allowed.has(field));
    if (next.length !== current.length) {
      form.setFieldValue('valueFields', next);
    }
  }, [form, lineBar, numericOptions, options.length]);

  useEffect(() => {
    if (!lineBar || !seriesValue) {
      return;
    }
    const values = normalizeLineBarFieldList(
      Array.isArray(form.getFieldValue('valueFields'))
        ? form.getFieldValue('valueFields')
        : [],
    );
    if (values.length >= 2 || values.includes(seriesValue) || seriesValue === dimension) {
      form.setFieldValue('seriesField', undefined);
    }
  }, [dimension, form, lineBar, selectedValueKey, seriesLocked, seriesValue]);

  return (
    <div className="mb-4">
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
      {roles.map((role) => {
        const roleOptions = role.optionScope === 'values'
          ? numericOptions
          : role.optionScope === 'series'
            ? options.filter((option) => (
              option.value !== dimension && !selectedValues.includes(String(option.value))
            ))
            : options;
        return (
          <Form.Item
            key={Array.isArray(role.name) ? role.name.join('.') : String(role.name)}
            name={role.name}
            label={<ChartRoleLabel text={role.label} tip={role.tip} />}
            rules={role.required
              ? [{ required: true, message: role.requiredMessage }]
              : undefined}
          >
            <Select
              mode={role.multiple ? 'multiple' : undefined}
              allowClear={!role.required}
              disabled={fieldSelectorDisabled || (role.optionScope === 'series' && seriesLocked)}
              optionFilterProp="value"
              options={roleOptions}
              placeholder={placeholder}
              showSearch
            />
          </Form.Item>
        );
      })}
    </div>
  );
};
