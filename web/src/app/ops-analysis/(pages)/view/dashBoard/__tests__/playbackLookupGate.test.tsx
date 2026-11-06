// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { DashboardRenderOpsAnalysisProvider, useOpsAnalysis } from '@/app/ops-analysis/context/common';
import { PlaybackInitialDetailProvider } from '@/app/ops-analysis/context/playbackInitialDetail';
import type { DirItem } from '@/app/ops-analysis/types';

const translate = (key: string) => key;

const testState = vi.hoisted(() => {
  const state = {
    detailRequests: [] as string[],
    dataSourceRequests: [] as string[],
    client: {
      get: async () => [] as unknown,
      post: async () => ({}),
      put: async () => ({}),
      patch: async () => ({}),
      del: async () => ({}),
      isLoading: false,
    } as {
      get: (url: string, config?: { params?: { ids?: string } }) => Promise<unknown>;
      post: () => Promise<unknown>;
      put: () => Promise<unknown>;
      patch: () => Promise<unknown>;
      del: () => Promise<unknown>;
      isLoading: boolean;
    },
  };
  state.client.get = async (url: string, config?: { params?: { ids?: string } }) => {
    const target = `${String(url)}?ids=${config?.params?.ids ?? ''}`;
    if (target.includes('data_source')) {
      state.dataSourceRequests.push(target);
      return [
        {
          id: 9,
          name: '告警源',
          required_app: null,
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
    state.detailRequests.push(target);
    return [];
  };
  return state;
});

vi.mock('next/navigation', () => ({
  usePathname: () => '/ops-analysis',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: { user: { id: 'u1' } }, status: 'authenticated' }),
}));

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: translate }),
}));

vi.mock('@/utils/request', () => ({
  default: () => testState.client,
}));

vi.mock('@/app/ops-analysis/components/widgetSelector', () => ({
  default: () => null,
}));

vi.mock('@/app/ops-analysis/components/widgetConfig', () => ({
  default: () => null,
}));

vi.mock('@/hooks/usePermissions', () => ({
  default: () => ({ hasPermission: () => true }),
}));

vi.mock('@/app/ops-analysis/hooks/useDashboardModuleAccess', () => ({
  useDashboardModuleAccess: () => ({
    authorizedAppNames: ['ops-analysis'],
    appAccessReady: true,
  }),
  useDashboardSelectedGroup: () => ({ id: 1, name: '默认组' }),
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

vi.mock('@/app/ops-analysis/components/widgetDataRenderer', () => ({
  default: ({ widgetId }: { widgetId: string }) => (
    <div data-testid={`runtime-${widgetId}`} />
  ),
}));

import Dashboard from '@/app/ops-analysis/(pages)/view/dashBoard';

const widget = (id: string, dataSource: number) => ({
  i: id,
  itemType: 'widget' as const,
  x: 0,
  y: 0,
  w: 8,
  h: 4,
  name: id,
  valueConfig: { chartType: 'line', dataSource },
});

const dashboardItem = (id: number): DirItem => ({
  id: `dashboard_${id}`,
  data_id: String(id),
  name: `盘${id}`,
  type: 'dashboard',
});

const LookupProbe = () => {
  const { canvasDataSourceLookupStatus } = useOpsAnalysis();
  return <div data-testid="canvas-lookup-status">{canvasDataSourceLookupStatus}</div>;
};

const renderPlayback = (canvasId: number, dataSource: number) => render(
  <DashboardRenderOpsAnalysisProvider selectedGroupId={1}>
    <PlaybackInitialDetailProvider
      value={{
        resourceType: 'dashboard',
        canvasId,
        detail: {
          view_sets: [widget(`w-${canvasId}`, dataSource)],
          filters: [],
          other: { title: `盘${canvasId}` },
        },
      }}
    >
      <LookupProbe />
      <Dashboard selectedDashboard={dashboardItem(canvasId)} playbackMode />
    </PlaybackInitialDetailProvider>
  </DashboardRenderOpsAnalysisProvider>,
);

beforeEach(() => {
  testState.detailRequests.length = 0;
  testState.dataSourceRequests.length = 0;
  vi.stubGlobal('ResizeObserver', class {
    observe() {}
    unobserve() {}
    disconnect() {}
  });
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => (
    window.setTimeout(() => callback(0), 0) as unknown as number
  ));
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

describe('仪表盘轮播缓存命中离开加载门', () => {
  it('种子详情同步铺上后，lookup 复位不会把已完成的数据源代数丢掉', async () => {
    const view = renderPlayback(7, 9);

    await waitFor(() => {
      expect(screen.getByTestId('canvas-lookup-status').textContent).toBe('success');
      expect(view.container.querySelector('.ant-spin-lg')).toBeNull();
      expect(view.container.querySelector('.grid-stack')).toBeTruthy();
    });
    expect(view.container.textContent).toContain('盘7');
    expect(testState.detailRequests.some((url) => url.includes('/dashboard/'))).toBe(false);
    expect(testState.dataSourceRequests.some((url) => url.includes('9'))).toBe(true);

    view.rerender(
      <DashboardRenderOpsAnalysisProvider selectedGroupId={1}>
        <PlaybackInitialDetailProvider
          value={{
            resourceType: 'dashboard',
            canvasId: 8,
            detail: {
              view_sets: [widget('w-8', 10)],
              filters: [],
              other: { title: '下一盘' },
            },
          }}
        >
          <LookupProbe />
          <Dashboard selectedDashboard={dashboardItem(8)} playbackMode />
        </PlaybackInitialDetailProvider>
      </DashboardRenderOpsAnalysisProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('canvas-lookup-status').textContent).toBe('success');
      expect(view.container.textContent).toContain('盘8');
      expect(view.container.querySelector('.ant-spin-lg')).toBeNull();
      expect(view.container.querySelector('.grid-stack')).toBeTruthy();
    });
    expect(view.container.textContent).not.toContain('盘7');
    expect(testState.dataSourceRequests.some((url) => url.includes('10'))).toBe(true);
    expect(testState.detailRequests.some((url) => url.includes('/dashboard/'))).toBe(false);
  });
});
