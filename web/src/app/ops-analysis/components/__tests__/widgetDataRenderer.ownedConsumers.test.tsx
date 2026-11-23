// @vitest-environment jsdom

import React from 'react';
import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { HandledRequestError } from '@/utils/request';
import type { DatasourceItem, ParamItem } from '@/app/ops-analysis/types/dataSource';

const testState = vi.hoisted(() => ({
  fetchCompareData: vi.fn(),
  getSourceDataByApiId: vi.fn(),
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
      getSourceDataByApiId: testState.getSourceDataByApiId,
      getDataSourceList: vi.fn(),
    }),
  };
});

vi.mock('@/app/ops-analysis/utils/compareQuery', () => ({
  fetchCompareData: (...args: unknown[]) => testState.fetchCompareData(...args),
  validateGaugeData: vi.fn(),
}));

vi.mock('@/app/ops-analysis/components/widgetRegistry', () => ({
  getWidgetComponent: () => function FakeChart({
    loading,
    rawData,
  }: {
    loading?: boolean;
    rawData?: unknown;
  }) {
    return (
      <div>
        {loading ? <span data-testid="chart-loading">loading</span> : null}
        {rawData ? <div data-testid="chart-renderer">{JSON.stringify(rawData)}</div> : null}
      </div>
    );
  },
}));

import WidgetWrapper from '../widgetDataRenderer';
import { DashboardRuntimeSchedulerProvider } from '@/app/ops-analysis/context/dashboardRuntimeScheduler';
import { DashboardRuntimeScheduler } from '@/app/ops-analysis/utils/dashboardRuntimeScheduler';

const switchParam = (sourceId: number): ParamItem => ({
  name: 'server_room_id',
  alias_name: '机房',
  type: 'string',
  filterType: 'params',
  value: 'room-1',
  inputConfig: {
    control: 'select',
    componentSwitch: true,
    optionsSource: {
      type: 'dynamic',
      sourceId,
      valueField: 'id',
      labelField: 'name',
    },
  },
});

const datasource = (sourceId: number): DatasourceItem => ({
  id: 42,
  created_at: '',
  updated_at: '',
  created_by: '',
  updated_by: '',
  domain: '',
  updated_by_domain: '',
  name: 'TopN source',
  source_type: 'rest_api',
  desc: '',
  params: [switchParam(sourceId)],
  chart_type: ['topN'],
  namespaces: [1],
});

const renderSwitch = (sourceId: number, dashboardId = 'dashboard-1') => (
  <DashboardRuntimeSchedulerProvider>
    <WidgetWrapper
      dashboardId={dashboardId}
      widgetId="widget-options"
      chartType="topN"
      config={{ dataSource: 42, dataSourceParams: [switchParam(sourceId)] }}
      dataSource={datasource(sourceId)}
    />
  </DashboardRuntimeSchedulerProvider>
);

afterEach(() => {
  cleanup();
  testState.fetchCompareData.mockReset();
  testState.getSourceDataByApiId.mockReset();
});

describe('WidgetWrapper owned scheduler consumers', () => {
  it('forgets a settled options consumer and still aborts a later in-flight one', async () => {
    const releaseConsumer = vi.spyOn(DashboardRuntimeScheduler.prototype, 'releaseConsumer');
    const pending: Array<{
      sourceId: number;
      signal?: AbortSignal;
      resolve: (value: { data: Array<{ id: string; name: string }> }) => void;
    }> = [];
    testState.getSourceDataByApiId.mockImplementation(
      (id: number, _params: unknown, options?: { signal?: AbortSignal }) => new Promise((resolve) => {
        pending.push({ sourceId: id, signal: options?.signal, resolve });
      }),
    );
    testState.fetchCompareData.mockResolvedValue({
      currentData: [{ name: 'room', value: 1 }],
      baselineData: null,
    });

    try {
      const { rerender } = render(renderSwitch(7));
      await waitFor(() => expect(pending).toHaveLength(1));
      rerender(renderSwitch(8));
      await waitFor(() => expect(pending).toHaveLength(2));
      await act(async () => {
        pending[0].resolve({ data: [{ id: 'room-1', name: '一号机房' }] });
      });
      expect(releaseConsumer).not.toHaveBeenCalled();
      expect(pending[1].signal?.aborted).toBe(false);

      rerender(renderSwitch(8, 'dashboard-2'));
      await waitFor(() => expect(pending[1].signal?.aborted).toBe(true));
      expect(releaseConsumer).toHaveBeenCalledTimes(1);
      expect(pending[0].signal?.aborted).toBe(false);
      expect(screen.queryByText('网络异常')).toBeNull();
      expect(screen.queryByText('dashboard.dataFetchFailed')).toBeNull();
    } finally {
      releaseConsumer.mockRestore();
    }
  });

  it('forgets a failed options consumer before the next canvas change', async () => {
    const releaseConsumer = vi.spyOn(DashboardRuntimeScheduler.prototype, 'releaseConsumer');
    testState.getSourceDataByApiId.mockRejectedValue(new HandledRequestError('选项失败'));
    testState.fetchCompareData.mockResolvedValue({
      currentData: [{ name: 'room', value: 1 }],
      baselineData: null,
    });

    try {
      const { rerender } = render(renderSwitch(7));
      await waitFor(() => {
        expect(screen.getByText('选项失败')).toBeTruthy();
      });
      await Promise.resolve();
      rerender(renderSwitch(7, 'dashboard-2'));
      await Promise.resolve();
      expect(releaseConsumer).not.toHaveBeenCalled();
      expect(testState.fetchCompareData).not.toHaveBeenCalled();
    } finally {
      releaseConsumer.mockRestore();
    }
  });
});
