// @vitest-environment jsdom

import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { usePersistedCollapseOpen } from '@/components/collapse';

const STORAGE_KEY = 'test.collapse.expanded';

afterEach(() => {
  window.localStorage.removeItem(STORAGE_KEY);
});

describe('usePersistedCollapseOpen', () => {
  it('defaults to expanded when nothing is stored', () => {
    const { result } = renderHook(() => usePersistedCollapseOpen(STORAGE_KEY));
    expect(result.current[0]).toBe(true);
  });

  it('restores a collapsed preference from localStorage', () => {
    window.localStorage.setItem(STORAGE_KEY, '0');
    const { result } = renderHook(() => usePersistedCollapseOpen(STORAGE_KEY));
    expect(result.current[0]).toBe(false);
  });

  it('persists toggle changes so the next visit keeps the habit', () => {
    const { result } = renderHook(() => usePersistedCollapseOpen(STORAGE_KEY));

    act(() => {
      result.current[1](false);
    });

    expect(result.current[0]).toBe(false);
    expect(window.localStorage.getItem(STORAGE_KEY)).toBe('0');

    act(() => {
      result.current[1](true);
    });

    expect(result.current[0]).toBe(true);
    expect(window.localStorage.getItem(STORAGE_KEY)).toBe('1');
  });
});
