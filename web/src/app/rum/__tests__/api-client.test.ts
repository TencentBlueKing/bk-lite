import { renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const { get, post, put, patch, del, requestState } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  patch: vi.fn(),
  del: vi.fn(),
  requestState: { isLoading: false },
}));

vi.mock('@/utils/request', () => ({
  default: () => ({
    get,
    post,
    put,
    patch,
    del,
    isLoading: requestState.isLoading,
  }),
}));

import { useRumQueries } from '@/app/rum/api';
import { useRumApi, useRumAuthReady } from '@/app/rum/api/client';

describe('rum API client identity', () => {
  it('keeps the client object stable across rerenders', () => {
    const { result, rerender } = renderHook(() => useRumApi());
    const first = result.current;
    rerender();
    expect(result.current).toBe(first);
  });

  it('keeps request functions stable when the shared client finishes attaching a token', () => {
    requestState.isLoading = true;
    const { result, rerender } = renderHook(() => useRumApi());
    const first = result.current;
    requestState.isLoading = false;
    rerender();
    expect(result.current).toBe(first);
  });

  it('reports authReady only after the shared client has a token', () => {
    requestState.isLoading = true;
    const { result, rerender } = renderHook(() => useRumAuthReady());
    expect(result.current).toBe(false);
    requestState.isLoading = false;
    rerender();
    expect(result.current).toBe(true);
  });

  it('keeps getAnalyticsCatalog stable so catalog pages do not refetch every render', () => {
    requestState.isLoading = false;
    const { result, rerender } = renderHook(() => useRumQueries());
    const first = result.current.getAnalyticsCatalog;
    rerender();
    expect(result.current.getAnalyticsCatalog).toBe(first);
  });

  it('keeps listApplications stable so setup and application lists do not refetch every render', () => {
    requestState.isLoading = false;
    const { result, rerender } = renderHook(() => useRumQueries());
    const first = result.current.listApplications;
    rerender();
    expect(result.current.listApplications).toBe(first);
  });

  it('does not special-case RUM GET error toasts', async () => {
    get.mockResolvedValueOnce([]);
    const { result } = renderHook(() => useRumApi());
    await result.current.get('/applications/', { params: { range: '24h' } });
    expect(get).toHaveBeenCalledWith('/rum/applications', {
      params: { range: '24h' },
    });
  });
});
