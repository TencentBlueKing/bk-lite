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

import { PublicRelatedTopoSlot } from '../publicRelatedTopoSlot';

afterEach(() => {
  cleanup();
  widgetState.status = 'unavailable';
  widgetState.declared = false;
  widgetState.loadWidget = null;
  lazyState.Widget = null;
  lazyState.loadFailed = false;
  lazyState.loadCalls = [];
});

describe('PublicRelatedTopoSlot', () => {
  it('renders the default Topo when the public widget is undeclared', () => {
    render(
      <PublicRelatedTopoSlot instUuid={INST_UUID} fallback={<div>default-topo</div>} />,
    );
    expect(screen.getByText('default-topo')).toBeTruthy();
    expect(screen.queryByText('public-related-topo')).toBeNull();
    expect(lazyState.loadCalls.at(-1)).toBe(false);
  });

  it('renders the default Topo when instUuid is missing', () => {
    widgetState.status = 'ready';
    widgetState.declared = true;
    widgetState.loadWidget = async () => ({ default: () => null });
    render(
      <PublicRelatedTopoSlot instUuid="" fallback={<div>default-topo</div>} />,
    );
    expect(screen.getByText('default-topo')).toBeTruthy();
    expect(lazyState.loadCalls.at(-1)).toBe(false);
  });

  it('does not treat a name as instUuid', () => {
    widgetState.status = 'ready';
    widgetState.declared = true;
    widgetState.loadWidget = async () => ({ default: () => null });
    render(
      <PublicRelatedTopoSlot instUuid="web-1" fallback={<div>default-topo</div>} />,
    );
    expect(screen.getByText('default-topo')).toBeTruthy();
    expect(lazyState.loadCalls.at(-1)).toBe(false);
  });

  it('mounts the public widget when declared and instUuid is present', () => {
    widgetState.status = 'ready';
    widgetState.declared = true;
    widgetState.loadWidget = async () => ({ default: () => null });
    lazyState.Widget = ({ instUuid }) => (
      <div>{`public-related-topo:${instUuid}`}</div>
    );
    render(
      <PublicRelatedTopoSlot instUuid={INST_UUID} fallback={<div>default-topo</div>} />,
    );
    expect(screen.getByText(`public-related-topo:${INST_UUID}`)).toBeTruthy();
    expect(screen.queryByText('default-topo')).toBeNull();
    expect(lazyState.loadCalls.at(-1)).toBe(true);
  });

  it('falls back to the default Topo when the public widget fails to load', () => {
    widgetState.status = 'ready';
    widgetState.declared = true;
    widgetState.loadWidget = async () => ({ default: () => null });
    lazyState.loadFailed = true;
    render(
      <PublicRelatedTopoSlot instUuid={INST_UUID} fallback={<div>default-topo</div>} />,
    );
    expect(screen.getByText('default-topo')).toBeTruthy();
    expect(screen.queryByText('public-related-topo')).toBeNull();
  });
});
