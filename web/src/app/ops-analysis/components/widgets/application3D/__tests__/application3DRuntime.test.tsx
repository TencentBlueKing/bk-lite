import React from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import Application3D from '../index';
import type { Application3DWallData, Application3DWallItem } from '@/app/ops-analysis/types/sceneWidget';
import type { ScreenRenderContext } from '@/app/ops-analysis/types/dashBoard';

interface SceneCallbacks {
  onSelect: (item: Application3DWallItem) => void;
  onBackgroundClick?: () => void;
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
});
