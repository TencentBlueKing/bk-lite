// @vitest-environment jsdom

import React from 'react';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

vi.mock('@/app/ops-analysis/context/common', () => ({
  useOpsAnalysis: () => ({ canvasDataSourceLookupStatus: 'ready', dataSources: [] }),
}));

vi.mock('@/app/ops-analysis/api/dataSource', async () => {
  const actual = await vi.importActual<typeof import('@/app/ops-analysis/api/dataSource')>(
    '@/app/ops-analysis/api/dataSource',
  );
  return {
    ...actual,
    useDataSourceApi: () => ({
      getSourceDataByApiId: vi.fn(),
      getDataSourceList: vi.fn(),
    }),
  };
});

vi.mock('@/app/ops-analysis/hooks/useParamInputOptions', () => ({
  useParamInputOptions: () => ({ status: 'idle', options: [] }),
}));

vi.mock('@/app/ops-analysis/utils/compareQuery', () => ({
  fetchCompareData: vi.fn(),
  validateGaugeData: vi.fn(),
}));

vi.mock('@/app/ops-analysis/context/dataVariableRuntime', () => ({
  useDataVariableRuntime: () => ({
    ready: true,
    columns: {
      dv_region: { status: 'blocked', reason: 'nodata' },
    },
  }),
}));

vi.mock('@/app/ops-analysis/components/widgetRegistry', () => ({
  getWidgetComponent: () => function FakeChart() {
    return <div data-testid="chart-renderer" />;
  },
}));

import WidgetWrapper from '../widgetDataRenderer';

const datasource: DatasourceItem = {
  id: 140,
  created_at: '',
  updated_at: '',
  created_by: '',
  updated_by: '',
  domain: '',
  updated_by_domain: '',
  name: 'CMDB 资源监控告警分布',
  source_type: 'nats',
  desc: '',
  params: [
    {
      name: 'uuids',
      alias_name: '实例标识',
      required: true,
      value: { dataVariableId: 'dv_region' },
    },
  ],
  chart_type: ['cardList'],
  namespaces: [],
};

afterEach(() => {
  cleanup();
});

describe('WidgetDataRenderer data variable empty column', () => {
  it('stops loading and shows no data when the value column is empty', async () => {
    const onRawData = vi.fn();
    const onRenderStatus = vi.fn();

    render(
      <WidgetWrapper
        dashboardId="ops"
        widgetId="config-preview:finance-cloud"
        chartType="cardList"
        config={{
          dataSource: datasource.id,
          chartType: 'cardList',
          dataSourceParams: [
            {
              name: 'uuids',
              alias_name: '实例标识',
              required: true,
              value: { dataVariableId: 'dv_region' },
            },
          ],
        }}
        dataSource={datasource}
        runtimeActive
        onRawData={onRawData}
        onRenderStatus={onRenderStatus}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText('dataVariable.reasonNoData')).toBeTruthy();
    });
    expect(document.querySelector('.ant-spin')).toBeNull();
    await waitFor(() => {
      expect(onRawData).toHaveBeenCalled();
    });
    const lastStatus = [...onRenderStatus.mock.calls].reverse()[0]?.[0];
    expect(lastStatus).toMatchObject({
      widgetId: 'config-preview:finance-cloud',
      status: 'empty',
    });
  });
});
