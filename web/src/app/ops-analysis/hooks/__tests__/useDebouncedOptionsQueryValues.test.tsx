// @vitest-environment jsdom

import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { useDebouncedOptionsQueryValues } from '@/app/ops-analysis/hooks/useDebouncedOptionsQueryValues';
import { OPTIONS_QUERY_TEXT_DEBOUNCE_MS } from '@/app/ops-analysis/utils/optionsQueryTextDebounce';

afterEach(() => {
  vi.useRealTimers();
});

describe('useDebouncedOptionsQueryValues', () => {
  it('publishes the first text value immediately and trails later edits', async () => {
    vi.useFakeTimers();
    const { result, rerender } = renderHook(
      ({ values }: { values: Record<string, unknown> }) => (
        useDebouncedOptionsQueryValues(values, ['room'])
      ),
      { initialProps: { values: { room: 'east', zone: 'z1' } } },
    );

    expect(result.current).toEqual({ room: 'east', zone: 'z1' });

    rerender({ values: { room: 'e', zone: 'z1' } });
    expect(result.current.room).toBe('east');

    rerender({ values: { room: 'ea', zone: 'z2' } });
    expect(result.current).toEqual({ room: 'east', zone: 'z2' });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(OPTIONS_QUERY_TEXT_DEBOUNCE_MS - 1);
    });
    expect(result.current.room).toBe('east');

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });
    expect(result.current.room).toBe('ea');
  });

  it('debounces the first character typed into an empty field and publishes a clear immediately', async () => {
    vi.useFakeTimers();
    const { result, rerender } = renderHook(
      ({ values }: { values: Record<string, unknown> }) => (
        useDebouncedOptionsQueryValues(values, ['room'])
      ),
      { initialProps: { values: { room: '' } } },
    );

    rerender({ values: { room: 'a' } });
    rerender({ values: { room: 'ab' } });
    expect(result.current.room).toBe('');

    await act(async () => {
      await vi.advanceTimersByTimeAsync(OPTIONS_QUERY_TEXT_DEBOUNCE_MS);
    });
    expect(result.current.room).toBe('ab');

    rerender({ values: { room: 'abc' } });
    rerender({ values: { room: null } });
    expect(result.current.room).toBeNull();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(OPTIONS_QUERY_TEXT_DEBOUNCE_MS);
    });
    expect(result.current.room).toBeNull();
  });

  it('adopts a newly appearing text key immediately', () => {
    vi.useFakeTimers();
    const { result, rerender } = renderHook(
      ({ values, keys }: { values: Record<string, unknown>; keys: string[] }) => (
        useDebouncedOptionsQueryValues(values, keys)
      ),
      { initialProps: { values: { room: '' }, keys: ['room'] } },
    );

    rerender({ values: { room: '', extra: 'ready' }, keys: ['room', 'extra'] });
    expect(result.current.extra).toBe('ready');
  });
});
