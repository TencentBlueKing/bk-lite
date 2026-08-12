// @vitest-environment jsdom

import React from 'react';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { HandledRequestError } from '@/utils/request';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';

const testState = vi.hoisted(() => ({
  messageError: vi.fn(),
  fetchCompareData: vi.fn(),
}));

vi.mock('antd', async () => {
  const actual = await vi.importActual<typeof import('antd')>('antd');
  return {
    ...actual,
    message: {
      ...actual.message,
      error: testState.messageError,
      warning: vi.fn(),
      success: vi.fn(),
      info: vi.fn(),
    },
  };
});

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

vi.mock('@/app/ops-analysis/context/common', () => ({
  useOpsAnalysis: () => ({ canvasDataSourceLookupStatus: 'ready' }),
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
  fetchCompareData: (...args: unknown[]) => testState.fetchCompareData(...args),
}));

vi.mock('@/app/ops-analysis/components/widgetRegistry', () => ({
  getWidgetComponent: () => function FakePie({
    onReady,
  }: {
    onReady?: (hasData?: boolean) => void;
  }) {
    React.useEffect(() => {
      onReady?.(true);
    }, [onReady]);
    return <div data-testid="pie-renderer" />;
  },
}));

import WidgetWrapper from '../widgetDataRenderer';

const datasource: DatasourceItem = {
  id: 42,
  created_at: '',
  updated_at: '',
  created_by: '',
  updated_by: '',
  domain: '',
  updated_by_domain: '',
  name: 'Namespace NATS',
  source_type: 'nats',
  desc: '',
  params: [],
  chart_type: ['pie'],
  namespaces: [1],
};

afterEach(() => {
  cleanup();
  testState.messageError.mockClear();
  testState.fetchCompareData.mockReset();
});

describe('WidgetWrapper runtime fetch failure', () => {
  it('shows business error in widget without global message.error', async () => {
    const businessError = '未找到可用命名空间';
    testState.fetchCompareData.mockRejectedValue(new HandledRequestError(businessError));

    render(
      <WidgetWrapper
        dashboardId="dashboard-1"
        widgetId="widget-1"
        chartType="pie"
        config={{ dataSource: datasource.id }}
        dataSource={datasource}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText(businessError)).toBeTruthy();
    });
    expect(testState.messageError).not.toHaveBeenCalled();
    expect(screen.queryByTestId('pie-renderer')).toBeNull();
  });

  it('recovers after failed request is followed by success', async () => {
    const businessError = '未找到可用命名空间';
    testState.fetchCompareData
      .mockRejectedValueOnce(new HandledRequestError(businessError))
      .mockResolvedValueOnce({
        currentData: [{ name: 'A', value: 1 }],
        baselineData: null,
      });

    const { rerender } = render(
      <WidgetWrapper
        dashboardId="dashboard-1"
        widgetId="widget-1"
        chartType="pie"
        config={{ dataSource: datasource.id }}
        dataSource={datasource}
        reloadVersion="0:0"
      />,
    );

    await waitFor(() => {
      expect(screen.getByText(businessError)).toBeTruthy();
    });

    rerender(
      <WidgetWrapper
        dashboardId="dashboard-1"
        widgetId="widget-1"
        chartType="pie"
        config={{ dataSource: datasource.id }}
        dataSource={datasource}
        reloadVersion="1:0"
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('pie-renderer')).toBeTruthy();
    });
    expect(screen.queryByText(businessError)).toBeNull();
    expect(testState.messageError).not.toHaveBeenCalled();
  });
});
