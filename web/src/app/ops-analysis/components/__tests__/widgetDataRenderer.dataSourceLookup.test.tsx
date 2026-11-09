// @vitest-environment jsdom

import React from 'react';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { DataSourceLookupStatus } from '@/app/ops-analysis/utils/widgetRequestVersion';
import type { DashboardWidgetRenderResult } from '@/app/ops-analysis/renderContract';

const testState = vi.hoisted(() => ({
  lookupStatus: 'error' as DataSourceLookupStatus,
}));

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

vi.mock('@/app/ops-analysis/context/common', () => ({
  useOpsAnalysis: () => ({
    canvasDataSourceLookupStatus: testState.lookupStatus,
    dataSources: [],
  }),
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

vi.mock('@/app/ops-analysis/components/widgetRegistry', () => ({
  getWidgetComponent: () => function FakeChart() {
    return <div data-testid="chart-renderer" />;
  },
}));

import WidgetWrapper from '../widgetDataRenderer';

afterEach(() => {
  cleanup();
  testState.lookupStatus = 'error';
});

describe('WidgetWrapper canvas data source lookup', () => {
  it('shows data-source-load-error and reports failed when lookup is error', async () => {
    const onRenderStatus = vi.fn();
    render(
      <WidgetWrapper
        dashboardId="dashboard-1"
        widgetId="w-chart"
        chartType="line"
        config={{ dataSource: 7 }}
        onRenderStatus={onRenderStatus}
      />,
    );

    expect(await screen.findByText('dashboard.dataSourceLoadFailed')).toBeTruthy();
    await waitFor(() => {
      const last = onRenderStatus.mock.calls.at(-1)?.[0] as DashboardWidgetRenderResult;
      expect(last).toEqual({
        widgetId: 'w-chart',
        status: 'failed',
        error: 'dashboard.dataFetchFailed',
        errorCode: 'datasource_missing',
      });
    });
  });
});
