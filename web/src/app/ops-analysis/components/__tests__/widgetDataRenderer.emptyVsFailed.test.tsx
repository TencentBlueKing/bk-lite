// @vitest-environment jsdom

import React, { useEffect } from 'react';
import { cleanup, render, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import { ChartDataTransformer } from '@/app/ops-analysis/utils/chartDataTransform';
import {
  extractComparableValue,
  toComparableNumber,
} from '@/app/ops-analysis/utils/compareQuery';
import { parseTableLikeData } from '@/app/ops-analysis/utils/tableLikeData';
import { buildDashboardRenderSignal } from '@/app/ops-analysis/renderContract';
import type { DashboardWidgetRenderResult } from '@/app/ops-analysis/renderContract';

const testState = vi.hoisted(() => ({
  payload: null as unknown,
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
    fetchCompareData: async () => ({
      currentData: testState.payload,
      baselineData: null,
    }),
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
      config?: { selectedFields?: string[] };
      onReady?: (hasData?: boolean) => void;
    }) {
      let hasData = Boolean(rawData);
      if (chartType === 'pie') {
        const chartData = ChartDataTransformer.transformToPieData(rawData);
        hasData = chartData.some(
          (item) => Number.isFinite(item.value) && item.value > 0,
        );
      } else if (chartType === 'single') {
        hasData = extractComparableValue(rawData, config?.selectedFields?.[0]) !== null;
      } else if (chartType === 'gauge') {
        hasData =
          toComparableNumber(
            extractComparableValue(rawData, config?.selectedFields?.[0]),
          ) !== null;
      } else if (chartType === 'line' || chartType === 'bar') {
        hasData =
          ChartDataTransformer.transformToLineBarData(rawData).categories.length > 0;
      } else if (chartType === 'topN' || chartType === 'table') {
        hasData =
          parseTableLikeData(rawData, { current: 1, pageSize: 20 }).rows.length > 0;
      }
      useEffect(() => {
        if (!loading) onReady?.(hasData);
      }, [hasData, loading, onReady]);
      return <div data-testid={`${chartType || 'chart'}-renderer`} />;
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
  name: '云资源成本汇总',
  source_type: 'nats',
  desc: '',
  params: [],
  chart_type: ['single', 'pie', 'topN', 'table'],
  namespaces: [],
};

const emptyCloudCostSummary = {
  total_cost: '0.00',
  instance_count: 0,
  avg_daily_cost: '0.00',
  mom_change_pct: null,
};

const lastTerminalStatus = (
  onRenderStatus: ReturnType<typeof vi.fn>,
): DashboardWidgetRenderResult | undefined => {
  const calls = onRenderStatus.mock.calls.map(
    ([result]) => result as DashboardWidgetRenderResult,
  );
  return [...calls].reverse().find((result) => result.status !== 'loading');
};

const renderWidget = ({
  widgetId,
  chartType,
  config,
}: {
  widgetId: string;
  chartType: string;
  config?: Record<string, unknown>;
}) => {
  const onRenderStatus = vi.fn();
  render(
    <WidgetWrapper
      dashboardId="cloud-cost"
      widgetId={widgetId}
      chartType={chartType}
      config={{ dataSource: datasource.id, ...config }}
      dataSource={datasource}
      onRenderStatus={onRenderStatus}
    />,
  );
  return onRenderStatus;
};

afterEach(() => {
  cleanup();
  testState.payload = null;
});

describe('Cloud cost empty payloads must not fail report render', () => {
  it('reports empty for all-zero pie slices instead of staying loading', async () => {
    testState.payload = [
      { name: '计算', value: 0 },
      { name: '存储', value: 0 },
    ];
    const onRenderStatus = renderWidget({
      widgetId: 'pie-zero',
      chartType: 'pie',
    });

    await waitFor(() => {
      expect(lastTerminalStatus(onRenderStatus)).toEqual({
        widgetId: 'pie-zero',
        status: 'empty',
      });
    });
  });

  it('reports empty for cloud-cost 环比 null instead of staying loading', async () => {
    testState.payload = emptyCloudCostSummary;
    const onRenderStatus = renderWidget({
      widgetId: 'mom-change',
      chartType: 'single',
      config: { selectedFields: ['mom_change_pct'] },
    });

    await waitFor(() => {
      expect(lastTerminalStatus(onRenderStatus)).toEqual({
        widgetId: 'mom-change',
        status: 'empty',
      });
    });
  });

  it('reports ready for zero total_cost KPI instead of empty', async () => {
    testState.payload = emptyCloudCostSummary;
    const onRenderStatus = renderWidget({
      widgetId: 'total-cost',
      chartType: 'single',
      config: { selectedFields: ['total_cost'] },
    });

    await waitFor(() => {
      expect(lastTerminalStatus(onRenderStatus)).toEqual({
        widgetId: 'total-cost',
        status: 'ready',
      });
    });
  });

  it('reports empty for empty distribution list as pie', async () => {
    testState.payload = [];
    const onRenderStatus = renderWidget({
      widgetId: 'pie-empty-list',
      chartType: 'pie',
    });

    await waitFor(() => {
      expect(lastTerminalStatus(onRenderStatus)).toEqual({
        widgetId: 'pie-empty-list',
        status: 'empty',
      });
    });
  });

  it('reports empty for empty bill table envelope', async () => {
    testState.payload = { total: 0, page: 1, page_size: 20, items: [] };
    const onRenderStatus = renderWidget({
      widgetId: 'bill-table',
      chartType: 'table',
    });

    await waitFor(() => {
      expect(lastTerminalStatus(onRenderStatus)).toEqual({
        widgetId: 'bill-table',
        status: 'empty',
      });
    });
  });

  it('reports empty for structurally empty line envelope instead of staying loading', async () => {
    testState.payload = { categories: [], values: [] };
    const onRenderStatus = renderWidget({
      widgetId: 'line-empty',
      chartType: 'line',
    });

    await waitFor(() => {
      expect(lastTerminalStatus(onRenderStatus)).toEqual({
        widgetId: 'line-empty',
        status: 'empty',
      });
    });
  });

  it('reports ready for line categories including all-zero values', async () => {
    testState.payload = [{ name: '周一', value: 0 }];
    const onRenderStatus = renderWidget({
      widgetId: 'line-zero',
      chartType: 'line',
    });

    await waitFor(() => {
      expect(lastTerminalStatus(onRenderStatus)).toEqual({
        widgetId: 'line-zero',
        status: 'ready',
      });
    });
  });

  it('reports empty for table count envelope without items instead of staying loading', async () => {
    testState.payload = { count: 0 };
    const onRenderStatus = renderWidget({
      widgetId: 'count-table',
      chartType: 'table',
    });

    await waitFor(() => {
      expect(lastTerminalStatus(onRenderStatus)).toEqual({
        widgetId: 'count-table',
        status: 'empty',
      });
    });
  });

  it('reports ready for pie slices with a positive value', async () => {
    testState.payload = [
      { name: '计算', value: 0 },
      { name: '存储', value: 8 },
    ];
    const onRenderStatus = renderWidget({
      widgetId: 'pie-ready',
      chartType: 'pie',
    });

    await waitFor(() => {
      expect(lastTerminalStatus(onRenderStatus)).toEqual({
        widgetId: 'pie-ready',
        status: 'ready',
      });
    });
  });

  it('reports ready for gauge zero instead of empty', async () => {
    testState.payload = { value: 0 };
    const onRenderStatus = renderWidget({
      widgetId: 'gauge-zero',
      chartType: 'gauge',
      config: { selectedFields: ['value'] },
    });

    await waitFor(() => {
      expect(lastTerminalStatus(onRenderStatus)).toEqual({
        widgetId: 'gauge-zero',
        status: 'ready',
      });
    });
  });

  it('aggregates empty widgets into report-ready, not report-failed', async () => {
    testState.payload = emptyCloudCostSummary;
    const onRenderStatus = renderWidget({
      widgetId: 'mom-change',
      chartType: 'single',
      config: { selectedFields: ['mom_change_pct'] },
    });

    await waitFor(() => {
      expect(lastTerminalStatus(onRenderStatus)?.status).toBe('empty');
    });

    const signal = buildDashboardRenderSignal(
      'cloud-cost',
      ['mom-change', 'pie-empty', 'bill-table'],
      new Map([
        ['mom-change', { widgetId: 'mom-change', status: 'empty' }],
        ['pie-empty', { widgetId: 'pie-empty', status: 'empty' }],
        ['bill-table', { widgetId: 'bill-table', status: 'empty' }],
      ]),
    );
    expect(signal?.type).toBe('report-ready');
  });
});
