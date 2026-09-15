import { renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { resetAppCapabilityCache } from '../load';
import { useAppWidget } from '../useAppWidget';

const mocks = vi.hoisted(() => ({
  clientData: [] as Array<{ name: string }>,
  loading: false,
  loadOps: vi.fn(async () => ({
    widgets: {
      'ops-analysis.relatedTopology': () =>
        Promise.resolve({ default: () => null }),
    },
  })),
}));

vi.mock('@/context/client', () => ({
  useClientData: () => ({
    clientData: mocks.clientData,
    loading: mocks.loading,
  }),
}));

vi.mock('../catalog', () => ({
  APP_CAPABILITY_LOADERS: {
    'ops-analysis': () => mocks.loadOps(),
  },
}));

afterEach(() => {
  resetAppCapabilityCache();
  mocks.loadOps.mockClear();
});

describe('useAppWidget', () => {
  beforeEach(() => {
    mocks.clientData = [];
    mocks.loading = false;
  });

  it('stays undeclared when the sold module is missing', async () => {
    mocks.clientData = [{ name: 'monitor' }];
    const { result } = renderHook(() =>
      useAppWidget('ops-analysis.relatedTopology'),
    );

    await waitFor(() => {
      expect(result.current.status).toBe('unavailable');
    });
    expect(result.current.declared).toBe(false);
    expect(result.current.loadWidget).toBeNull();
    expect(mocks.loadOps).not.toHaveBeenCalled();
  });

  it('is ready only for declared keys after the module loads', async () => {
    mocks.clientData = [{ name: 'ops-analysis' }];
    const { result, rerender } = renderHook(
      ({ key }: { key: 'ops-analysis.relatedTopology' | 'ops-analysis.application3D' }) =>
        useAppWidget(key),
      { initialProps: { key: 'ops-analysis.relatedTopology' as const } },
    );

    await waitFor(() => {
      expect(result.current.status).toBe('ready');
    });
    expect(result.current.declared).toBe(true);
    expect(result.current.loadWidget).toBeTypeOf('function');

    rerender({ key: 'ops-analysis.application3D' });
    await waitFor(() => {
      expect(result.current.status).toBe('unavailable');
    });
    expect(result.current.declared).toBe(false);
    expect(result.current.loadWidget).toBeNull();
  });

  it('keeps a declared widget when clientData is a new array of the same apps', async () => {
    mocks.clientData = [{ name: 'ops-analysis' }];
    const { result, rerender } = renderHook(() =>
      useAppWidget('ops-analysis.relatedTopology'),
    );

    await waitFor(() => {
      expect(result.current.status).toBe('ready');
    });
    const loadWidget = result.current.loadWidget;

    mocks.clientData = [{ name: 'ops-analysis' }];
    rerender();

    expect(result.current.status).toBe('ready');
    expect(result.current.declared).toBe(true);
    expect(result.current.loadWidget).toBe(loadWidget);
    expect(mocks.loadOps).toHaveBeenCalledTimes(1);
  });
});
