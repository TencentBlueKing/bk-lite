import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

const INST_UUID = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';

const widgetState = vi.hoisted(() => ({
  status: 'unavailable' as 'unavailable' | 'loading' | 'ready',
  declared: false,
  loadWidget: null as (() => Promise<{ default: unknown }>) | null,
}));

const lazyState = vi.hoisted(() => ({
  Widget: null as React.ComponentType<{ instUuid: string }> | null,
  loadFailed: false,
  loadCalls: [] as boolean[],
}));

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock('@/context/appCapabilities', async () => {
  const actual = await vi.importActual<typeof import('@/context/appCapabilities')>(
    '@/context/appCapabilities',
  );
  return {
    ...actual,
    useAppWidget: () => ({
      status: widgetState.status,
      declared: widgetState.declared,
      loadWidget: widgetState.loadWidget,
    }),
    useLazyAppWidget: ({ active }: { active: boolean }) => {
      lazyState.loadCalls.push(active);
      return { Widget: lazyState.Widget, loadFailed: lazyState.loadFailed };
    },
  };
});

import { canShowRoom3DTab, PublicRoom3DSlot } from '../publicRoom3DSlot';

afterEach(() => {
  cleanup();
  widgetState.status = 'unavailable';
  widgetState.declared = false;
  widgetState.loadWidget = null;
  lazyState.Widget = null;
  lazyState.loadFailed = false;
  lazyState.loadCalls = [];
});

describe('canShowRoom3DTab', () => {
  // 未购运营分析 = 目录探测不到 ops-analysis.room3D，declared 为 false。
  it('shows only for server_room with a declared widget and instUuid', () => {
    expect(
      canShowRoom3DTab({
        modelId: 'server_room',
        declared: true,
        instUuid: INST_UUID,
      }),
    ).toBe(true);
    expect(
      canShowRoom3DTab({
        modelId: 'rack',
        declared: true,
        instUuid: INST_UUID,
      }),
    ).toBe(false);
    expect(
      canShowRoom3DTab({
        modelId: 'host',
        declared: true,
        instUuid: INST_UUID,
      }),
    ).toBe(false);
    expect(
      canShowRoom3DTab({
        modelId: 'server_room',
        declared: false,
        instUuid: INST_UUID,
      }),
    ).toBe(false);
    expect(
      canShowRoom3DTab({
        modelId: 'server_room',
        declared: true,
        instUuid: '',
      }),
    ).toBe(false);
    expect(
      canShowRoom3DTab({
        modelId: 'server_room',
        declared: true,
        instUuid: 'room-1',
      }),
    ).toBe(false);
  });
});

describe('PublicRoom3DSlot', () => {
  it('mounts the public widget when declared and instUuid are present', () => {
    widgetState.status = 'ready';
    widgetState.declared = true;
    widgetState.loadWidget = async () => ({ default: () => null });
    lazyState.Widget = function PublicRoom3DWidget({ instUuid }: { instUuid: string }) {
      return <div>{`public-room3d:${instUuid}`}</div>;
    };
    render(<PublicRoom3DSlot instUuid={INST_UUID} />);
    expect(screen.getByText(`public-room3d:${INST_UUID}`)).toBeTruthy();
    expect(lazyState.loadCalls.at(-1)).toBe(true);
  });

  // 未购运营分析走的就是这条分支：目录探测不到该键，declared 为 false。
  it('does not activate when the key is undeclared', () => {
    widgetState.status = 'ready';
    widgetState.declared = false;
    render(<PublicRoom3DSlot instUuid={INST_UUID} />);
    expect(screen.getByText('common.noData')).toBeTruthy();
    expect(lazyState.loadCalls.at(-1)).toBe(false);
  });

  it('keeps an in-slot error when the public widget fails to load', () => {
    widgetState.status = 'ready';
    widgetState.declared = true;
    widgetState.loadWidget = async () => ({ default: () => null });
    lazyState.loadFailed = true;
    render(<PublicRoom3DSlot instUuid={INST_UUID} />);
    expect(screen.getByText('common.loadFailed')).toBeTruthy();
    expect(screen.queryByText('public-room3d')).toBeNull();
  });

  it('does not treat a name as instUuid', () => {
    widgetState.status = 'ready';
    widgetState.declared = true;
    widgetState.loadWidget = async () => ({ default: () => null });
    render(<PublicRoom3DSlot instUuid="room-1" />);
    expect(screen.getByText('Model.missingStableId')).toBeTruthy();
    expect(lazyState.loadCalls.at(-1)).toBe(false);
  });
});
