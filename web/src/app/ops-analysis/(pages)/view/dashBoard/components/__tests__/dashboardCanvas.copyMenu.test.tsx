import React, { createRef } from 'react';
import '@ant-design/v5-patch-for-react-19';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

import { ShareModeProvider } from '@/app/ops-analysis/context/shareMode';
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
  vi.stubGlobal('ResizeObserver', class {
    observe() {}
    unobserve() {}
    disconnect() {}
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
  widgetRuntimeRenderCount.current = 0;
  cleanup();
});

const renderCanvas = (
  layout: DashboardLayoutItem[],
  options: {
    isEditMode?: boolean;
    selectedDashboardLocked?: boolean;
    shareMode?: boolean;
    renderMode?: boolean;
    isFullscreen?: boolean;
    pdfExportPreparing?: boolean;
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
      isFullscreen={options.isFullscreen}
      onLayoutChange={vi.fn()}
      onOpenAddModal={vi.fn()}
      onToggleCollapsedGroup={vi.fn()}
      onRenameGroup={vi.fn()}
      onRemoveGroup={vi.fn()}
      onDeleteEntireGroup={vi.fn()}
      onEditWidget={vi.fn()}
      onCopyWidget={vi.fn()}
      onDeleteWidget={vi.fn()}
      renderMode={options.renderMode ?? true}
      pdfExportPreparing={options.pdfExportPreparing}
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

  it('shows a hover-only csv export icon in the title row for a line chart in view mode and hides it for unsupported charts', async () => {
    renderCanvas([dataWidget], { isEditMode: false, renderMode: false });
    const button = await screen.findByRole('button', { name: 'dashboard.exportCsv' });
    expect(button.getAttribute('data-csv-export-hover')).toBe('true');
    expect(button.getAttribute('data-export-hidden')).toBe('true');
    expect(button.className).toContain('opacity-0');
    expect(button.className).toContain('shrink-0');
    expect(button.className).toContain('cursor-pointer');
    expect(button.className).not.toContain('absolute');
    fireEvent.mouseEnter(button);
    const tooltip = await screen.findByRole('tooltip');
    expect(tooltip.textContent).toBe('dashboard.exportCsv');
    expect(button.closest('.widget')?.contains(tooltip)).toBe(false);
    const header = button.closest('.widget-header');
    const slot = header?.querySelector('.overflow-x-auto');
    expect(slot).toBeTruthy();
    expect(slot!.compareDocumentPosition(button) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.queryByRole('menuitem')).toBeNull();

    cleanup();
    const singleWidget: DashboardLayoutItem = {
      ...dataWidget,
      i: 'single',
      name: '单值',
      valueConfig: { chartType: 'single' },
    };
    renderCanvas([singleWidget], { isEditMode: false, renderMode: false });
    await waitFor(() => {
      expect(screen.getByText('单值')).toBeTruthy();
    });
    expect(screen.queryByRole('button', { name: 'dashboard.exportCsv' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'common.more' })).toBeNull();
  });

  it('hides csv export in share, fullscreen, and screenshot modes', async () => {
    renderCanvas([dataWidget], { isEditMode: false, renderMode: false, shareMode: true });
    await waitFor(() => {
      expect(screen.getByText('CPU')).toBeTruthy();
    });
    expect(screen.queryByRole('button', { name: 'dashboard.exportCsv' })).toBeNull();

    cleanup();
    renderCanvas([dataWidget], { isEditMode: false, renderMode: false, isFullscreen: true });
    await waitFor(() => {
      expect(screen.getByText('CPU')).toBeTruthy();
    });
    expect(screen.queryByRole('button', { name: 'dashboard.exportCsv' })).toBeNull();

    cleanup();
    renderCanvas([dataWidget], { isEditMode: true, renderMode: false, shareMode: true });
    await openMoreMenu();
    expect(screen.queryByText('dashboard.exportCsv')).toBeNull();

    cleanup();
    renderCanvas([dataWidget], { isEditMode: true, renderMode: true });
    await openMoreMenu();
    expect(screen.queryByText('dashboard.exportCsv')).toBeNull();

    cleanup();
    renderCanvas([dataWidget], { isEditMode: false, renderMode: false, pdfExportPreparing: true });
    await waitFor(() => {
      expect(screen.getByText('CPU')).toBeTruthy();
    });
    expect(screen.queryByRole('button', { name: 'dashboard.exportCsv' })).toBeNull();
  });

  it('adds csv export to the edit menu outside render snapshots', async () => {
    renderCanvas([dataWidget], { isEditMode: true, renderMode: false });
    await openMoreMenu();
    const items = await screen.findAllByRole('menuitem');
    expect(items.map((item) => item.textContent)).toEqual([
      'common.edit',
      'common.copy',
      'dashboard.exportCsv',
      'common.delete',
    ]);
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

const titleLinkWidget: DashboardLayoutItem = {
  ...dataWidget,
  name: '告警源总数',
  valueConfig: {
    chartType: 'line',
    dataSource: 7,
    interaction: {
      kind: 'title',
      name: '查看详情',
      url: '/ops',
      openMode: 'sameTab',
    },
  },
};

const isLastIn = (node: HTMLElement, root: HTMLElement) => {
  const last = root.lastElementChild;
  return last === node || Boolean(last?.contains(node));
};

describe('Dashboard title link', () => {
  it('places the chevron after the runtime slot and the csv download', async () => {
    renderCanvas([titleLinkWidget], { isEditMode: false, renderMode: false });
    const link = await screen.findByRole('button', { name: '查看详情' });
    const header = link.closest('.widget-header') as HTMLElement;
    const title = screen.getByRole('heading', { name: '告警源总数' });
    const csv = screen.getByRole('button', { name: 'dashboard.exportCsv' });
    const slot = header.querySelector('.overflow-x-auto') as HTMLElement;

    expect(link.querySelector('.anticon-export')).toBeTruthy();
    expect(link.querySelector('.anticon-share-alt')).toBeNull();
    expect(link.className).toContain('w-0');
    expect(link.className).toContain('group-hover:w-5');
    expect(link.getAttribute('data-export-hidden')).toBe('true');
    expect(link.className).toContain('no-drag');
    expect(title.className).toContain('truncate');
    expect(title.closest('button')).toBeNull();
    expect(title.compareDocumentPosition(link) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(slot.compareDocumentPosition(link) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(csv.compareDocumentPosition(link) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(isLastIn(link, header)).toBe(true);
  });

  it('places the jump icon before the edit menu so the menu stays at the end', async () => {
    renderCanvas([titleLinkWidget], { isEditMode: true, renderMode: false });
    const link = await screen.findByRole('button', { name: '查看详情' });
    const more = screen.getByRole('button', { name: 'common.more' });
    const header = link.closest('.widget-header') as HTMLElement;

    expect(link.compareDocumentPosition(more) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(link.className).toContain('-mr-2');
    expect(isLastIn(more, header)).toBe(true);
    expect(screen.queryByRole('button', { name: 'dashboard.exportCsv' })).toBeNull();
  });

  it('hides the chevron on the share surface', async () => {
    const scrollRootRef = createRef<HTMLDivElement | null>();
    scrollRootRef.current = document.createElement('div');
    render(
      <ShareModeProvider value>
        <DashboardCanvas
          loading={false}
          isEditMode={false}
          isDarkTheme={false}
          dashboardId={1}
          layout={[titleLinkWidget]}
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
          shareMode
          onLayoutChange={vi.fn()}
          onOpenAddModal={vi.fn()}
          onToggleCollapsedGroup={vi.fn()}
          onRenameGroup={vi.fn()}
          onRemoveGroup={vi.fn()}
          onDeleteEntireGroup={vi.fn()}
          onEditWidget={vi.fn()}
          onCopyWidget={vi.fn()}
          onDeleteWidget={vi.fn()}
          renderMode={false}
          scrollRootRef={scrollRootRef}
        />
      </ShareModeProvider>,
    );
    await waitFor(() => {
      expect(screen.getByText('告警源总数')).toBeTruthy();
    });
    expect(screen.queryByRole('button', { name: '查看详情' })).toBeNull();
  });
});
