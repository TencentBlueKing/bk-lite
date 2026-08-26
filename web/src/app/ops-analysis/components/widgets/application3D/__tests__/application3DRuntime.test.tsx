import React from 'react';
import { act, cleanup, render, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import Application3D from '../index';
import type { Application3DWallData } from '@/app/ops-analysis/types/sceneWidget';
import type { ScreenRenderContext } from '@/app/ops-analysis/types/dashBoard';

const mocks = vi.hoisted(() => ({
  getWall: vi.fn(),
  getApplicationDetail: vi.fn(),
  getAlarmDetail: vi.fn(),
  getMetric: vi.fn(),
  setActive: vi.fn(),
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
  createApplication3DScene: () => ({
    reconcile: vi.fn(),
    focus: vi.fn(),
    restoreWall: vi.fn(),
    resize: vi.fn(),
    dispose: vi.fn(),
    setActive: mocks.setActive,
  }),
}));

const context: ScreenRenderContext = {
  enabled: true,
  fitScale: 1,
  screenDensity: 1,
  screenUiScale: 1,
  widgetDensity: 1,
  widgetUiScale: 1,
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
