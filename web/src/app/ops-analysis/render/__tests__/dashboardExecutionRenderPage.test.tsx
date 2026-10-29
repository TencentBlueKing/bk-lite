import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';

import { DashboardRenderOpsAnalysisProvider } from '@/app/ops-analysis/context/common';
import { DashboardExecutionRenderPageContent } from '@/app/ops-analysis/render/execution/[executionId]/dashboardExecutionRenderPage';

const api = {
  getExecutionRenderInput: vi.fn(),
};

const testState = vi.hoisted(() => ({
  dataSourceLoadError: false,
  translate: (key: string) => key,
  request: {
    get: async (url: string) => {
      if (String(url).includes('data_source')) {
        if (testState.dataSourceLoadError) {
          throw new Error('data source lookup failed');
        }
        return [
          {
            id: 9,
            name: '告警源',
            required_app: 'alarm',
            hasAuth: true,
            params: [],
            chart_type: ['line'],
          },
          {
            id: 10,
            name: '外部源',
            required_app: null,
            hasAuth: true,
            params: [],
            chart_type: ['line'],
          },
        ];
      }
      return [];
    },
    post: async () => ({ results: [] as Array<{ widget_id: string; code: string }> }),
    put: async () => undefined,
    del: async () => undefined,
    patch: async () => undefined,
    isLoading: false,
  },
}));

vi.mock('next/navigation', () => ({
  usePathname: () => '/ops-analysis/render/execution/42',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: null, status: 'authenticated' }),
}));

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: testState.translate }),
}));

vi.mock('@/utils/request', () => ({
  default: () => testState.request,
}));

vi.mock('gridstack', () => ({
  GridStack: {
    init: () => ({
      makeWidget: vi.fn(),
      update: vi.fn(),
      on: vi.fn(),
      off: vi.fn(),
      destroy: vi.fn(),
      save: vi.fn(() => []),
      resizeToContent: vi.fn(),
      updateOptions: vi.fn(),
      enableMove: vi.fn(),
      enableResize: vi.fn(),
      engine: { nodes: [] },
    }),
  },
}));

vi.mock('@/app/ops-analysis/components/widgetDataRenderer', async () => {
  const ReactModule = await import('react');
  const { useOpsAnalysis } = await import('@/app/ops-analysis/context/common');
  return {
    default: function WidgetRuntime({
      widgetId,
      onRenderStatus,
    }: {
      widgetId: string;
      onRenderStatus?: (result: {
        widgetId: string;
        status: string;
        error?: string;
        errorCode?: string;
      }) => void;
    }) {
      const { canvasDataSourceLookupStatus } = useOpsAnalysis();
      ReactModule.useEffect(() => {
        if (
          canvasDataSourceLookupStatus === 'idle'
          || canvasDataSourceLookupStatus === 'loading'
        ) {
          onRenderStatus?.({ widgetId, status: 'loading' });
          return;
        }
        if (canvasDataSourceLookupStatus === 'error') {
          onRenderStatus?.({
            widgetId,
            status: 'failed',
            error: 'dashboard.dataSourceLoadFailed',
            errorCode: 'datasource_missing',
          });
          return;
        }
        onRenderStatus?.({ widgetId, status: 'ready' });
      }, [canvasDataSourceLookupStatus, onRenderStatus, widgetId]);
      return ReactModule.createElement('div', {
        'data-testid': `runtime-${widgetId}`,
      });
    },
  };
});

vi.mock('@/app/ops-analysis/api/dashboardSubscription', () => ({
  useDashboardSubscriptionApi: () => api,
}));

const layout = [
  {
    i: 'g-alarm',
    itemType: 'group',
    x: 0,
    y: 0,
    w: 24,
    h: 1,
    name: '告警组',
  },
  {
    i: 'w-alarm',
    itemType: 'widget',
    x: 0,
    y: 1,
    w: 8,
    h: 4,
    name: '告警图',
    groupId: 'g-alarm',
    valueConfig: { chartType: 'line', dataSource: 9 },
  },
  {
    i: 'g-open',
    itemType: 'group',
    x: 0,
    y: 10,
    w: 24,
    h: 1,
    name: '外部组',
  },
  {
    i: 'w-open',
    itemType: 'widget',
    x: 0,
    y: 11,
    w: 8,
    h: 4,
    name: '外部图',
    groupId: 'g-open',
    valueConfig: { chartType: 'line', dataSource: 10 },
  },
];

const renderInput = {
  execution_id: 42,
  authorized_app_names: ['cmdb'],
  input_snapshot: {
    dashboard_id: 8,
    creator_id: 'test',
    subscription_id: 3,
    filter_values: { environment: 'production' },
    created_at: '2026-07-29T00:00:00Z',
  },
  render_snapshot: {
    dashboard_id: 8,
    dashboard_name: '冻结仪表盘',
    dashboard_updated_at: '2026-07-29T00:00:00Z',
    view_sets: layout,
    filters: [],
    other: { title: '冻结标题' },
    widget_manifest: [
      { widget_id: 'w-alarm', widget_type: 'line', datasource_id: 9 },
      { widget_id: 'w-open', widget_type: 'line', datasource_id: 10 },
    ],
    created_at: '2026-07-29T00:00:01Z',
  },
};

const renderPage = () =>
  render(
    <DashboardRenderOpsAnalysisProvider selectedGroupId={1}>
      <DashboardExecutionRenderPageContent executionId={42} />
    </DashboardRenderOpsAnalysisProvider>,
  );

beforeEach(() => {
  testState.dataSourceLoadError = false;
  api.getExecutionRenderInput.mockResolvedValue(renderInput);
  vi.stubGlobal('ResizeObserver', class {
    observe() {}
    unobserve() {}
    disconnect() {}
  });
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
    return window.setTimeout(() => callback(0), 0) as unknown as number;
  });
  vi.stubGlobal('cancelAnimationFrame', (id: number) => {
    window.clearTimeout(id);
  });
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('DashboardExecutionRenderPageContent', () => {
  it('emits report-ready after a licensed group is omitted', async () => {
    const signals: Array<{ type?: string; widgets?: Array<{ widgetId: string }> }> = [];
    const onSignal = (event: Event) => {
      signals.push((event as CustomEvent).detail);
    };
    window.addEventListener('bk-dashboard-render', onSignal);

    renderPage();

    await waitFor(() => {
      const ready = signals.find((signal) => signal.type === 'report-ready');
      expect(ready?.widgets?.map((widget) => widget.widgetId)).toEqual(['w-open']);
    });
    expect(signals.filter((signal) => signal.type === 'report-ready')).toHaveLength(1);
    expect(signals.some((signal) =>
      signal.type === 'report-ready' && (signal.widgets?.length ?? 0) === 0,
    )).toBe(false);
    expect(signals.some((signal) =>
      signal.widgets?.some((widget) => widget.widgetId === 'w-alarm'),
    )).toBe(false);
    window.removeEventListener('bk-dashboard-render', onSignal);
  });

  it('publishes report-failed when render input cannot be loaded', async () => {
    api.getExecutionRenderInput.mockRejectedValueOnce(new Error('forbidden'));
    const signals: unknown[] = [];
    window.addEventListener('bk-dashboard-render', (event) => {
      signals.push((event as CustomEvent).detail);
    });

    renderPage();

    await waitFor(() => {
      expect(signals).toEqual([
        {
          type: 'report-failed',
          dashboardId: '42',
          widgets: [],
          error: 'Render input load failed',
        },
      ]);
    });
  });

  it('publishes report-failed when authorized apps are missing instead of rendering a blank omit', async () => {
    api.getExecutionRenderInput.mockResolvedValueOnce({
      ...renderInput,
      authorized_app_names: undefined,
    });
    const signals: unknown[] = [];
    window.addEventListener('bk-dashboard-render', (event) => {
      signals.push((event as CustomEvent).detail);
    });

    renderPage();

    await waitFor(() => {
      expect(signals).toEqual([
        {
          type: 'report-failed',
          dashboardId: '42',
          widgets: [],
          error: 'Render input missing authorized apps',
        },
      ]);
    });
    expect(document.querySelector('[data-testid="canvas-probe"]')).toBeNull();
  });

  it('mounts the grid and reports failed when canvas data source lookup errors', async () => {
    testState.dataSourceLoadError = true;
    const signals: Array<{
      type?: string;
      errorCode?: string;
      widgets?: Array<{ widgetId: string; status?: string }>;
    }> = [];
    const onSignal = (event: Event) => {
      signals.push((event as CustomEvent).detail);
    };
    window.addEventListener('bk-dashboard-render', onSignal);

    const { container } = renderPage();

    await waitFor(() => {
      expect(screen.getByTestId('runtime-w-open')).toBeTruthy();
      expect(screen.getByTestId('runtime-w-alarm')).toBeTruthy();
    });
    expect(container.querySelector('[data-module-license-canvas-empty]')).toBeNull();

    await waitFor(() => {
      const failed = signals.find((signal) => signal.type === 'report-failed');
      expect(failed?.errorCode).toBe('datasource_missing');
      expect(failed?.widgets?.map((widget) => widget.widgetId).sort()).toEqual([
        'w-alarm',
        'w-open',
      ]);
    });

    window.removeEventListener('bk-dashboard-render', onSignal);
  });

  it('omits unauthorized topology on lookup error and still reports failed for mounted charts', async () => {
    testState.dataSourceLoadError = true;
    api.getExecutionRenderInput.mockResolvedValue({
      ...renderInput,
      authorized_app_names: ['monitor'],
      render_snapshot: {
        ...renderInput.render_snapshot,
        view_sets: [
          {
            i: 'g-topo',
            itemType: 'group',
            x: 0,
            y: 0,
            w: 24,
            h: 1,
            name: '拓扑组',
          },
          {
            i: 'w-topo',
            itemType: 'widget',
            x: 0,
            y: 1,
            w: 8,
            h: 4,
            name: '网络拓扑',
            groupId: 'g-topo',
            valueConfig: {
              chartType: 'networkStatusTopology',
              sceneWidgetType: 'networkStatusTopology',
            },
          },
          {
            i: 'g-open',
            itemType: 'group',
            x: 0,
            y: 10,
            w: 24,
            h: 1,
            name: '外部组',
          },
          {
            i: 'w-open',
            itemType: 'widget',
            x: 0,
            y: 11,
            w: 8,
            h: 4,
            name: '外部图',
            groupId: 'g-open',
            valueConfig: { chartType: 'line', dataSource: 10 },
          },
        ],
        widget_manifest: [
          { widget_id: 'w-topo', widget_type: 'networkStatusTopology' },
          { widget_id: 'w-open', widget_type: 'line', datasource_id: 10 },
        ],
      },
    });
    const signals: Array<{
      type?: string;
      errorCode?: string;
      widgets?: Array<{ widgetId: string }>;
    }> = [];
    const onSignal = (event: Event) => {
      signals.push((event as CustomEvent).detail);
    };
    window.addEventListener('bk-dashboard-render', onSignal);

    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId('runtime-w-open')).toBeTruthy();
    });
    expect(screen.queryByTestId('runtime-w-topo')).toBeNull();
    expect(document.querySelector('[data-module-license-canvas-empty]')).toBeNull();

    await waitFor(() => {
      const failed = signals.find((signal) => signal.type === 'report-failed');
      expect(failed?.errorCode).toBe('datasource_missing');
      expect(failed?.widgets?.map((widget) => widget.widgetId)).toEqual(['w-open']);
    });

    window.removeEventListener('bk-dashboard-render', onSignal);
  });
});
