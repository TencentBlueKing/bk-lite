import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const replace = vi.fn();
const push = vi.fn();
let currentSearch = new URLSearchParams('range=1h&traffic=all&application=store&q=checkout');

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace, push }),
  usePathname: () => '/rum/sessions',
  useSearchParams: () => currentSearch,
}));

import { useRumSearchParams } from '@/app/rum/lib/search-params';

describe('useRumSearchParams', () => {
  beforeEach(() => {
    replace.mockClear();
    push.mockClear();
    currentSearch = new URLSearchParams('range=1h&traffic=all&application=store&q=checkout');
  });

  it('reads range, traffic, application, and q from the URL', () => {
    const { result } = renderHook(() => useRumSearchParams());
    expect(result.current.range).toBe('1h');
    expect(result.current.traffic).toBe('all');
    expect(result.current.application).toBe('store');
    expect(result.current.q).toBe('checkout');
  });

  it('writes filters through router.replace by default', () => {
    const { result } = renderHook(() => useRumSearchParams());
    act(() => {
      result.current.setRange('7d');
    });
    expect(replace).toHaveBeenCalledWith('/rum/sessions?range=7d&traffic=all&application=store&q=checkout', {
      scroll: false,
    });

    act(() => {
      result.current.setTraffic('visitors');
    });
    expect(replace).toHaveBeenCalledWith('/rum/sessions?range=1h&application=store&q=checkout', {
      scroll: false,
    });

    act(() => {
      result.current.setApplication('');
    });
    expect(replace).toHaveBeenCalledWith('/rum/sessions?range=1h&traffic=all&q=checkout', {
      scroll: false,
    });
    act(() => {
      result.current.setQuery('');
    });
    expect(replace).toHaveBeenCalledWith('/rum/sessions?range=1h&traffic=all&application=store', {
      scroll: false,
    });
  });

  it('resets page in the same URL write when range or application changes', () => {
    currentSearch = new URLSearchParams('range=1h&application=store&page=3');
    const rangeHook = renderHook(() => useRumSearchParams());
    act(() => {
      rangeHook.result.current.setRange('7d');
    });
    expect(replace).toHaveBeenCalledWith('/rum/sessions?range=7d&application=store', {
      scroll: false,
    });

    currentSearch = new URLSearchParams('range=1h&application=store&page=3');
    const appHook = renderHook(() => useRumSearchParams());
    act(() => {
      appHook.result.current.setApplication('checkout');
    });
    expect(replace).toHaveBeenCalledWith('/rum/sessions?range=1h&application=checkout', {
      scroll: false,
    });
  });

  it('supports push when replace is disabled', () => {
    const { result } = renderHook(() => useRumSearchParams());
    act(() => {
      result.current.setParams({ range: '24h' }, { replace: false });
    });
    expect(push).toHaveBeenCalledWith('/rum/sessions?range=24h&traffic=all&application=store&q=checkout', {
      scroll: false,
    });
  });
});
