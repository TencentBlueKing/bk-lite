import React from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import Application3D from '../index';
import type { Application3DWallData, Application3DWallItem } from '@/app/ops-analysis/types/sceneWidget';
import type { ScreenRenderContext } from '@/app/ops-analysis/types/dashBoard';

interface SceneCallbacks {
  onSelect: (item: Application3DWallItem) => void;
  onFocusSettled?: (item: Application3DWallItem) => void;
  onBackground?: () => void;
}

const mocks = vi.hoisted(() => ({
  getWall: vi.fn(),
  getApplicationDetail: vi.fn(),
  getAlarmDetail: vi.fn(),
  getMetric: vi.fn(),
  setActive: vi.fn(),
  restoreWall: vi.fn(),
  reconcile: vi.fn(),
  sceneCallbacks: null as SceneCallbacks | null,
}));

vi.mock('@/utils/i18n', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('next/navigation', () => ({ useParams: () => ({}) }));
vi.mock('@/app/ops-analysis/context/shareMode', () => ({ useShareMode: () => false }));
vi.mock('@/app/ops-analysis/api/application3D', () => ({
  useApplication3DApi: () => ({
    getWall: mocks.getWall,
    getApplicationDetail: mocks.getApplicationDetail,
    getAlarmDetail: mocks.getAlarmDetail,
    getMetric: mocks.getMetric,
  }),
}));
vi.mock('../application3DScene', () => ({
  createApplication3DScene: (_node: unknown, options: SceneCallbacks) => {
    mocks.sceneCallbacks = options;
    return {
      reconcile: mocks.reconcile,
      focus: vi.fn(),
      restoreWall: mocks.restoreWall,
      resize: vi.fn(),
      getFocusChromeLayout: vi.fn(() => null),
      dispose: vi.fn(),
      setActive: mocks.setActive,
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

describe('application3D focus chrome', () => {
  it('shows detail and back only after the focused card settles, and background click restores the wall', async () => {
    mocks.getWall.mockResolvedValue({
      ...wall,
      items: [wallItem],
      capacity: { actualCount: 1, supportedCount: null },
    });
    render(<Application3D refreshKey="0" runtimeActive screenRenderContext={context} />);

    await waitFor(() => expect(mocks.sceneCallbacks).not.toBeNull());
    expect(screen.queryByRole('button', { name: /application3DOpenDetail/ })).toBeNull();

    act(() => {
      mocks.sceneCallbacks?.onSelect(wallItem);
    });
    expect(screen.queryByRole('button', { name: /application3DOpenDetail/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /application3DBackWall/ })).toBeNull();

    act(() => {
      mocks.sceneCallbacks?.onFocusSettled?.(wallItem);
    });
    expect(screen.getByRole('button', { name: /application3DOpenDetail/ })).toBeTruthy();
    expect(screen.getByRole('button', { name: /application3DBackWall/ })).toBeTruthy();
    expect(document.querySelector('.app3d-detail-cta-frame')).toBeNull();
    expect(document.querySelector('.app3d-detail-cta-mark')).toBeNull();
    expect(document.querySelector('.app3d-detail-cta')).toBeTruthy();
    expect(document.querySelector('.app3d-back-cta')).toBeTruthy();

    act(() => {
      mocks.sceneCallbacks?.onBackground?.();
    });
    expect(screen.queryByRole('button', { name: /application3DOpenDetail/ })).toBeNull();
    expect(mocks.restoreWall).toHaveBeenCalled();
  });

  it('sends the focused card home when opening application detail', async () => {
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
    act(() => {
      mocks.sceneCallbacks?.onFocusSettled?.(wallItem);
    });
    fireEvent.click(screen.getByRole('button', { name: /application3DOpenDetail/ }));

    expect(mocks.restoreWall).toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: /application3DOpenDetail/ })).toBeNull();
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
    await waitFor(() => expect(mocks.getWall).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(mocks.reconcile).toHaveBeenCalled());
    expect(mocks.reconcile.mock.calls.every((call) => call[1]?.playIntro === true)).toBe(false);
    expect(mocks.reconcile.mock.calls.every((call) => call[1]?.playFilter !== true)).toBe(true);
  });
});
