import React from 'react';
import { Form, Input, Select } from 'antd';
import type { OpsAnalysisWidgetSurface } from '@/app/ops-analysis/utils/chartTypeSurface';
import { ConfigSectionTitle } from '../configTitles';

interface WidgetConfigBasicFieldsProps {
  t: (key: string, defaultValue?: string) => string;
  chartType: string;
  showChartThemeMode: boolean;
  isNetworkStatusTopology: boolean;
  surface?: OpsAnalysisWidgetSurface;
}

export const WidgetConfigBasicFields: React.FC<WidgetConfigBasicFieldsProps> = ({
  t,
  showChartThemeMode,
  isNetworkStatusTopology,
  surface,
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
      <Input placeholder={t('dashboard.inputName')} />
    </Form.Item>

    {surface === 'screen' ? null : (
      <Form.Item label={t('dataSource.describe')} name="description">
        <Input.TextArea
          placeholder={t('common.inputMsg')}
          autoSize={{ minRows: 2, maxRows: 3 }}
        />
      </Form.Item>
    )}

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
