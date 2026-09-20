import { renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const get = vi.fn();
const post = vi.fn();
const put = vi.fn();
const patch = vi.fn();
const del = vi.fn();

vi.mock('@/utils/request', () => ({
  default: () => ({ get, post, put, patch, del, isLoading: false }),
}));

import { useRumQueries } from '@/app/rum/api';
import { useRumApi } from '@/app/rum/api/client';

describe('rum API client identity', () => {
  it('keeps the client object stable across rerenders', () => {
    const { result, rerender } = renderHook(() => useRumApi());
    const first = result.current;
    rerender();
    expect(result.current).toBe(first);
  });

  it('keeps getAnalyticsCatalog stable so catalog pages do not refetch every render', () => {
    const { result, rerender } = renderHook(() => useRumQueries());
    const first = result.current.getAnalyticsCatalog;
    rerender();
    expect(result.current.getAnalyticsCatalog).toBe(first);
  });

  it('keeps listApplications stable so setup and application lists do not refetch every render', () => {
    const { result, rerender } = renderHook(() => useRumQueries());
    const first = result.current.listApplications;
    rerender();
    expect(result.current.listApplications).toBe(first);
  });

  it('does not special-case RUM GET error toasts', async () => {
    get.mockResolvedValueOnce([]);
    const { result } = renderHook(() => useRumApi());
    await result.current.get('/applications/', { params: { range: '24h' } });
    expect(get).toHaveBeenCalledWith('/rum/applications/', {
      params: { range: '24h' },
    });
  });
});
