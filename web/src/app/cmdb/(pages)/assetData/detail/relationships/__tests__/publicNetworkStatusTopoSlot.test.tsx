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

vi.mock('@/context/appCapabilities', () => ({
  useAppWidget: () => ({
    status: widgetState.status,
    declared: widgetState.declared,
    loadWidget: widgetState.loadWidget,
  }),
  useLazyAppWidget: ({ active }: { active: boolean }) => {
    lazyState.loadCalls.push(active);
    return { Widget: lazyState.Widget, loadFailed: lazyState.loadFailed };
  },
}));

import {
  canShowNetworkStatusTopoTab,
  PublicNetworkStatusTopoSlot,
} from '../publicNetworkStatusTopoSlot';

afterEach(() => {
  cleanup();
  widgetState.status = 'unavailable';
  widgetState.declared = false;
  widgetState.loadWidget = null;
  lazyState.Widget = null;
  lazyState.loadFailed = false;
  lazyState.loadCalls = [];
});

describe('canShowNetworkStatusTopoTab', () => {
  it('shows only when network theme, declared widget and instUuid are all present', () => {
    expect(
      canShowNetworkStatusTopoTab({
        hasNetworkTheme: true,
        declared: true,
        instUuid: INST_UUID,
      }),
    ).toBe(true);
    expect(
      canShowNetworkStatusTopoTab({
        hasNetworkTheme: false,
        declared: true,
        instUuid: INST_UUID,
      }),
    ).toBe(false);
    expect(
      canShowNetworkStatusTopoTab({
        hasNetworkTheme: true,
        declared: false,
        instUuid: INST_UUID,
      }),
    ).toBe(false);
    expect(
      canShowNetworkStatusTopoTab({
        hasNetworkTheme: true,
        declared: true,
        instUuid: '',
      }),
    ).toBe(false);
    expect(
      canShowNetworkStatusTopoTab({
        hasNetworkTheme: true,
        declared: true,
        instUuid: 'web-1',
      }),
    ).toBe(false);
  });
});

describe('PublicNetworkStatusTopoSlot', () => {
  it('mounts the public widget when declared and instUuid is present', () => {
    widgetState.status = 'ready';
    widgetState.declared = true;
    widgetState.loadWidget = async () => ({ default: () => null });
    lazyState.Widget = ({ instUuid }) => (
      <div>{`public-network-status:${instUuid}`}</div>
    );
    render(<PublicNetworkStatusTopoSlot instUuid={INST_UUID} />);
    expect(screen.getByText(`public-network-status:${INST_UUID}`)).toBeTruthy();
    expect(lazyState.loadCalls.at(-1)).toBe(true);
  });

  it('keeps an in-slot error when the public widget fails to load', () => {
    widgetState.status = 'ready';
    widgetState.declared = true;
    widgetState.loadWidget = async () => ({ default: () => null });
    lazyState.loadFailed = true;
    render(<PublicNetworkStatusTopoSlot instUuid={INST_UUID} />);
    expect(screen.getByText('common.loadFailed')).toBeTruthy();
    expect(screen.queryByText('public-network-status')).toBeNull();
  });

  it('does not treat a name as instUuid', () => {
    widgetState.status = 'ready';
    widgetState.declared = true;
    widgetState.loadWidget = async () => ({ default: () => null });
    render(<PublicNetworkStatusTopoSlot instUuid="sw-1" />);
    expect(screen.getByText('Model.missingStableId')).toBeTruthy();
    expect(lazyState.loadCalls.at(-1)).toBe(false);
  });
});
