import React from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import Application3D from '../index';
import type { Application3DWallData, Application3DWallItem } from '@/app/ops-analysis/types/sceneWidget';
import type { ScreenRenderContext, ValueConfig } from '@/app/ops-analysis/types/dashBoard';
import { resolveApplication3DWallConfig } from '@/app/ops-analysis/utils/application3DWallConfig';

interface SceneCallbacks {
  onSelect: (item: Application3DWallItem) => void;
  onBackgroundClick?: () => void;
  onArchitectureHostSelect?: (selection: {
    node: { id: string; name: string; health?: { state: string; activeAlarmCount: number | null; highestSeverity: { label: string } | null } };
    overlay: { left: number; top: number };
  } | null) => void;
}

const mocks = vi.hoisted(() => ({
  getWall: vi.fn(),
  getApplicationDetail: vi.fn(),
  getArchitecture: vi.fn(),
  getAlarmDetail: vi.fn(),
  getMetric: vi.fn(),
  setActive: vi.fn(),
  reconcile: vi.fn(),
  resetCamera: vi.fn(),
  focus: vi.fn(),
  showArchitecture: vi.fn(),
  hideArchitecture: vi.fn(),
  sceneCallbacks: null as SceneCallbacks | null,
}));

vi.mock('@/utils/i18n', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('next/navigation', () => ({ useParams: () => ({}) }));
vi.mock('@/app/ops-analysis/context/shareMode', () => ({ useShareMode: () => false }));
vi.mock('@/app/ops-analysis/api/application3D', () => ({
  useApplication3DApi: () => ({
    getWall: mocks.getWall,
    getApplicationDetail: mocks.getApplicationDetail,
    getArchitecture: mocks.getArchitecture,
    getAlarmDetail: mocks.getAlarmDetail,
    getMetric: mocks.getMetric,
  }),
}));
vi.mock('../application3DScene', () => ({
  createApplication3DScene: (_node: unknown, options: SceneCallbacks) => {
    mocks.sceneCallbacks = options;
    return {
      reconcile: mocks.reconcile,
      resize: vi.fn(),
      dispose: vi.fn(),
      setActive: mocks.setActive,
      resetCamera: mocks.resetCamera,
      focus: mocks.focus,
      showArchitecture: mocks.showArchitecture,
      hideArchitecture: mocks.hideArchitecture,
      dismissArchitectureOverlay: vi.fn(),
    };
  },
}));

const context: ScreenRenderContext = {
  enabled: true,
  fitScale: 1,
  screenDensity: 1,
  screenUiScale: 1,
  widgetDensity: 1,
  widgetUiScale: 1,
};

const wallItem: Application3DWallItem = {
  id: 'app-1',
  name: '运营门户',
  health: {
    state: 'normal',
    reason: 'no_active_alarm',
    activeAlarmCount: 0,
    severityCounts: { critical: 0, error: 0, warning: 0, info: 0 },
    noDataAlarmCount: 0,
    highestSeverity: { id: 'normal', label: '正常', rank: 0, color: 'success' },
    stale: false,
  },
};

const wall: Application3DWallData = {
  items: [],
  filters: [],
  appliedFilters: { system_status: [] },
  refreshedAt: '2026-08-26T00:00:00Z',
  capacity: { actualCount: 0, supportedCount: null },
};

afterEach(() => {
  cleanup();
  mocks.sceneCallbacks = null;
  vi.clearAllMocks();
});

describe('application3D runtimeActive contract', () => {
  it('does not request while inactive and performs one latest refresh on activation', async () => {
    mocks.getWall.mockResolvedValue(wall);
    const view = render(
      <Application3D refreshKey="0" runtimeActive={false} screenRenderContext={context} />,
    );

    await act(async () => Promise.resolve());
    expect(mocks.getWall).not.toHaveBeenCalled();

    view.rerender(
      <Application3D refreshKey="1" runtimeActive={false} screenRenderContext={context} />,
    );
    expect(mocks.getWall).not.toHaveBeenCalled();

    view.rerender(
      <Application3D refreshKey="1" runtimeActive screenRenderContext={context} />,
    );
    await waitFor(() => expect(mocks.getWall).toHaveBeenCalledTimes(1));
    expect(mocks.setActive).toHaveBeenCalledWith(true);
  });

  it('aborts an in-flight wall request when deactivated and on unmount', async () => {
    const signals: AbortSignal[] = [];
    mocks.getWall.mockImplementation((_filters, signal: AbortSignal) => {
      signals.push(signal);
      return new Promise<Application3DWallData>(() => undefined);
    });
    const view = render(
      <Application3D refreshKey="0" runtimeActive screenRenderContext={context} />,
    );
    await waitFor(() => expect(signals).toHaveLength(1));

    view.rerender(
      <Application3D refreshKey="0" runtimeActive={false} screenRenderContext={context} />,
    );
    expect(signals[0].aborted).toBe(true);
    view.unmount();
    expect(mocks.setActive).toHaveBeenCalledWith(false);
  });
});

describe('application3D application detail', () => {
  it('focuses a card first and shows 详情 / 部署架构 without opening detail', async () => {
    mocks.getWall.mockResolvedValue({
      ...wall,
      items: [wallItem],
      capacity: { actualCount: 1, supportedCount: null },
    });
    render(<Application3D refreshKey="0" runtimeActive screenRenderContext={context} />);

    await waitFor(() => expect(mocks.sceneCallbacks).not.toBeNull());
    expect(screen.queryByRole('dialog')).toBeNull();

    act(() => {
      mocks.sceneCallbacks?.onSelect(wallItem);
    });
    expect(mocks.focus).toHaveBeenCalledWith('app-1');
    expect(mocks.resetCamera).not.toHaveBeenCalled();
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(mocks.getApplicationDetail).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: /application3DOpenDetail/ })).toBeTruthy();
    expect(screen.getByRole('button', { name: /application3DOpenArchitecture/ })).toBeTruthy();
    expect(screen.getByRole('button', { name: /application3DBackWall/ })).toBeTruthy();
    expect(document.querySelector('.app3d-detail-cta')).toBeTruthy();
    expect(document.querySelector('.app3d-architecture-cta')).toBeTruthy();
    expect(document.querySelector('.app3d-back-cta')).toBeTruthy();
  });

  it('opens the existing detail chrome from 详情 using the system uuid', async () => {
    mocks.getWall.mockResolvedValue({
      ...wall,
      items: [wallItem],
      capacity: { actualCount: 1, supportedCount: null },
    });
    mocks.getApplicationDetail.mockImplementation(() => new Promise(() => undefined));
    render(<Application3D refreshKey="0" runtimeActive screenRenderContext={context} />);

    await waitFor(() => expect(mocks.sceneCallbacks).not.toBeNull());
    act(() => {
      mocks.sceneCallbacks?.onSelect(wallItem);
    });
    fireEvent.click(screen.getByRole('button', { name: /application3DOpenDetail/ }));
    expect(mocks.resetCamera).toHaveBeenCalled();
    expect(screen.getByRole('dialog')).toBeTruthy();
    expect(screen.queryByRole('button', { name: /application3DOpenDetail/ })).toBeNull();
    expect(mocks.getApplicationDetail).toHaveBeenCalledWith('app-1', undefined, expect.any(AbortSignal));
  });

  it('requests architecture with the system uuid after 部署架构', async () => {
    mocks.getWall.mockResolvedValue({
      ...wall,
      items: [wallItem],
      capacity: { actualCount: 1, supportedCount: null },
    });
    const architecture = {
      systemId: 'app-1',
      refreshedAt: '2026-09-01T00:00:00Z',
      nodes: [{ id: 'app-1', kind: 'system' as const, name: '运营门户' }],
      edges: [],
    };
    mocks.getArchitecture.mockResolvedValue(architecture);
    render(<Application3D refreshKey="0" runtimeActive screenRenderContext={context} />);

    await waitFor(() => expect(mocks.sceneCallbacks).not.toBeNull());
    act(() => {
      mocks.sceneCallbacks?.onSelect(wallItem);
    });
    fireEvent.click(screen.getByRole('button', { name: /application3DOpenArchitecture/ }));
    await waitFor(() => expect(mocks.getArchitecture).toHaveBeenCalledWith('app-1', expect.any(AbortSignal)));
    await waitFor(() => expect(mocks.showArchitecture).toHaveBeenCalledWith(architecture));
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(mocks.getApplicationDetail).not.toHaveBeenCalled();
  });

  it('returns from architecture to the full wall without focused CTAs', async () => {
    mocks.getWall.mockResolvedValue({
      ...wall,
      items: [wallItem],
      capacity: { actualCount: 1, supportedCount: null },
    });
    mocks.getArchitecture.mockResolvedValue({
      systemId: 'app-1',
      refreshedAt: '2026-09-01T00:00:00Z',
      nodes: [{ id: 'app-1', kind: 'system' as const, name: '运营门户' }],
      edges: [],
    });
    render(<Application3D refreshKey="0" runtimeActive screenRenderContext={context} />);
    await waitFor(() => expect(mocks.sceneCallbacks).not.toBeNull());
    act(() => {
      mocks.sceneCallbacks?.onSelect(wallItem);
    });
    fireEvent.click(screen.getByRole('button', { name: /application3DOpenArchitecture/ }));
    await waitFor(() => expect(mocks.showArchitecture).toHaveBeenCalled());
    fireEvent.click(screen.getByRole('button', { name: /application3DBackWall/ }));
    expect(mocks.hideArchitecture).toHaveBeenCalled();
    expect(mocks.hideArchitecture.mock.calls[0]?.[0]).toBeUndefined();
    expect(screen.queryByRole('button', { name: /application3DOpenDetail/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /application3DOpenArchitecture/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /application3DBackFocus/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /application3DBackWall/ })).toBeNull();
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('renders a compact host status chip from architecture selection without opening detail', async () => {
    mocks.getWall.mockResolvedValue({
      ...wall,
      items: [wallItem],
      capacity: { actualCount: 1, supportedCount: null },
    });
    mocks.getArchitecture.mockResolvedValue({
      systemId: 'app-1',
      refreshedAt: '2026-09-01T00:00:00Z',
      nodes: [{ id: 'app-1', kind: 'system' as const, name: '运营门户' }],
      edges: [],
    });
    render(<Application3D refreshKey="0" runtimeActive screenRenderContext={context} />);
    await waitFor(() => expect(mocks.sceneCallbacks).not.toBeNull());
    act(() => {
      mocks.sceneCallbacks?.onSelect(wallItem);
    });
    fireEvent.click(screen.getByRole('button', { name: /application3DOpenArchitecture/ }));
    await waitFor(() => expect(mocks.showArchitecture).toHaveBeenCalled());

    act(() => {
      mocks.sceneCallbacks?.onArchitectureHostSelect?.({
        node: {
          id: 'host-alarm',
          name: 'web-alarm',
          kind: 'host',
          health: {
            state: 'alarming',
            activeAlarmCount: 3,
            highestSeverity: { label: '严重' },
          },
        },
        overlay: { left: 48, top: 12 },
      } as never);
    });

    const chip = document.querySelector('.app3d-arch-host-chip') as HTMLElement | null;
    expect(chip).toBeTruthy();
    expect(chip?.style.left).toBe('48px');
    expect(chip?.style.top).toBe('12px');
    expect(chip?.textContent).toContain('web-alarm');
    expect(chip?.textContent).toContain('application3DHostStatus');
    expect(chip?.textContent).toContain('application3DStatus_alarming');
    expect(chip?.textContent).toContain('application3DHostAlarmCount');
    expect(chip?.textContent).toContain('3');
    expect(chip?.textContent).toContain('application3DHostHighestSeverity');
    expect(chip?.textContent).toContain('严重');
    expect(chip?.querySelector('button')).toBeNull();
    expect(chip?.textContent).not.toContain('application3DBackWall');
    expect(getComputedStyle(chip as Element).pointerEvents === 'none' || chip?.className.includes('app3d-arch-host-chip')).toBe(true);
    expect(screen.getByRole('button', { name: /application3DBackWall/ })).toBeTruthy();
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(mocks.getApplicationDetail).not.toHaveBeenCalled();
    expect(mocks.getAlarmDetail).not.toHaveBeenCalled();

    act(() => {
      mocks.sceneCallbacks?.onArchitectureHostSelect?.({
        node: {
          id: 'host-alarm',
          name: 'web-alarm',
          kind: 'host',
          health: {
            state: 'alarming',
            activeAlarmCount: null,
            highestSeverity: null,
          },
        },
        overlay: { left: 48, top: 12 },
      } as never);
    });
    expect(document.querySelector('.app3d-arch-host-chip')?.textContent).toContain('--');

    act(() => {
      mocks.sceneCallbacks?.onArchitectureHostSelect?.({
        node: {
          id: 'host-unknown',
          name: 'web-unknown',
          kind: 'host',
          health: {
            state: 'unknown',
            activeAlarmCount: 0,
            highestSeverity: null,
          },
        },
        overlay: { left: 48, top: 12 },
      } as never);
    });
    const unknownMetricVal = document.querySelector('.app3d-arch-host-chip__metric-val');
    expect(unknownMetricVal?.textContent).toBe('--');

    act(() => {
      mocks.sceneCallbacks?.onArchitectureHostSelect?.({
        node: {
          id: 'host-bare',
          name: 'web-bare',
          kind: 'host',
          health: {
            state: 'unknown',
            reason: 'unmonitored',
            activeAlarmCount: null,
            highestSeverity: null,
          },
        },
        overlay: { left: 48, top: 12 },
      } as never);
    });
    expect(document.querySelector('.app3d-arch-host-chip')?.textContent).toContain(
      'application3DHostUnmonitored',
    );
    expect(document.querySelector('.app3d-arch-host-chip__metric-val')?.textContent).toBe('--');

    act(() => {
      mocks.sceneCallbacks?.onArchitectureHostSelect?.(null);
    });
    expect(document.querySelector('.app3d-arch-host-chip')).toBeNull();
  });

  it('does not refetch the same application while its detail is already open', async () => {
    mocks.getWall.mockResolvedValue({
      ...wall,
      items: [wallItem],
      capacity: { actualCount: 1, supportedCount: null },
    });
    mocks.getApplicationDetail.mockImplementation(() => new Promise(() => undefined));
    render(<Application3D refreshKey="0" runtimeActive screenRenderContext={context} />);

    await waitFor(() => expect(mocks.sceneCallbacks).not.toBeNull());
    act(() => {
      mocks.sceneCallbacks?.onSelect(wallItem);
    });
    fireEvent.click(screen.getByRole('button', { name: /application3DOpenDetail/ }));
    act(() => {
      mocks.sceneCallbacks?.onSelect(wallItem);
    });
    expect(mocks.getApplicationDetail).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('dialog')).toBeTruthy();
  });
});

describe('application3D wall motion triggers', () => {
  const populated = {
    ...wall,
    items: [wallItem],
    capacity: { actualCount: 1, supportedCount: null },
  };

  it('plays intro on first wall and not on silent refresh', async () => {
    mocks.getWall.mockResolvedValue(populated);
    render(<Application3D refreshKey="0" runtimeActive screenRenderContext={context} />);
    await waitFor(() => expect(mocks.reconcile).toHaveBeenCalled());
    expect(mocks.reconcile.mock.calls.some((call) => call[1]?.playIntro === true)).toBe(true);

    mocks.reconcile.mockClear();
    mocks.getWall.mockResolvedValue({
      ...populated,
      refreshedAt: '2026-08-26T00:01:00Z',
    });
    fireEvent.click(screen.getByTitle('common.refresh'));
    expect(mocks.resetCamera).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(mocks.getWall).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(mocks.reconcile).toHaveBeenCalled());
    expect(mocks.reconcile.mock.calls.every((call) => call[1]?.playIntro === true)).toBe(false);
    expect(mocks.reconcile.mock.calls.every((call) => call[1]?.playFilter !== true)).toBe(true);
  });

  it('plays filter motion when 运行状态 changes', async () => {
    const filtered = {
      ...populated,
      filters: [
        {
          id: 'system_status',
          label: '运行状态',
          type: 'multiple' as const,
          options: [
            { value: 'normal', label: '正常' },
            { value: 'alarming', label: '告警' },
          ],
        },
      ],
    };
    mocks.getWall.mockResolvedValue(filtered);
    render(<Application3D refreshKey="0" runtimeActive screenRenderContext={context} />);
    await waitFor(() => expect(mocks.reconcile).toHaveBeenCalled());

    mocks.reconcile.mockClear();
    mocks.getWall.mockResolvedValue({
      ...filtered,
      items: [wallItem, { ...wallItem, id: 'app-2', name: '采购管理' }],
      appliedFilters: { system_status: ['normal'] },
      capacity: { actualCount: 2, supportedCount: null },
    });
    fireEvent.mouseDown(screen.getByRole('combobox'));
    fireEvent.click(await screen.findByTitle('正常'));
    await waitFor(() => expect(mocks.getWall).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(mocks.reconcile).toHaveBeenCalled());
    expect(mocks.focus).toHaveBeenCalledWith(null);
    expect(mocks.hideArchitecture).toHaveBeenCalled();
    expect(mocks.reconcile.mock.calls.some((call) => call[1]?.playFilter === true)).toBe(true);
    expect(mocks.reconcile.mock.calls.every((call) => call[1]?.pageDirection == null)).toBe(true);
    expect(mocks.reconcile.mock.calls.every((call) => call[1]?.playIntro === true)).toBe(false);
  });
});

describe('application3D wall paging chrome', () => {
  const manyItems = Array.from({ length: 50 }, (_, index) => ({
    ...wallItem,
    id: `sys-${String(index + 1).padStart(2, '0')}`,
    name: `系统${String(index + 1).padStart(2, '0')}`,
  }));
  const manyWall = {
    ...wall,
    items: manyItems,
    capacity: { actualCount: 50, supportedCount: null },
  };

  it('reconciles the first 24 sorted cards and shows next plus page label', async () => {
    mocks.getWall.mockResolvedValue(manyWall);
    render(<Application3D refreshKey="0" runtimeActive screenRenderContext={context} />);
    await waitFor(() => expect(mocks.reconcile).toHaveBeenCalled());
    const firstPage = mocks.reconcile.mock.calls.at(-1)?.[0] as Application3DWallItem[];
    expect(firstPage).toHaveLength(24);
    expect(firstPage[0].id).toBe('sys-01');
    expect(firstPage[23].id).toBe('sys-24');
    expect(screen.queryByRole('button', { name: /application3DWallPrevPage/ })).toBeNull();
    expect(screen.getByRole('button', { name: /application3DWallNextPage/ })).toBeTruthy();
    expect(screen.getByText('dashboard.application3DWallPage')).toBeTruthy();
  });

  it('turns the page with pageDirection motion and hides next on the last page', async () => {
    mocks.getWall.mockResolvedValue(manyWall);
    render(<Application3D refreshKey="0" runtimeActive screenRenderContext={context} />);
    await waitFor(() => expect(screen.getByRole('button', { name: /application3DWallNextPage/ })).toBeTruthy());
    mocks.reconcile.mockClear();
    fireEvent.click(screen.getByRole('button', { name: /application3DWallNextPage/ }));
    await waitFor(() => expect(mocks.reconcile).toHaveBeenCalled());
    expect(mocks.focus).toHaveBeenCalledWith(null);
    expect(mocks.reconcile.mock.calls.some((call) => call[1]?.pageDirection === 'next')).toBe(true);
    expect(mocks.reconcile.mock.calls.every((call) => call[1]?.playFilter !== true)).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: /application3DWallNextPage/ }));
    await waitFor(() => expect(screen.queryByRole('button', { name: /application3DWallNextPage/ })).toBeNull());
    expect(screen.getByRole('button', { name: /application3DWallPrevPage/ })).toBeTruthy();
    const lastPage = mocks.reconcile.mock.calls.at(-1)?.[0] as Application3DWallItem[];
    expect(lastPage.map((item) => item.id)).toEqual(['sys-49', 'sys-50']);
  });

  it('hides paging chrome while a card is focused', async () => {
    mocks.getWall.mockResolvedValue(manyWall);
    render(<Application3D refreshKey="0" runtimeActive screenRenderContext={context} />);
    await waitFor(() => expect(screen.getByRole('button', { name: /application3DWallNextPage/ })).toBeTruthy());
    act(() => {
      mocks.sceneCallbacks?.onSelect(manyItems[0]);
    });
    expect(screen.queryByRole('button', { name: /application3DWallNextPage/ })).toBeNull();
    expect(screen.queryByText('dashboard.application3DWallPage')).toBeNull();
  });

  it('keeps a read-only page label in edit mode without turn-page wings', async () => {
    mocks.getWall.mockResolvedValue(manyWall);
    const view = render(
      <Application3D refreshKey="0" runtimeActive screenRenderContext={context} />,
    );
    await waitFor(() => expect(screen.getByRole('button', { name: /application3DWallNextPage/ })).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: /application3DWallNextPage/ }));
    await waitFor(() => expect(screen.getByRole('button', { name: /application3DWallPrevPage/ })).toBeTruthy());

    view.rerender(
      <Application3D refreshKey="0" editMode runtimeActive screenRenderContext={context} />,
    );
    await waitFor(() => expect(screen.queryByRole('button', { name: /application3DWallNextPage/ })).toBeNull());
    expect(screen.queryByRole('button', { name: /application3DWallPrevPage/ })).toBeNull();
    expect(screen.getByText('dashboard.application3DWallPage')).toBeTruthy();
    const firstPage = mocks.reconcile.mock.calls.at(-1)?.[0] as Application3DWallItem[];
    expect(firstPage).toHaveLength(24);
    expect(firstPage[0].id).toBe('sys-01');
  });

  it('returns to page 1 when 运行状态 changes and keeps the page on silent refresh', async () => {
    const filtered = {
      ...manyWall,
      filters: [
        {
          id: 'system_status',
          label: '运行状态',
          type: 'multiple' as const,
          options: [
            { value: 'normal', label: '正常' },
            { value: 'alarming', label: '告警' },
          ],
        },
      ],
    };
    mocks.getWall.mockResolvedValue(filtered);
    render(<Application3D refreshKey="0" runtimeActive screenRenderContext={context} />);
    await waitFor(() => expect(screen.getByRole('button', { name: /application3DWallNextPage/ })).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: /application3DWallNextPage/ }));
    await waitFor(() => expect(screen.getByRole('button', { name: /application3DWallPrevPage/ })).toBeTruthy());

    mocks.getWall.mockResolvedValue({
      ...filtered,
      appliedFilters: { system_status: ['normal'] },
    });
    fireEvent.mouseDown(screen.getByRole('combobox'));
    fireEvent.click(await screen.findByTitle('正常'));
    await waitFor(() => expect(screen.queryByRole('button', { name: /application3DWallPrevPage/ })).toBeNull());
    expect(screen.getByRole('button', { name: /application3DWallNextPage/ })).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: /application3DWallNextPage/ }));
    await waitFor(() => expect(screen.getByRole('button', { name: /application3DWallPrevPage/ })).toBeTruthy());
    mocks.getWall.mockResolvedValue({
      ...filtered,
      appliedFilters: { system_status: ['normal'] },
      refreshedAt: '2026-08-26T00:02:00Z',
    });
    fireEvent.click(screen.getByTitle('common.refresh'));
    await waitFor(() => expect(mocks.getWall).toHaveBeenCalledTimes(3));
    expect(screen.getByRole('button', { name: /application3DWallPrevPage/ })).toBeTruthy();
    expect(screen.getByRole('button', { name: /application3DWallNextPage/ })).toBeTruthy();
  });

  it('passes the configured page effect on a manual turn', async () => {
    mocks.getWall.mockResolvedValue(manyWall);
    render(
      <Application3D
        refreshKey="0"
        runtimeActive
        screenRenderContext={context}
        config={wallConfig({ pageEffect: 'fade' })}
      />,
    );
    await waitFor(() => expect(screen.getByRole('button', { name: /application3DWallNextPage/ })).toBeTruthy());
    mocks.reconcile.mockClear();
    fireEvent.click(screen.getByRole('button', { name: /application3DWallNextPage/ }));
    await waitFor(() => expect(mocks.reconcile).toHaveBeenCalled());
    expect(mocks.reconcile.mock.calls.some((call) => (
      call[1]?.pageDirection === 'next' && call[1]?.pageEffect === 'fade'
    ))).toBe(true);
  });
});

const wallConfig = (
  overrides: Parameters<typeof resolveApplication3DWallConfig>[0] = {},
): ValueConfig => ({
  chartType: 'application3D',
  sceneWidgetType: 'application3D',
  application3DWall: resolveApplication3DWallConfig(overrides),
});

const latestPage = () => mocks.reconcile.mock.calls.at(-1)?.[0] as Application3DWallItem[];

describe('application3D auto page and section restore', () => {
  const manyItems = Array.from({ length: 50 }, (_, index) => ({
    ...wallItem,
    id: `sys-${String(index + 1).padStart(2, '0')}`,
    name: `系统${String(index + 1).padStart(2, '0')}`,
  }));

  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  const settle = async () => {
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
  };

  const advance = async (ms: number) => {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(ms);
    });
  };

  const renderPlaying = async (
    items: Application3DWallItem[],
    overrides: Parameters<typeof resolveApplication3DWallConfig>[0] = {},
    editMode = false,
  ) => {
    mocks.getWall.mockResolvedValue({
      ...wall,
      items,
      capacity: { actualCount: items.length, supportedCount: null },
    });
    render(
      <Application3D
        refreshKey="0"
        runtimeActive
        editMode={editMode}
        screenRenderContext={context}
        config={wallConfig({
          autoPageEnabled: true,
          dwellSeconds: 5,
          pageEffect: 'cut',
          ...overrides,
        })}
      />,
    );
    for (let step = 0; step < 8; step += 1) {
      await settle();
      if (mocks.reconcile.mock.calls.length > 0) return;
    }
    throw new Error('wall did not reconcile');
  };

  it('turns to the next page after the dwell and loops to page 1', async () => {
    await renderPlaying(manyItems);
    expect(latestPage()[0].id).toBe('sys-01');

    await advance(5000);
    expect(latestPage()[0].id).toBe('sys-25');
    await advance(5000);
    expect(latestPage()[0].id).toBe('sys-49');
    await advance(5000);
    expect(latestPage()[0].id).toBe('sys-01');
  });

  it('does not pause on hover, and pauses while a card, detail, or architecture is open', async () => {
    await renderPlaying(manyItems);
    await advance(4000);
    fireEvent.mouseMove(document.body);
    await advance(1000);
    expect(latestPage()[0].id).toBe('sys-25');

    act(() => {
      mocks.sceneCallbacks?.onSelect(manyItems[24]);
    });
    await advance(5000);
    expect(latestPage()[0].id).toBe('sys-25');

    act(() => {
      mocks.sceneCallbacks?.onBackgroundClick?.();
    });
    await advance(4999);
    expect(latestPage()[0].id).toBe('sys-25');
    await advance(1);
    expect(latestPage()[0].id).toBe('sys-49');

    act(() => {
      mocks.sceneCallbacks?.onSelect(manyItems[48]);
    });
    mocks.getApplicationDetail.mockImplementation(() => new Promise(() => undefined));
    fireEvent.click(screen.getByRole('button', { name: /application3DOpenDetail/ }));
    await settle();
    await advance(5000);
    expect(latestPage()[0].id).toBe('sys-49');
    fireEvent.click(screen.getByRole('button', { name: /application3DCloseDetail/ }));
    await settle();
    await advance(5000);
    expect(latestPage()[0].id).toBe('sys-01');

    act(() => {
      mocks.sceneCallbacks?.onSelect(manyItems[0]);
    });
    mocks.getArchitecture.mockResolvedValue({
      systemId: 'sys-01',
      refreshedAt: '2026-08-26T00:00:00Z',
      nodes: [],
      edges: [],
    });
    fireEvent.click(screen.getByRole('button', { name: /application3DOpenArchitecture/ }));
    await settle();
    await advance(5000);
    expect(latestPage()[0].id).toBe('sys-01');
    fireEvent.click(screen.getByRole('button', { name: /application3DBackWall/ }));
    await settle();
    await advance(5000);
    expect(latestPage()[0].id).toBe('sys-25');
  });

  it('restarts the dwell after a manual turn and after a filter change', async () => {
    const filtered = {
      ...wall,
      items: manyItems,
      capacity: { actualCount: 50, supportedCount: null },
      filters: [
        {
          id: 'system_status',
          label: '运行状态',
          type: 'multiple' as const,
          options: [
            { value: 'normal', label: '正常' },
            { value: 'alarming', label: '告警' },
          ],
        },
      ],
    };
    mocks.getWall.mockResolvedValue(filtered);
    render(
      <Application3D
        refreshKey="0"
        runtimeActive
        screenRenderContext={context}
        config={wallConfig({ autoPageEnabled: true, dwellSeconds: 5, pageEffect: 'cut' })}
      />,
    );
    for (let step = 0; step < 8; step += 1) {
      await settle();
      if (screen.queryByRole('button', { name: /application3DWallNextPage/ })) break;
    }
    expect(screen.getByRole('button', { name: /application3DWallNextPage/ })).toBeTruthy();

    await advance(4000);
    fireEvent.click(screen.getByRole('button', { name: /application3DWallNextPage/ }));
    await settle();
    expect(latestPage()[0].id).toBe('sys-25');
    await advance(4000);
    expect(latestPage()[0].id).toBe('sys-25');
    await advance(1000);
    expect(latestPage()[0].id).toBe('sys-49');

    mocks.getWall.mockResolvedValue({
      ...filtered,
      appliedFilters: { system_status: ['normal'] },
    });
    fireEvent.mouseDown(screen.getByRole('combobox'));
    await settle();
    fireEvent.click(screen.getByTitle('正常'));
    for (let step = 0; step < 8; step += 1) {
      await settle();
      if (latestPage()[0]?.id === 'sys-01') break;
    }
    expect(latestPage()[0].id).toBe('sys-01');
    await advance(4999);
    expect(latestPage()[0].id).toBe('sys-01');
    await advance(1);
    expect(latestPage()[0].id).toBe('sys-25');
  });

  it('does not auto-turn in edit mode', async () => {
    await renderPlaying(manyItems, {}, true);
    expect(screen.queryByRole('button', { name: /application3DWallNextPage/ })).toBeNull();
    await advance(5000);
    expect(latestPage()[0].id).toBe('sys-01');
    expect(latestPage()).toHaveLength(24);
  });

  it('stays on the same rest page when a refresh inserts alarm pages ahead of it', async () => {
    const alarming = {
      ...wallItem.health,
      state: 'alarming' as const,
      activeAlarmCount: 2,
    };
    const alarms = (count: number, prefix: string) => Array.from({ length: count }, (_, index) => ({
      ...wallItem,
      id: `${prefix}-${index + 1}`,
      name: `告警${prefix}${index + 1}`,
      health: alarming,
    }));
    const normals = Array.from({ length: 30 }, (_, index) => ({
      ...wallItem,
      id: `normal-${index + 1}`,
      name: `正常${String(index + 1).padStart(2, '0')}`,
    }));
    const first = {
      ...wall,
      items: [...alarms(10, 'alarm'), ...normals],
      capacity: { actualCount: 40, supportedCount: null },
    };
    mocks.getWall.mockResolvedValue(first);
    render(
      <Application3D
        refreshKey="0"
        runtimeActive
        screenRenderContext={context}
        config={wallConfig({
          alarmPagesEnabled: true,
          autoPageEnabled: true,
          dwellSeconds: 5,
          pageEffect: 'cut',
        })}
      />,
    );
    for (let step = 0; step < 8; step += 1) {
      await settle();
      if (screen.queryByRole('button', { name: /application3DWallNextPage/ })) break;
    }
    fireEvent.click(screen.getByRole('button', { name: /application3DWallNextPage/ }));
    for (let step = 0; step < 8; step += 1) {
      await settle();
      if (latestPage().every((item) => item.health.state === 'normal')) break;
    }
    expect(latestPage().every((item) => item.health.state === 'normal')).toBe(true);

    mocks.getWall.mockResolvedValue({
      ...first,
      items: [...alarms(30, 'alarm'), ...normals],
      refreshedAt: '2026-08-26T00:05:00Z',
      capacity: { actualCount: 60, supportedCount: null },
    });
    await advance(4000);
    fireEvent.click(screen.getByTitle('common.refresh'));
    for (let step = 0; step < 8; step += 1) {
      await settle();
      if (mocks.getWall.mock.calls.length >= 2 && latestPage()[0]?.id === 'normal-1') break;
    }
    expect(latestPage()[0]?.id).toBe('normal-1');
    expect(latestPage()).toHaveLength(24);
    expect(screen.getByRole('button', { name: /application3DWallPrevPage/ })).toBeTruthy();
    await advance(1000);
    expect(latestPage()[0].id).toBe('normal-25');
  });
});

describe('application3D surface gate', () => {
  it('allows screen config preview without screenRenderContext', async () => {
    mocks.getWall.mockResolvedValue(wall);
    render(<Application3D refreshKey="0" runtimeActive surface="screen" />);

    await waitFor(() => expect(mocks.getWall).toHaveBeenCalledTimes(1));
    expect(screen.queryByText('dashboard.application3DScreenOnly')).toBeNull();
  });

  it('reports wall payload for preview raw data', async () => {
    mocks.getWall.mockResolvedValue(wall);
    const onRawData = vi.fn();
    render(
      <Application3D
        refreshKey="0"
        runtimeActive
        surface="screen"
        onRawData={onRawData}
      />,
    );

    await waitFor(() => expect(onRawData).toHaveBeenCalledWith(wall));
  });

  it('narrows the wall query to the given application instUuid', async () => {
    mocks.getWall.mockResolvedValue({
      ...wall,
      items: [wallItem],
      capacity: { actualCount: 1, supportedCount: null },
    });
    render(
      <Application3D
        instUuid="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        runtimeActive
        surface="screen"
      />,
    );

    await waitFor(() => expect(mocks.getWall).toHaveBeenCalled());
    expect(mocks.getWall.mock.calls[0][2]).toBe(
      'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    );
  });

  it('blocks dashboard without screen canvas context', async () => {
    mocks.getWall.mockResolvedValue(wall);
    render(<Application3D refreshKey="0" runtimeActive surface="dashboard" />);

    expect(screen.getByText('dashboard.application3DScreenOnly')).toBeTruthy();
    await act(async () => Promise.resolve());
    expect(mocks.getWall).not.toHaveBeenCalled();
  });
});
