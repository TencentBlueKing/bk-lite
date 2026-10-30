// @vitest-environment jsdom

import React, { useEffect } from 'react';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import { ChartDataTransformer } from '@/app/ops-analysis/utils/chartDataTransform';
import type { ValueConfig } from '@/app/ops-analysis/types/dashBoard';

const testState = vi.hoisted(() => ({
  payload: null as unknown,
  fetchCount: 0,
}));

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

vi.mock('@/app/ops-analysis/utils/compareQuery', async () => {
  const actual = await vi.importActual<typeof import('@/app/ops-analysis/utils/compareQuery')>(
    '@/app/ops-analysis/utils/compareQuery',
  );
  return {
    ...actual,
    fetchCompareData: async () => {
      testState.fetchCount += 1;
      return {
        currentData: testState.payload,
        baselineData: null,
      };
    },
  };
});

vi.mock('@/app/ops-analysis/components/widgetRegistry', () => ({
  getWidgetComponent: (chartType?: string) => {
    return function FakeChart({
      rawData,
      loading,
      config,
      onReady,
    }: {
      rawData: unknown;
      loading?: boolean;
      config?: ValueConfig;
      onReady?: (hasData?: boolean) => void;
    }) {
      const chartData = chartType === 'line' || chartType === 'bar'
        ? ChartDataTransformer.transformToLineBarData(rawData, {
          dimensionField: config?.dimensionField,
          valueField: config?.valueField,
          valueFields: config?.valueFields,
          seriesField: config?.seriesField,
        })
        : { categories: [] as string[], values: [] as Array<number | null> };
      const hasData = chartData.categories.length > 0;
      useEffect(() => {
        if (!loading) onReady?.(hasData);
      }, [hasData, loading, onReady]);
      return (
        <div
          data-testid="mapped-line-bar"
          data-series={(chartData.series || []).map((series) => series.name).join(',')}
        />
      );
    };
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
  name: '宽表多系列趋势图',
  source_type: 'excel',
  desc: '',
  params: [],
  chart_type: ['line', 'bar'],
  namespaces: [],
};

const renderLine = (config: ValueConfig) => render(
  <WidgetWrapper
    dashboardId="preview"
    widgetId="line-mapping"
    chartType="line"
    config={{ dataSource: datasource.id, chartType: 'line', ...config }}
    dataSource={datasource}
  />,
);

afterEach(() => {
  cleanup();
  testState.payload = null;
  testState.fetchCount = 0;
});

describe('line and bar mapping revalidates the rows already fetched', () => {
  it('draws a wide chart after value fields are filled without fetching again', async () => {
    testState.payload = [
      { time: '10:00', cpu: 1, memory: 2 },
      { time: '10:05', cpu: 3, memory: 4 },
    ];
    const view = renderLine({});

    await waitFor(() => {
      expect(screen.getByText('dashboard.dataFormatMismatch')).toBeTruthy();
    });
    expect(testState.fetchCount).toBe(1);
    expect(screen.queryByTestId('mapped-line-bar')).toBeNull();

    view.rerender(
      <WidgetWrapper
        dashboardId="preview"
        widgetId="line-mapping"
        chartType="line"
        config={{
          dataSource: datasource.id,
          chartType: 'line',
          dimensionField: 'time',
          valueFields: ['cpu', 'memory'],
        }}
        dataSource={datasource}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('mapped-line-bar').getAttribute('data-series')).toBe('cpu,memory');
    });
    expect(screen.queryByText('dashboard.dataFormatMismatch')).toBeNull();
    expect(testState.fetchCount).toBe(1);
  });

  it('draws a single series after one value field is filled without fetching again', async () => {
    testState.payload = [
      { host: 'a', cpu: 1 },
      { host: 'b', cpu: 2 },
    ];
    const view = renderLine({});

    await waitFor(() => {
      expect(screen.getByText('dashboard.dataFormatMismatch')).toBeTruthy();
    });

    view.rerender(
      <WidgetWrapper
        dashboardId="preview"
        widgetId="line-mapping"
        chartType="line"
        config={{
          dataSource: datasource.id,
          chartType: 'line',
          dimensionField: 'host',
          valueField: 'cpu',
          valueFields: ['cpu'],
        }}
        dataSource={datasource}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('mapped-line-bar')).toBeTruthy();
    });
    expect(screen.queryByText('dashboard.dataFormatMismatch')).toBeNull();
    expect(testState.fetchCount).toBe(1);
  });

  it('draws long-table series after the series field is filled without fetching again', async () => {
    testState.payload = [
      { time: '10:00', metric: 'cpu', value: 1 },
      { time: '10:00', metric: 'mem', value: 2 },
      { time: '10:05', metric: 'cpu', value: 3 },
      { time: '10:05', metric: 'mem', value: 4 },
    ];
    const view = renderLine({
      dimensionField: 'time',
      valueFields: ['value'],
    });

    await waitFor(() => {
      expect(screen.getByTestId('mapped-line-bar')).toBeTruthy();
    });
    const fetchesAfterPartial = testState.fetchCount;

    view.rerender(
      <WidgetWrapper
        dashboardId="preview"
        widgetId="line-mapping"
        chartType="line"
        config={{
          dataSource: datasource.id,
          chartType: 'line',
          dimensionField: 'time',
          valueField: 'value',
          valueFields: ['value'],
          seriesField: 'metric',
        }}
        dataSource={datasource}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('mapped-line-bar').getAttribute('data-series')).toBe('cpu,mem');
    });
    expect(testState.fetchCount).toBe(fetchesAfterPartial);
  });

  it('returns to automatic detection after the mapping is cleared without fetching again', async () => {
    testState.payload = {
      cpu: [['10:00', 1]],
    };
    const view = renderLine({
      dimensionField: 'time',
      valueFields: ['cpu'],
    });

    await waitFor(() => {
      expect(screen.getByText('dashboard.dataFormatMismatch')).toBeTruthy();
    });
    const fetchesAfterMapped = testState.fetchCount;

    view.rerender(
      <WidgetWrapper
        dashboardId="preview"
        widgetId="line-mapping"
        chartType="line"
        config={{
          dataSource: datasource.id,
          chartType: 'line',
        }}
        dataSource={datasource}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('mapped-line-bar').getAttribute('data-series')).toBe('cpu');
    });
    expect(screen.queryByText('dashboard.dataFormatMismatch')).toBeNull();
    expect(testState.fetchCount).toBe(fetchesAfterMapped);
  });
});
