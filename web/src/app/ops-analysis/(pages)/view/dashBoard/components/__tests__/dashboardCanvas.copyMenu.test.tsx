import React, { createRef } from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

import DashboardCanvas from '../dashboardCanvas';
import type { DashboardLayoutItem } from '@/app/ops-analysis/types/dashBoard';

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

const widgetRuntimeRenderCount = { current: 0 };

vi.mock('@/app/ops-analysis/components/widgetDataRenderer', () => ({
  default: function WidgetRuntimeMock() {
    widgetRuntimeRenderCount.current += 1;
    return <div data-testid="widget-runtime" />;
  },
}));

vi.mock('gridstack', () => ({
  GridStack: {
    init: () => ({
      makeWidget: vi.fn(),
      update: vi.fn(),
      on: vi.fn(),
      off: vi.fn(),
      destroy: vi.fn(),
      engine: { nodes: [] },
    }),
  },
}));

const dataWidget: DashboardLayoutItem = {
  i: 'cpu',
  x: 0,
  y: 0,
  w: 4,
  h: 3,
  name: 'CPU',
  valueConfig: { chartType: 'line', dataSource: 7 },
};

const sceneWidget: DashboardLayoutItem = {
  i: 'topo',
  x: 0,
  y: 0,
  w: 4,
  h: 3,
  name: '网络拓扑',
  valueConfig: {
    chartType: 'networkStatusTopology',
    sceneWidgetType: 'networkStatusTopology',
  },
};

beforeAll(() => {
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
  widgetRuntimeRenderCount.current = 0;
  cleanup();
});

const renderCanvas = (
  layout: DashboardLayoutItem[],
  options: {
    isEditMode?: boolean;
    selectedDashboardLocked?: boolean;
    shareMode?: boolean;
  } = {},
) => {
  const scrollRootRef = createRef<HTMLDivElement | null>();
  scrollRootRef.current = document.createElement('div');
  return render(
    <DashboardCanvas
      loading={false}
      isEditMode={options.isEditMode ?? true}
      isDarkTheme={false}
      dashboardId={1}
      layout={layout}
      collapsedGroups={{}}
      chartTheme={{ panelBg: '#fff', panelBorderColor: '#eee' }}
      filterSearchVersion={0}
      namespaceSearchVersion={0}
      dashboardReloadVersion={0}
      widgetReloadVersions={{}}
      dataSourceResolver={() => undefined}
      appliedFilterValues={{}}
      appliedFilterDefinitions={[]}
      appliedNamespaceId={undefined}
      selectedDashboardLocked={options.selectedDashboardLocked}
      shareMode={options.shareMode}
      onLayoutChange={vi.fn()}
      onOpenAddModal={vi.fn()}
      onToggleCollapsedGroup={vi.fn()}
      onRenameGroup={vi.fn()}
      onRemoveGroup={vi.fn()}
      onDeleteEntireGroup={vi.fn()}
      onEditWidget={vi.fn()}
      onCopyWidget={vi.fn()}
      onDeleteWidget={vi.fn()}
      renderMode
      scrollRootRef={scrollRootRef}
    />,
  );
};

const openMoreMenu = async () => {
  const user = userEvent.setup();
  const more = await screen.findByRole('button', { name: 'common.more' });
  await user.click(more);
};

describe('DashboardCanvas copy menu', () => {
  it('includes 复制 between edit and delete for a data widget in edit mode', async () => {
    renderCanvas([dataWidget], { isEditMode: true });
    await openMoreMenu();
    const items = await screen.findAllByRole('menuitem');
    expect(items.map((item) => item.textContent)).toEqual([
      'common.edit',
      'common.copy',
      'common.delete',
    ]);
  });

  it('omits 复制 entirely for a networkStatusTopology scene widget', async () => {
    renderCanvas([sceneWidget], { isEditMode: true });
    await openMoreMenu();
    expect(await screen.findByText('common.edit')).toBeTruthy();
    expect(screen.queryByText('common.copy')).toBeNull();
    expect(screen.getByText('common.delete')).toBeTruthy();
    expect(screen.queryByRole('menuitem', { name: /common.copy/ })).toBeNull();
  });

  it('omits 复制 in view mode', async () => {
    renderCanvas([dataWidget], { isEditMode: false });
    await waitFor(() => {
      expect(screen.getByText('CPU')).toBeTruthy();
    });
    expect(screen.queryByRole('button', { name: 'common.more' })).toBeNull();
    expect(screen.queryByText('common.copy')).toBeNull();
  });

  it('omits 复制 in share mode', async () => {
    renderCanvas([dataWidget], { isEditMode: true, shareMode: true });
    await openMoreMenu();
    expect(await screen.findByText('common.edit')).toBeTruthy();
    expect(screen.queryByText('common.copy')).toBeNull();
    expect(screen.getByText('common.delete')).toBeTruthy();
  });

  it('omits 复制 on a builtin dashboard even if the ⋯ menu is open', async () => {
    renderCanvas([dataWidget], {
      isEditMode: true,
      selectedDashboardLocked: true,
    });
    await openMoreMenu();
    expect(await screen.findByText('common.edit')).toBeTruthy();
    expect(screen.queryByText('common.copy')).toBeNull();
    expect(screen.getByText('common.delete')).toBeTruthy();
  });
});

describe('DashboardCanvas overlay re-render isolation', () => {
  it('does not re-render widget runtime when parent overlay-like state changes', async () => {
    const scrollRootRef = createRef<HTMLDivElement | null>();
    scrollRootRef.current = document.createElement('div');
    const canvasProps = {
      loading: false,
      isEditMode: false,
      isDarkTheme: false,
      dashboardId: 1,
      layout: [dataWidget],
      collapsedGroups: {},
      chartTheme: { panelBg: '#fff', panelBorderColor: '#eee' },
      filterSearchVersion: 0,
      namespaceSearchVersion: 0,
      dashboardReloadVersion: 0,
      widgetReloadVersions: {},
      dataSourceResolver: () => undefined,
      appliedFilterValues: {},
      appliedFilterDefinitions: [],
      appliedNamespaceId: undefined as number | undefined,
      onLayoutChange: vi.fn(),
      onOpenAddModal: vi.fn(),
      onToggleCollapsedGroup: vi.fn(),
      onRenameGroup: vi.fn(),
      onRemoveGroup: vi.fn(),
      onDeleteEntireGroup: vi.fn(),
      onEditWidget: vi.fn(),
      onCopyWidget: vi.fn(),
      onDeleteWidget: vi.fn(),
      renderMode: true,
      scrollRootRef,
    };

    const Parent = ({ overlayOpen }: { overlayOpen: boolean }) => (
      <>
        <span data-testid="overlay-flag">{String(overlayOpen)}</span>
        <DashboardCanvas {...canvasProps} />
      </>
    );

    const { rerender } = render(<Parent overlayOpen={false} />);
    await waitFor(() => {
      expect(screen.getByText('CPU')).toBeTruthy();
    });
    const rendersAfterMount = widgetRuntimeRenderCount.current;
    expect(rendersAfterMount).toBeGreaterThan(0);

    rerender(<Parent overlayOpen={true} />);
    expect(screen.getByTestId('overlay-flag').textContent).toBe('true');
    expect(widgetRuntimeRenderCount.current).toBe(rendersAfterMount);
  });
});
