import { renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { resetAppCapabilityCache } from '../load';
import { useAppCapability } from '../useAppCapability';

const mocks = vi.hoisted(() => ({
  clientData: [] as Array<{ name: string }>,
  loading: false,
  loadAlarm: vi.fn(async () => ({ TrendChart: () => null })),
}));

vi.mock('@/context/client', () => ({
  useClientData: () => ({
    clientData: mocks.clientData,
    loading: mocks.loading,
  }),
}));

vi.mock('../catalog', () => ({
  APP_CAPABILITY_LOADERS: {
    alarm: () => mocks.loadAlarm(),
  },
}));

afterEach(() => {
  resetAppCapabilityCache();
  mocks.loadAlarm.mockClear();
});

describe('useAppCapability', () => {
  beforeEach(() => {
    mocks.clientData = [];
    mocks.loading = false;
  });

  it('stays unavailable and does not import when alarm is not authorized', async () => {
    mocks.clientData = [{ name: 'monitor' }];
    const { result } = renderHook(() => useAppCapability('alarm'));

    await waitFor(() => {
      expect(result.current.status).toBe('unavailable');
    });
    expect(mocks.loadAlarm).not.toHaveBeenCalled();
  });

  it('loads the capability after the user has alarm access', async () => {
    mocks.clientData = [{ name: 'alarm' }];
    const { result } = renderHook(() => useAppCapability('alarm'));

    await waitFor(() => {
      expect(result.current.status).toBe('ready');
    });
    expect(result.current.status === 'ready' && result.current.api.TrendChart).toBeTruthy();
    expect(mocks.loadAlarm).toHaveBeenCalledTimes(1);
  });
});
