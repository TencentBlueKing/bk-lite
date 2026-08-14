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
    loading,
    rawData,
    onReady,
  }: {
    loading?: boolean;
    rawData?: unknown;
    onReady?: (hasData?: boolean) => void;
  }) {
    React.useEffect(() => {
      onReady?.(Boolean(rawData));
    }, [onReady, rawData]);
    return (
      <div>
        {loading ? <span data-testid="chart-loading">loading</span> : null}
        {rawData ? (
          <div data-testid="chart-renderer">{JSON.stringify(rawData)}</div>
        ) : null}
      </div>
    );
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
  it('keeps the initial request valid through React StrictMode effect replay', async () => {
    testState.fetchCompareData.mockResolvedValue({
      currentData: [{ name: 'strict', value: 1 }],
      baselineData: null,
    });

    render(
      <React.StrictMode>
        <WidgetWrapper
          dashboardId="dashboard-1"
          widgetId="widget-1"
          chartType="pie"
          config={{ dataSource: pieDatasource.id }}
          dataSource={pieDatasource}
        />
      </React.StrictMode>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('chart-renderer').textContent).toContain('strict');
    });
    expect(testState.fetchCompareData).toHaveBeenCalledTimes(1);
  });

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

  it('keeps previous data and skips loading on a failed periodic refresh', async () => {
    testState.fetchCompareData
      .mockResolvedValueOnce({
        currentData: [{ name: 'A', value: 1 }],
        baselineData: null,
      })
      .mockRejectedValueOnce(new HandledRequestError('周期刷新失败'));

    const { rerender } = render(
      <WidgetWrapper
        dashboardId="dashboard-1"
        widgetId="widget-1"
        chartType="pie"
        config={{ dataSource: pieDatasource.id }}
        dataSource={pieDatasource}
        reloadVersion="0:0"
        refreshCause="initial"
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('chart-renderer')).toBeTruthy();
    });

    rerender(
      <WidgetWrapper
        dashboardId="dashboard-1"
        widgetId="widget-1"
        chartType="pie"
        config={{ dataSource: pieDatasource.id }}
        dataSource={pieDatasource}
        reloadVersion="1:0"
        refreshCause="periodic"
      />,
    );

    await waitFor(() => {
      expect(testState.fetchCompareData).toHaveBeenCalledTimes(2);
    });
    expect(screen.getByTestId('chart-renderer')).toBeTruthy();
    expect(screen.queryByTestId('chart-loading')).toBeNull();
    expect(screen.queryByText('周期刷新失败')).toBeNull();
  });

  it('skips a later periodic tick while the previous interval request is still in flight', async () => {
    let resolvePeriodic: ((value: {
      currentData: Array<{ name: string; value: number }>;
      baselineData: null;
    }) => void) | undefined;
    testState.fetchCompareData
      .mockResolvedValueOnce({
        currentData: [{ name: 'A', value: 1 }],
        baselineData: null,
      })
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolvePeriodic = resolve;
          }),
      );

    const { rerender } = render(
      <WidgetWrapper
        dashboardId="dashboard-1"
        widgetId="widget-1"
        chartType="pie"
        config={{ dataSource: pieDatasource.id }}
        dataSource={pieDatasource}
        reloadVersion="0:0"
        refreshCause="initial"
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('chart-renderer')).toBeTruthy();
    });

    rerender(
      <WidgetWrapper
        dashboardId="dashboard-1"
        widgetId="widget-1"
        chartType="pie"
        config={{ dataSource: pieDatasource.id }}
        dataSource={pieDatasource}
        reloadVersion="1:0"
        refreshCause="periodic"
      />,
    );

    await waitFor(() => {
      expect(testState.fetchCompareData).toHaveBeenCalledTimes(2);
    });

    rerender(
      <WidgetWrapper
        dashboardId="dashboard-1"
        widgetId="widget-1"
        chartType="pie"
        config={{ dataSource: pieDatasource.id }}
        dataSource={pieDatasource}
        reloadVersion="2:0"
        refreshCause="periodic"
      />,
    );

    await Promise.resolve();
    expect(testState.fetchCompareData).toHaveBeenCalledTimes(2);

    resolvePeriodic?.({
      currentData: [{ name: 'B', value: 2 }],
      baselineData: null,
    });
    await waitFor(() => {
      expect(screen.getByTestId('chart-renderer')).toBeTruthy();
    });
  });

  it('skips a silent tick while a manual request is in flight and still accepts the manual success', async () => {
    let resolveManual: ((value: {
      currentData: Array<{ name: string; value: number }>;
      baselineData: null;
    }) => void) | undefined;
    testState.fetchCompareData
      .mockResolvedValueOnce({
        currentData: [{ name: 'A', value: 1 }],
        baselineData: null,
      })
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveManual = resolve;
          }),
      );

    const { rerender } = render(
      <WidgetWrapper
        dashboardId="dashboard-1"
        widgetId="widget-1"
        chartType="pie"
        config={{ dataSource: pieDatasource.id }}
        dataSource={pieDatasource}
        reloadVersion="0:0"
        refreshCause="initial"
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('chart-renderer').textContent).toContain('A');
    });

    rerender(
      <WidgetWrapper
        dashboardId="dashboard-1"
        widgetId="widget-1"
        chartType="pie"
        config={{ dataSource: pieDatasource.id }}
        dataSource={pieDatasource}
        reloadVersion="1:0"
        refreshCause="manual"
      />,
    );

    await waitFor(() => {
      expect(testState.fetchCompareData).toHaveBeenCalledTimes(2);
    });
    expect(screen.getByTestId('chart-loading')).toBeTruthy();

    rerender(
      <WidgetWrapper
        dashboardId="dashboard-1"
        widgetId="widget-1"
        chartType="pie"
        config={{ dataSource: pieDatasource.id }}
        dataSource={pieDatasource}
        reloadVersion="2:0"
        refreshCause="periodic"
      />,
    );
    await Promise.resolve();
    expect(testState.fetchCompareData).toHaveBeenCalledTimes(2);

    rerender(
      <WidgetWrapper
        dashboardId="dashboard-1"
        widgetId="widget-1"
        chartType="pie"
        config={{ dataSource: pieDatasource.id }}
        dataSource={pieDatasource}
        reloadVersion="3:0"
        refreshCause="visibility"
      />,
    );
    await Promise.resolve();
    expect(testState.fetchCompareData).toHaveBeenCalledTimes(2);

    resolveManual?.({
      currentData: [{ name: 'Manual', value: 3 }],
      baselineData: null,
    });
    await waitFor(() => {
      expect(screen.getByTestId('chart-renderer').textContent).toContain('Manual');
    });
    expect(screen.queryByTestId('chart-loading')).toBeNull();
  });

  it('starts newer active requests without waiting for stale orchestration to settle', async () => {
    let resolveA: ((value: {
      currentData: Array<{ name: string; value: number }>;
      baselineData: null;
    }) => void) | undefined;
    testState.fetchCompareData
      .mockImplementationOnce(
        () => new Promise((resolve) => {
          resolveA = resolve;
        }),
      )
      .mockResolvedValueOnce({
        currentData: [{ name: 'B', value: 2 }],
        baselineData: null,
      })
      .mockResolvedValueOnce({
        currentData: [{ name: 'C', value: 3 }],
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
        refreshCause="initial"
      />,
    );
    await waitFor(() => expect(testState.fetchCompareData).toHaveBeenCalledTimes(1));

    rerender(
      <WidgetWrapper
        dashboardId="dashboard-1"
        widgetId="widget-1"
        chartType="pie"
        config={{ dataSource: pieDatasource.id }}
        dataSource={pieDatasource}
        reloadVersion="1:0"
        refreshCause="manual"
      />,
    );
    await waitFor(() => expect(testState.fetchCompareData).toHaveBeenCalledTimes(2));

    rerender(
      <WidgetWrapper
        dashboardId="dashboard-1"
        widgetId="widget-1"
        chartType="pie"
        config={{ dataSource: pieDatasource.id }}
        dataSource={pieDatasource}
        reloadVersion="2:0"
        refreshCause="manual"
      />,
    );
    await waitFor(() => expect(testState.fetchCompareData).toHaveBeenCalledTimes(3));
    expect(screen.getByTestId('chart-renderer').textContent).toContain('C');

    resolveA?.({
      currentData: [{ name: 'A', value: 1 }],
      baselineData: null,
    });
    await Promise.resolve();
    expect(screen.getByTestId('chart-renderer').textContent).toContain('C');
  });

  it('waits for activation and refetches only when the required version changed offscreen', async () => {
    testState.fetchCompareData.mockResolvedValue({
      currentData: [{ name: 'active', value: 1 }],
      baselineData: null,
    });
    const props = {
      dashboardId: 'dashboard-1',
      widgetId: 'widget-1',
      chartType: 'pie',
      config: { dataSource: pieDatasource.id },
      dataSource: pieDatasource,
      refreshCause: 'initial' as const,
    };
    const { rerender } = render(
      <WidgetWrapper {...props} reloadVersion="0:0" runtimeActive={false} />,
    );
    expect(testState.fetchCompareData).not.toHaveBeenCalled();

    rerender(<WidgetWrapper {...props} reloadVersion="0:0" runtimeActive />);
    await waitFor(() => expect(testState.fetchCompareData).toHaveBeenCalledTimes(1));

    rerender(<WidgetWrapper {...props} reloadVersion="0:0" runtimeActive={false} />);
    rerender(<WidgetWrapper {...props} reloadVersion="0:0" runtimeActive />);
    await Promise.resolve();
    expect(testState.fetchCompareData).toHaveBeenCalledTimes(1);

    rerender(<WidgetWrapper {...props} reloadVersion="1:0" runtimeActive={false} />);
    await Promise.resolve();
    expect(testState.fetchCompareData).toHaveBeenCalledTimes(1);
    rerender(<WidgetWrapper {...props} reloadVersion="1:0" runtimeActive />);
    await waitFor(() => expect(testState.fetchCompareData).toHaveBeenCalledTimes(2));
  });

  it('skips a silent tick while a manual request is in flight and still shows the manual error', async () => {
    let rejectManual: ((reason?: unknown) => void) | undefined;
    testState.fetchCompareData
      .mockResolvedValueOnce({
        currentData: [{ name: 'A', value: 1 }],
        baselineData: null,
      })
      .mockImplementationOnce(
        () =>
          new Promise((_, reject) => {
            rejectManual = reject;
          }),
      );

    const { rerender } = render(
      <WidgetWrapper
        dashboardId="dashboard-1"
        widgetId="widget-1"
        chartType="pie"
        config={{ dataSource: pieDatasource.id }}
        dataSource={pieDatasource}
        reloadVersion="0:0"
        refreshCause="initial"
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('chart-renderer')).toBeTruthy();
    });

    rerender(
      <WidgetWrapper
        dashboardId="dashboard-1"
        widgetId="widget-1"
        chartType="pie"
        config={{ dataSource: pieDatasource.id }}
        dataSource={pieDatasource}
        reloadVersion="1:0"
        refreshCause="manual"
      />,
    );
    await waitFor(() => {
      expect(testState.fetchCompareData).toHaveBeenCalledTimes(2);
    });

    rerender(
      <WidgetWrapper
        dashboardId="dashboard-1"
        widgetId="widget-1"
        chartType="pie"
        config={{ dataSource: pieDatasource.id }}
        dataSource={pieDatasource}
        reloadVersion="2:0"
        refreshCause="visibility"
      />,
    );
    await Promise.resolve();
    expect(testState.fetchCompareData).toHaveBeenCalledTimes(2);

    rejectManual?.(new HandledRequestError('手动刷新失败'));
    await waitFor(() => {
      expect(screen.getByText('手动刷新失败')).toBeTruthy();
    });
    expect(screen.queryByTestId('chart-renderer')).toBeNull();
    expect(testState.messageError).not.toHaveBeenCalled();
  });

  it('lets a manual request become latest while a silent request is in flight', async () => {
    let resolveSilent: ((value: {
      currentData: Array<{ name: string; value: number }>;
      baselineData: null;
    }) => void) | undefined;
    let resolveManual: ((value: {
      currentData: Array<{ name: string; value: number }>;
      baselineData: null;
    }) => void) | undefined;
    testState.fetchCompareData
      .mockResolvedValueOnce({
        currentData: [{ name: 'A', value: 1 }],
        baselineData: null,
      })
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveSilent = resolve;
          }),
      )
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveManual = resolve;
          }),
      );

    const { rerender } = render(
      <WidgetWrapper
        dashboardId="dashboard-1"
        widgetId="widget-1"
        chartType="pie"
        config={{ dataSource: pieDatasource.id }}
        dataSource={pieDatasource}
        reloadVersion="0:0"
        refreshCause="initial"
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId('chart-renderer').textContent).toContain('A');
    });

    rerender(
      <WidgetWrapper
        dashboardId="dashboard-1"
        widgetId="widget-1"
        chartType="pie"
        config={{ dataSource: pieDatasource.id }}
        dataSource={pieDatasource}
        reloadVersion="1:0"
        refreshCause="periodic"
      />,
    );
    await waitFor(() => {
      expect(testState.fetchCompareData).toHaveBeenCalledTimes(2);
    });
    expect(screen.queryByTestId('chart-loading')).toBeNull();

    rerender(
      <WidgetWrapper
        dashboardId="dashboard-1"
        widgetId="widget-1"
        chartType="pie"
        config={{ dataSource: pieDatasource.id }}
        dataSource={pieDatasource}
        reloadVersion="2:0"
        refreshCause="manual"
      />,
    );
    await waitFor(() => {
      expect(testState.fetchCompareData).toHaveBeenCalledTimes(3);
    });

    resolveSilent?.({
      currentData: [{ name: 'Stale', value: 9 }],
      baselineData: null,
    });
    await Promise.resolve();
    expect(screen.getByTestId('chart-renderer').textContent).toContain('A');
    expect(screen.getByTestId('chart-loading')).toBeTruthy();

    resolveManual?.({
      currentData: [{ name: 'Latest', value: 4 }],
      baselineData: null,
    });
    await waitFor(() => {
      expect(screen.getByTestId('chart-renderer').textContent).toContain('Latest');
    });
    expect(screen.queryByText('Stale')).toBeNull();
    expect(screen.queryByTestId('chart-loading')).toBeNull();
  });

  it('skips the next periodic tick when an older silent request is still in flight after a newer manual completes', async () => {
    let resolveSilent: ((value: {
      currentData: Array<{ name: string; value: number }>;
      baselineData: null;
    }) => void) | undefined;
    let resolveManual: ((value: {
      currentData: Array<{ name: string; value: number }>;
      baselineData: null;
    }) => void) | undefined;
    testState.fetchCompareData
      .mockResolvedValueOnce({
        currentData: [{ name: 'A', value: 1 }],
        baselineData: null,
      })
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveSilent = resolve;
          }),
      )
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveManual = resolve;
          }),
      );

    const { rerender } = render(
      <WidgetWrapper
        dashboardId="dashboard-1"
        widgetId="widget-1"
        chartType="pie"
        config={{ dataSource: pieDatasource.id }}
        dataSource={pieDatasource}
        reloadVersion="0:0"
        refreshCause="initial"
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId('chart-renderer').textContent).toContain('A');
    });

    rerender(
      <WidgetWrapper
        dashboardId="dashboard-1"
        widgetId="widget-1"
        chartType="pie"
        config={{ dataSource: pieDatasource.id }}
        dataSource={pieDatasource}
        reloadVersion="1:0"
        refreshCause="periodic"
      />,
    );
    await waitFor(() => {
      expect(testState.fetchCompareData).toHaveBeenCalledTimes(2);
    });

    rerender(
      <WidgetWrapper
        dashboardId="dashboard-1"
        widgetId="widget-1"
        chartType="pie"
        config={{ dataSource: pieDatasource.id }}
        dataSource={pieDatasource}
        reloadVersion="2:0"
        refreshCause="manual"
      />,
    );
    await waitFor(() => {
      expect(testState.fetchCompareData).toHaveBeenCalledTimes(3);
    });

    resolveManual?.({
      currentData: [{ name: 'Latest', value: 4 }],
      baselineData: null,
    });
    await waitFor(() => {
      expect(screen.getByTestId('chart-renderer').textContent).toContain('Latest');
    });
    expect(screen.queryByTestId('chart-loading')).toBeNull();

    rerender(
      <WidgetWrapper
        dashboardId="dashboard-1"
        widgetId="widget-1"
        chartType="pie"
        config={{ dataSource: pieDatasource.id }}
        dataSource={pieDatasource}
        reloadVersion="3:0"
        refreshCause="periodic"
      />,
    );
    await Promise.resolve();
    expect(testState.fetchCompareData).toHaveBeenCalledTimes(3);

    resolveSilent?.({
      currentData: [{ name: 'Stale', value: 9 }],
      baselineData: null,
    });
    await Promise.resolve();
    expect(screen.getByTestId('chart-renderer').textContent).toContain('Latest');
    expect(screen.queryByText('Stale')).toBeNull();
  });

  it('skips a visibility tick when an older manual request is still in flight after a newer manual completes', async () => {
    let resolveOlderManual: ((value: {
      currentData: Array<{ name: string; value: number }>;
      baselineData: null;
    }) => void) | undefined;
    let resolveNewerManual: ((value: {
      currentData: Array<{ name: string; value: number }>;
      baselineData: null;
    }) => void) | undefined;
    testState.fetchCompareData
      .mockResolvedValueOnce({
        currentData: [{ name: 'A', value: 1 }],
        baselineData: null,
      })
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveOlderManual = resolve;
          }),
      )
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveNewerManual = resolve;
          }),
      );

    const { rerender } = render(
      <WidgetWrapper
        dashboardId="dashboard-1"
        widgetId="widget-1"
        chartType="pie"
        config={{ dataSource: pieDatasource.id }}
        dataSource={pieDatasource}
        reloadVersion="0:0"
        refreshCause="initial"
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId('chart-renderer').textContent).toContain('A');
    });

    rerender(
      <WidgetWrapper
        dashboardId="dashboard-1"
        widgetId="widget-1"
        chartType="pie"
        config={{ dataSource: pieDatasource.id }}
        dataSource={pieDatasource}
        reloadVersion="1:0"
        refreshCause="manual"
      />,
    );
    await waitFor(() => {
      expect(testState.fetchCompareData).toHaveBeenCalledTimes(2);
    });

    rerender(
      <WidgetWrapper
        dashboardId="dashboard-1"
        widgetId="widget-1"
        chartType="pie"
        config={{ dataSource: pieDatasource.id }}
        dataSource={pieDatasource}
        reloadVersion="2:0"
        refreshCause="manual"
      />,
    );
    await waitFor(() => {
      expect(testState.fetchCompareData).toHaveBeenCalledTimes(3);
    });

    resolveNewerManual?.({
      currentData: [{ name: 'Latest', value: 4 }],
      baselineData: null,
    });
    await waitFor(() => {
      expect(screen.getByTestId('chart-renderer').textContent).toContain('Latest');
    });

    rerender(
      <WidgetWrapper
        dashboardId="dashboard-1"
        widgetId="widget-1"
        chartType="pie"
        config={{ dataSource: pieDatasource.id }}
        dataSource={pieDatasource}
        reloadVersion="3:0"
        refreshCause="visibility"
      />,
    );
    await Promise.resolve();
    expect(testState.fetchCompareData).toHaveBeenCalledTimes(3);

    resolveOlderManual?.({
      currentData: [{ name: 'Stale', value: 9 }],
      baselineData: null,
    });
    await Promise.resolve();
    expect(screen.getByTestId('chart-renderer').textContent).toContain('Latest');
    expect(screen.queryByText('Stale')).toBeNull();
  });

  it('does not skip another widget while one widget request is in flight', async () => {
    const secondDatasource: DatasourceItem = {
      ...pieDatasource,
      id: 43,
      name: 'Other pie',
    };
    let resolveSlowManual: ((value: {
      currentData: Array<{ name: string; value: number }>;
      baselineData: null;
    }) => void) | undefined;
    const callsBySource: number[] = [];
    testState.fetchCompareData.mockImplementation((input: { dataSourceId?: number }) => {
      callsBySource.push(input.dataSourceId ?? -1);
      const callCountForSource = callsBySource.filter((id) => id === input.dataSourceId).length;
      if (input.dataSourceId === pieDatasource.id && callCountForSource === 2) {
        return new Promise((resolve) => {
          resolveSlowManual = resolve;
        });
      }
      const name = input.dataSourceId === pieDatasource.id ? 'Slow' : 'Other';
      return Promise.resolve({
        currentData: [{ name, value: callCountForSource }],
        baselineData: null,
      });
    });

    const { rerender } = render(
      <>
        <WidgetWrapper
          dashboardId="dashboard-1"
          widgetId="widget-slow"
          chartType="pie"
          config={{ dataSource: pieDatasource.id }}
          dataSource={pieDatasource}
          reloadVersion="0:0"
          refreshCause="initial"
        />
        <WidgetWrapper
          dashboardId="dashboard-1"
          widgetId="widget-fast"
          chartType="pie"
          config={{ dataSource: secondDatasource.id }}
          dataSource={secondDatasource}
          reloadVersion="0:0"
          refreshCause="initial"
        />
      </>,
    );

    await waitFor(() => {
      expect(screen.getByText(/Slow/)).toBeTruthy();
      expect(screen.getByText(/Other/)).toBeTruthy();
    });
    expect(testState.fetchCompareData).toHaveBeenCalledTimes(2);

    rerender(
      <>
        <WidgetWrapper
          dashboardId="dashboard-1"
          widgetId="widget-slow"
          chartType="pie"
          config={{ dataSource: pieDatasource.id }}
          dataSource={pieDatasource}
          reloadVersion="1:0"
          refreshCause="manual"
        />
        <WidgetWrapper
          dashboardId="dashboard-1"
          widgetId="widget-fast"
          chartType="pie"
          config={{ dataSource: secondDatasource.id }}
          dataSource={secondDatasource}
          reloadVersion="1:0"
          refreshCause="manual"
        />
      </>,
    );

    await waitFor(() => {
      expect(testState.fetchCompareData).toHaveBeenCalledTimes(4);
    });

    rerender(
      <>
        <WidgetWrapper
          dashboardId="dashboard-1"
          widgetId="widget-slow"
          chartType="pie"
          config={{ dataSource: pieDatasource.id }}
          dataSource={pieDatasource}
          reloadVersion="2:0"
          refreshCause="periodic"
        />
        <WidgetWrapper
          dashboardId="dashboard-1"
          widgetId="widget-fast"
          chartType="pie"
          config={{ dataSource: secondDatasource.id }}
          dataSource={secondDatasource}
          reloadVersion="2:0"
          refreshCause="periodic"
        />
      </>,
    );

    await waitFor(() => {
      expect(testState.fetchCompareData).toHaveBeenCalledTimes(5);
    });
    expect(callsBySource.filter((id) => id === pieDatasource.id)).toHaveLength(2);
    expect(callsBySource.filter((id) => id === secondDatasource.id)).toHaveLength(3);

    resolveSlowManual?.({
      currentData: [{ name: 'SlowManual', value: 9 }],
      baselineData: null,
    });
    await waitFor(() => {
      expect(screen.getByText(/SlowManual/)).toBeTruthy();
      expect(screen.getByText(/Other/)).toBeTruthy();
    });
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
