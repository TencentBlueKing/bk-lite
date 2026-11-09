// @vitest-environment jsdom

import React from 'react';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';

const testState = vi.hoisted(() => ({
  fetchCompareData: vi.fn(),
}));

vi.mock('antd', async () => {
  const actual = await vi.importActual<typeof import('antd')>('antd');
  return {
    ...actual,
    message: {
      ...actual.message,
      error: vi.fn(),
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
  fetchCompareData: (...args: unknown[]) => testState.fetchCompareData(...args),
}));

vi.mock('@/app/ops-analysis/components/widgetRegistry', () => ({
  getWidgetComponent: (chartType?: string) => function FakeChart({
    loading,
    rawData,
    onReady,
  }: {
    loading?: boolean;
    rawData?: unknown;
    onReady?: (hasData?: boolean) => void;
  }) {
    React.useEffect(() => {
      if (!loading) onReady?.(Boolean(rawData));
    }, [loading, onReady, rawData]);
    return (
      <div
        data-testid="chart-renderer"
        data-chart-type={chartType}
        data-loading={String(Boolean(loading))}
      />
    );
  },
}));

import WidgetWrapper from '../widgetDataRenderer';

const datasource: DatasourceItem = {
  id: 149,
  created_at: '',
  updated_at: '',
  created_by: '',
  updated_by: '',
  domain: '',
  updated_by_domain: '',
  name: 'CMDB 实例查询',
  source_type: 'nats',
  desc: '',
  params: [],
  chart_type: ['table', 'eventTable', 'line'],
  namespaces: [],
};

const itemsEnvelope = {
  items: [{ inst_uuid: '4c4b9718', inst_name: 'bare-01', model_id: 'host' }],
  count: 16,
  fields: [],
};

const renderChart = ({
  chartType,
  reloadVersion = '1',
  onRawData = vi.fn(),
}: {
  chartType: string;
  reloadVersion?: string;
  onRawData?: ReturnType<typeof vi.fn>;
}) => {
  const view = render(
    <WidgetWrapper
      dashboardId="ops"
      widgetId="config-preview:cmdb"
      chartType={chartType}
      config={{ dataSource: datasource.id, chartType }}
      dataSource={datasource}
      reloadVersion={reloadVersion}
      sampleTicket={{ widgetId: 'config-preview:cmdb', sequence: 1 }}
      onRawData={onRawData}
      runtimeActive
    />,
  );
  return { ...view, onRawData };
};

afterEach(() => {
  cleanup();
  testState.fetchCompareData.mockReset();
});

describe('table preview loading releases onRawData', () => {
  it.each(['table', 'eventTable'])(
    'emits onRawData after %s items envelope succeeds',
    async (chartType) => {
      testState.fetchCompareData.mockResolvedValue({
        currentData: itemsEnvelope,
        baselineData: null,
      });
      const onRawData = vi.fn();
      renderChart({ chartType, onRawData });

      await waitFor(() => {
        expect(onRawData).toHaveBeenCalledWith(
          itemsEnvelope,
          { widgetId: 'config-preview:cmdb', sequence: 1 },
        );
      });
      expect(screen.getByTestId('chart-renderer').getAttribute('data-loading')).toBe('false');
    },
  );

  it('emits onRawData after a table failure so the preview can retry', async () => {
    const failed = new Error('实例查询失败');
    testState.fetchCompareData
      .mockRejectedValueOnce(failed)
      .mockResolvedValue({ currentData: itemsEnvelope, baselineData: null });
    const onRawData = vi.fn();
    const view = renderChart({ chartType: 'table', reloadVersion: '1', onRawData });

    await waitFor(() => {
      expect(onRawData).toHaveBeenCalledWith(
        null,
        { widgetId: 'config-preview:cmdb', sequence: 1 },
      );
    });
    expect(screen.getByText('实例查询失败')).toBeTruthy();
    expect(screen.queryByTestId('chart-renderer')).toBeNull();

    onRawData.mockClear();
    view.rerender(
      <WidgetWrapper
        dashboardId="ops"
        widgetId="config-preview:cmdb"
        chartType="table"
        config={{ dataSource: datasource.id, chartType: 'table' }}
        dataSource={datasource}
        reloadVersion="2"
        sampleTicket={{ widgetId: 'config-preview:cmdb', sequence: 1 }}
        onRawData={onRawData}
        runtimeActive
      />,
    );

    await waitFor(() => {
      expect(onRawData).toHaveBeenCalledWith(
        itemsEnvelope,
        { widgetId: 'config-preview:cmdb', sequence: 1 },
      );
    });
    expect(testState.fetchCompareData).toHaveBeenCalledTimes(2);
    expect(screen.queryByText('实例查询失败')).toBeNull();
    expect(screen.getByTestId('chart-renderer').getAttribute('data-loading')).toBe('false');
  });

  it('does not let a stale table response overwrite the current request', async () => {
    let resolveStale: (value: { currentData: unknown; baselineData: null }) => void = () => undefined;
    const stalePayload = { items: [{ inst_name: 'stale-host' }], count: 1, fields: [] };
    const currentPayload = { items: [{ inst_name: 'nic-01' }], count: 1, fields: [] };
    testState.fetchCompareData.mockImplementationOnce(
      () => new Promise((resolve) => {
        resolveStale = resolve;
      }),
    );
    const onRawData = vi.fn();
    const view = renderChart({ chartType: 'table', reloadVersion: '1', onRawData });

    await waitFor(() => {
      expect(testState.fetchCompareData).toHaveBeenCalledTimes(1);
    });

    testState.fetchCompareData.mockResolvedValue({
      currentData: currentPayload,
      baselineData: null,
    });
    view.rerender(
      <WidgetWrapper
        dashboardId="ops"
        widgetId="config-preview:cmdb"
        chartType="table"
        config={{ dataSource: datasource.id, chartType: 'table' }}
        dataSource={datasource}
        reloadVersion="2"
        sampleTicket={{ widgetId: 'config-preview:cmdb', sequence: 1 }}
        onRawData={onRawData}
        runtimeActive
      />,
    );

    await waitFor(() => {
      expect(onRawData).toHaveBeenCalledWith(
        currentPayload,
        { widgetId: 'config-preview:cmdb', sequence: 1 },
      );
    });

    resolveStale({ currentData: stalePayload, baselineData: null });
    await waitFor(() => {
      expect(testState.fetchCompareData).toHaveBeenCalledTimes(2);
    });
    expect(onRawData.mock.calls.some(([data]) => data === stalePayload)).toBe(false);
    expect(onRawData.mock.calls.at(-1)?.[0]).toBe(currentPayload);
  });

  it('still emits onRawData for a non-table chart', async () => {
    const linePayload = [{ name: 'east', value: 1 }];
    testState.fetchCompareData.mockResolvedValue({
      currentData: linePayload,
      baselineData: null,
    });
    const onRawData = vi.fn();
    renderChart({ chartType: 'line', onRawData });

    await waitFor(() => {
      expect(onRawData).toHaveBeenCalledWith(
        linePayload,
        { widgetId: 'config-preview:cmdb', sequence: 1 },
      );
    });
    expect(screen.getByTestId('chart-renderer').getAttribute('data-chart-type')).toBe('line');
    expect(screen.getByTestId('chart-renderer').getAttribute('data-loading')).toBe('false');
  });

  it('keeps a settled table visible during a silent refresh', async () => {
    let resolveSilent: (value: { currentData: unknown; baselineData: null }) => void = () => undefined;
    const refreshed = { items: [{ inst_name: 'refreshed' }], count: 1, fields: [] };
    testState.fetchCompareData
      .mockResolvedValueOnce({ currentData: itemsEnvelope, baselineData: null })
      .mockImplementationOnce(() => new Promise((resolve) => {
        resolveSilent = resolve;
      }));
    const onRawData = vi.fn();
    const view = renderChart({ chartType: 'table', onRawData });

    await waitFor(() => {
      expect(onRawData).toHaveBeenCalledWith(itemsEnvelope, expect.anything());
    });
    onRawData.mockClear();
    view.rerender(
      <WidgetWrapper
        dashboardId="ops"
        widgetId="config-preview:cmdb"
        chartType="table"
        config={{ dataSource: datasource.id, chartType: 'table' }}
        dataSource={datasource}
        reloadVersion="2"
        refreshCause="periodic"
        sampleTicket={{ widgetId: 'config-preview:cmdb', sequence: 1 }}
        onRawData={onRawData}
        runtimeActive
      />,
    );

    await waitFor(() => {
      expect(testState.fetchCompareData).toHaveBeenCalledTimes(2);
    });
    expect(screen.getByTestId('chart-renderer').getAttribute('data-loading')).toBe('false');
    resolveSilent({ currentData: refreshed, baselineData: null });
    await waitFor(() => {
      expect(onRawData).toHaveBeenCalledWith(
        refreshed,
        { widgetId: 'config-preview:cmdb', sequence: 1 },
      );
    });
  });

  it('keeps the last table payload when a silent refresh fails', async () => {
    testState.fetchCompareData
      .mockResolvedValueOnce({ currentData: itemsEnvelope, baselineData: null })
      .mockRejectedValueOnce(new Error('静默失败'));
    const onRawData = vi.fn();
    const view = renderChart({ chartType: 'table', onRawData });

    await waitFor(() => {
      expect(onRawData).toHaveBeenCalledWith(itemsEnvelope, expect.anything());
    });
    onRawData.mockClear();
    view.rerender(
      <WidgetWrapper
        dashboardId="ops"
        widgetId="config-preview:cmdb"
        chartType="table"
        config={{ dataSource: datasource.id, chartType: 'table' }}
        dataSource={datasource}
        reloadVersion="2"
        refreshCause="visibility"
        sampleTicket={{ widgetId: 'config-preview:cmdb', sequence: 1 }}
        onRawData={onRawData}
        runtimeActive
      />,
    );

    await waitFor(() => {
      expect(testState.fetchCompareData).toHaveBeenCalledTimes(2);
    });
    expect(screen.queryByText('静默失败')).toBeNull();
    expect(onRawData.mock.calls.some(([data]) => data === null)).toBe(false);
    expect(screen.getByTestId('chart-renderer')).toBeTruthy();
  });
});
