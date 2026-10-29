import React from 'react';
import { Form, Input, Select } from 'antd';
import { FilterTokenInput } from '@/app/ops-analysis/components/filterTokenInput';
import type { OpsAnalysisWidgetSurface } from '@/app/ops-analysis/utils/chartTypeSurface';
import { ConfigSectionTitle } from '../configTitles';

interface WidgetConfigBasicFieldsProps {
  t: (
    key: string,
    defaultValue?: string,
    values?: Record<string, string | number>,
  ) => string;
  chartType: string;
  showChartThemeMode: boolean;
  isNetworkStatusTopology: boolean;
  surface?: OpsAnalysisWidgetSurface;
  filterTemplateTokens?: boolean;
  children?: React.ReactNode;
}

export const WidgetConfigBasicFields: React.FC<WidgetConfigBasicFieldsProps> = ({
  t,
  showChartThemeMode,
  isNetworkStatusTopology,
  surface,
  filterTemplateTokens = true,
  children,
}) => (
  <section>
    <ConfigSectionTitle>
      {t('dashboard.basicInfoSection', '基本信息')}
    </ConfigSectionTitle>

    <Form.Item
      label={t('dashboard.widgetName')}
      name="name"
      rules={[{ required: true, message: t('dashboard.inputName') }]}
    >
      {filterTemplateTokens ? (
        <FilterTokenInput t={t} placeholder={t('dashboard.inputName')} />
      ) : (
        <Input placeholder={t('dashboard.inputName')} />
      )}
    </Form.Item>

    {surface === 'screen' ? null : (
      <Form.Item label={t('dataSource.describe')} name="description">
        {filterTemplateTokens ? (
          <FilterTokenInput
            t={t}
            multiline
            placeholder={t('common.inputMsg')}
            autoSize={{ minRows: 2, maxRows: 3 }}
          />
        ) : (
          <Input.TextArea
            placeholder={t('common.inputMsg')}
            autoSize={{ minRows: 2, maxRows: 3 }}
          />
        )}
      </Form.Item>
    )}

    {children}

    {showChartThemeMode && !isNetworkStatusTopology && (
      <Form.Item
        label={t('dashboard.chartThemeMode')}
        name="chartThemeMode"
        initialValue="default"
      >
        <Select
          options={[
            {
              label: t('dashboard.chartThemeModeDefault'),
              value: 'default',
            },
            {
              label: t('dashboard.chartThemeModeScreenDark'),
              value: 'screen-dark',
            },
            {
              label: t('dashboard.chartThemeModeScreenLight'),
              value: 'screen-light',
            },
          ]}
        />
      </Form.Item>
    )}
  </section>
);
