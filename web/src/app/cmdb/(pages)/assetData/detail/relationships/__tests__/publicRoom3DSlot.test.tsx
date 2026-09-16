import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

const INST_UUID = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';

const clientState = vi.hoisted(() => ({
  clientData: [{ name: 'ops-analysis' }] as Array<{ name: string }>,
}));

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

vi.mock('@/context/client', () => ({
  useClientData: () => ({
    clientData: clientState.clientData,
    loading: false,
  }),
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
  clientState.clientData = [{ name: 'ops-analysis' }];
  widgetState.status = 'unavailable';
  widgetState.declared = false;
  widgetState.loadWidget = null;
  lazyState.Widget = null;
  lazyState.loadFailed = false;
  lazyState.loadCalls = [];
});

describe('canShowRoom3DTab', () => {
  it('shows only for server_room with OA, a declared widget and instUuid', () => {
    expect(
      canShowRoom3DTab({
        modelId: 'server_room',
        declared: true,
        instUuid: INST_UUID,
        hasOpsAnalysis: true,
      }),
    ).toBe(true);
    expect(
      canShowRoom3DTab({
        modelId: 'server_room',
        declared: true,
        instUuid: INST_UUID,
        hasOpsAnalysis: false,
      }),
    ).toBe(false);
    expect(
      canShowRoom3DTab({
        modelId: 'rack',
        declared: true,
        instUuid: INST_UUID,
        hasOpsAnalysis: true,
      }),
    ).toBe(false);
    expect(
      canShowRoom3DTab({
        modelId: 'host',
        declared: true,
        instUuid: INST_UUID,
        hasOpsAnalysis: true,
      }),
    ).toBe(false);
    expect(
      canShowRoom3DTab({
        modelId: 'server_room',
        declared: false,
        instUuid: INST_UUID,
        hasOpsAnalysis: true,
      }),
    ).toBe(false);
    expect(
      canShowRoom3DTab({
        modelId: 'server_room',
        declared: true,
        instUuid: '',
        hasOpsAnalysis: true,
      }),
    ).toBe(false);
    expect(
      canShowRoom3DTab({
        modelId: 'server_room',
        declared: true,
        instUuid: 'room-1',
        hasOpsAnalysis: true,
      }),
    ).toBe(false);
  });
});

describe('PublicRoom3DSlot', () => {
  it('mounts the public widget when OA, declared and instUuid are present', () => {
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

  it('does not activate when ops-analysis is not sold', () => {
    clientState.clientData = [];
    widgetState.status = 'ready';
    widgetState.declared = true;
    widgetState.loadWidget = async () => ({ default: () => null });
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
