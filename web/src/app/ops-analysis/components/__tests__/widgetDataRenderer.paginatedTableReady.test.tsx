// @vitest-environment jsdom

import React, { useEffect } from 'react';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { DatasourceItem } from '@/app/ops-analysis/types/dataSource';
import { buildDashboardRenderSignal } from '@/app/ops-analysis/renderContract';
import type { DashboardWidgetRenderResult } from '@/app/ops-analysis/renderContract';

const testState = vi.hoisted(() => ({
  fetchCompareData: vi.fn(),
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

vi.mock('@/app/ops-analysis/utils/compareQuery', () => ({
  fetchCompareData: (...args: unknown[]) => testState.fetchCompareData(...args),
}));

vi.mock('@/app/ops-analysis/components/widgetRegistry', () => ({
  getWidgetComponent: () =>
    function FakePaginatedTable({
      loading,
      rawData,
      onReady,
      onQueryChange,
    }: {
      loading?: boolean;
      rawData?: unknown;
      onReady?: (hasData?: boolean) => void;
      onQueryChange?: (params: Record<string, unknown>) => void;
    }) {
      useEffect(() => {
        onQueryChange?.({ page: 1, page_size: 20 });
      }, [onQueryChange]);
      useEffect(() => {
        if (!loading) {
          const rows = (rawData as { items?: unknown[] } | null)?.items;
          onReady?.(Array.isArray(rows) && rows.length > 0);
        }
      }, [loading, onReady, rawData]);
      const hasRows = Array.isArray((rawData as { items?: unknown[] } | null)?.items)
        && ((rawData as { items?: unknown[] }).items?.length ?? 0) > 0;
      return (
        <div>
          {loading ? <span data-testid="table-loading">loading</span> : null}
          {!hasRows ? <span data-testid="table-empty">暂无数据</span> : null}
        </div>
      );
    },
}));

import WidgetWrapper from '../widgetDataRenderer';

const billDetailDatasource: DatasourceItem = {
  id: 77,
  created_at: '',
  updated_at: '',
  created_by: '',
  updated_by: '',
  domain: '',
  updated_by_domain: '',
  name: '云资源账单明细',
  source_type: 'nats',
  desc: '',
  params: [
    { name: 'page', type: 'number', value: 1, alias_name: '页码', filterType: 'params' },
    { name: 'page_size', type: 'number', value: 20, alias_name: '每页数量', filterType: 'params' },
  ],
  chart_type: ['table'],
  namespaces: [],
};

const emptyBillPayload = { total: 0, page: 1, page_size: 20, items: [] };

afterEach(() => {
  cleanup();
  testState.fetchCompareData.mockReset();
});

describe('paginated table report-ready vs loading overlay', () => {
  it('must not show a loading overlay after reporting a terminal status', async () => {
    testState.fetchCompareData.mockResolvedValue({
      currentData: emptyBillPayload,
      baselineData: null,
    });

    const onRenderStatus = vi.fn();
    render(
      <WidgetWrapper
        dashboardId="cloud-bill"
        widgetId="bill-table"
        chartType="table"
        config={{ dataSource: billDetailDatasource.id }}
        dataSource={billDetailDatasource}
        onRenderStatus={onRenderStatus}
      />,
    );

    await waitFor(() => {
      expect(onRenderStatus).toHaveBeenCalledWith({
        widgetId: 'bill-table',
        status: 'empty',
      });
    });

    const signal = buildDashboardRenderSignal(
      'cloud-bill',
      ['bill-table'],
      new Map([
        [
          'bill-table',
          onRenderStatus.mock.calls.at(-1)?.[0] as DashboardWidgetRenderResult,
        ],
      ]),
    );
    expect(signal?.type).toBe('report-ready');
    await waitFor(() => {
      expect(testState.fetchCompareData).toHaveBeenCalledTimes(1);
      expect(screen.queryByTestId('table-loading')).toBeNull();
    });
    expect(screen.getByTestId('table-empty').textContent).toBe('暂无数据');
    expect(onRenderStatus.mock.calls.at(-1)?.[0]).toEqual({
      widgetId: 'bill-table',
      status: 'empty',
    });
  });
});
