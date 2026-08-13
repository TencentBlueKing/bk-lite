// @vitest-environment jsdom

import React from 'react';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { HandledRequestError } from '@/utils/request';
import type { DatasourceItem, ParamItem } from '@/app/ops-analysis/types/dataSource';

interface OptionState {
  status: 'idle' | 'loading' | 'success' | 'error';
  options: Array<{ value: string | number; label: string }>;
  errorMessage?: string;
  resultKey?: string;
}

const testState = vi.hoisted(() => {
  const translate = (key: string) => key;
  return {
    messageError: vi.fn(),
    fetchCompareData: vi.fn(),
    translate,
    optionState: {
      status: 'idle',
      options: [],
    } as OptionState,
    loaderOptions: undefined as
      | { suppressErrorNotification?: boolean; fallbackErrorMessage?: string }
      | undefined,
  };
});

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
    t: testState.translate,
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
  useParamInputOptions: (
    _inputConfig: unknown,
    loaderOptions?: { suppressErrorNotification?: boolean; fallbackErrorMessage?: string },
  ) => {
    testState.loaderOptions = loaderOptions;
    return testState.optionState;
  },
}));

vi.mock('@/app/ops-analysis/utils/compareQuery', () => ({
  fetchCompareData: (...args: unknown[]) => testState.fetchCompareData(...args),
}));

vi.mock('@/app/ops-analysis/components/widgetRegistry', () => ({
  getWidgetComponent: () => function FakeChart({
    onReady,
  }: {
    onReady?: (hasData?: boolean) => void;
  }) {
    React.useEffect(() => {
      onReady?.(true);
    }, [onReady]);
    return <div data-testid="chart-renderer" />;
  },
}));

import WidgetWrapper from '../widgetDataRenderer';

const pieDatasource: DatasourceItem = {
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

const switchParam: ParamItem = {
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
      sourceId: 7,
      valueField: 'id',
      labelField: 'name',
    },
  },
};

const topNDatasource: DatasourceItem = {
  ...pieDatasource,
  name: 'TopN source',
  source_type: 'rest_api',
  params: [switchParam],
  chart_type: ['topN'],
};

afterEach(() => {
  cleanup();
  testState.messageError.mockClear();
  testState.fetchCompareData.mockReset();
  testState.optionState = {
    status: 'idle',
    options: [],
  };
  testState.loaderOptions = undefined;
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
        config={{ dataSource: pieDatasource.id }}
        dataSource={pieDatasource}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText(businessError)).toBeTruthy();
    });
    expect(testState.messageError).not.toHaveBeenCalled();
    expect(screen.queryByTestId('chart-renderer')).toBeNull();
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
        config={{ dataSource: pieDatasource.id }}
        dataSource={pieDatasource}
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
        config={{ dataSource: pieDatasource.id }}
        dataSource={pieDatasource}
        reloadVersion="1:0"
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('chart-renderer')).toBeTruthy();
    });
    expect(screen.queryByText(businessError)).toBeNull();
    expect(testState.messageError).not.toHaveBeenCalled();
  });
});

describe('WidgetWrapper component switch options runtime', () => {
  it('keeps widget loading and skips main fetch while options are loading', async () => {
    testState.optionState = { status: 'loading', options: [] };

    const { container } = render(
      <WidgetWrapper
        dashboardId="dashboard-1"
        widgetId="widget-1"
        chartType="topN"
        config={{ dataSource: topNDatasource.id, dataSourceParams: [switchParam] }}
        dataSource={topNDatasource}
      />,
    );

    await waitFor(() => {
      expect(container.querySelector('.ant-spin')).toBeTruthy();
    });
    expect(testState.fetchCompareData).not.toHaveBeenCalled();
    expect(testState.loaderOptions?.suppressErrorNotification).toBe(true);
  });

  it('shows options business error without global toast and skips main fetch', async () => {
    const businessError = '未找到可用命名空间';
    testState.optionState = {
      status: 'error',
      options: [],
      errorMessage: businessError,
    };

    render(
      <WidgetWrapper
        dashboardId="dashboard-1"
        widgetId="widget-1"
        chartType="topN"
        config={{ dataSource: topNDatasource.id, dataSourceParams: [switchParam] }}
        dataSource={topNDatasource}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText(businessError)).toBeTruthy();
    });
    expect(screen.queryByText('dashboard.noData')).toBeNull();
    expect(testState.fetchCompareData).not.toHaveBeenCalled();
    expect(testState.messageError).not.toHaveBeenCalled();
  });

  it('sends main fetch after options succeed', async () => {
    testState.optionState = {
      status: 'success',
      options: [{ value: 'room-1', label: 'Room 1' }],
      resultKey: 'ok',
    };
    testState.fetchCompareData.mockResolvedValue({
      currentData: [{ name: 'A', value: 1 }],
      baselineData: null,
    });

    render(
      <WidgetWrapper
        dashboardId="dashboard-1"
        widgetId="widget-1"
        chartType="topN"
        config={{ dataSource: topNDatasource.id, dataSourceParams: [switchParam] }}
        dataSource={topNDatasource}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('chart-renderer')).toBeTruthy();
    });
    expect(testState.fetchCompareData).toHaveBeenCalled();
  });

  it('recovers after options failure when options later succeed', async () => {
    const businessError = '未找到可用命名空间';
    testState.optionState = {
      status: 'error',
      options: [],
      errorMessage: businessError,
    };
    testState.fetchCompareData.mockResolvedValue({
      currentData: [{ name: 'A', value: 1 }],
      baselineData: null,
    });

    const { rerender } = render(
      <WidgetWrapper
        dashboardId="dashboard-1"
        widgetId="widget-1"
        chartType="topN"
        config={{ dataSource: topNDatasource.id, dataSourceParams: [switchParam] }}
        dataSource={topNDatasource}
        reloadVersion="0:0"
      />,
    );

    await waitFor(() => {
      expect(screen.getByText(businessError)).toBeTruthy();
    });
    expect(testState.fetchCompareData).not.toHaveBeenCalled();

    testState.optionState = {
      status: 'success',
      options: [{ value: 'room-1', label: 'Room 1' }],
      resultKey: 'ok',
    };

    rerender(
      <WidgetWrapper
        dashboardId="dashboard-1"
        widgetId="widget-1"
        chartType="topN"
        config={{ dataSource: topNDatasource.id, dataSourceParams: [switchParam] }}
        dataSource={topNDatasource}
        reloadVersion="1:0"
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('chart-renderer')).toBeTruthy();
    });
    expect(screen.queryByText(businessError)).toBeNull();
    expect(testState.fetchCompareData).toHaveBeenCalled();
    expect(testState.messageError).not.toHaveBeenCalled();
  });
});
