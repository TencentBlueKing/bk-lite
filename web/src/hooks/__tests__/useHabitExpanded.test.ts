// @vitest-environment jsdom

import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { useHabitExpanded } from '@/hooks/useHabitExpanded';

describe('useHabitExpanded', () => {
  it('defaults to expanded when the server has no habit', async () => {
    const load = vi.fn().mockResolvedValue(null);
    const save = vi.fn().mockResolvedValue({ expanded: true });
    const { result } = renderHook(() =>
      useHabitExpanded({ load, save, defaultOpen: true }),
    );

    expect(result.current[0]).toBe(true);
    await waitFor(() => expect(load).toHaveBeenCalledTimes(1));
    expect(result.current[0]).toBe(true);
  });

  it('restores a collapsed habit from the server', async () => {
    const load = vi.fn().mockResolvedValue({ expanded: false });
    const save = vi.fn().mockResolvedValue({ expanded: false });
    const { result } = renderHook(() => useHabitExpanded({ load, save }));

    await waitFor(() => expect(result.current[0]).toBe(false));
  });

  it('keeps the new UI state even if save fails', async () => {
    const load = vi.fn().mockResolvedValue({ expanded: true });
    const save = vi.fn().mockRejectedValue(new Error('network'));
    const { result } = renderHook(() => useHabitExpanded({ load, save }));

    await waitFor(() => expect(load).toHaveBeenCalled());

    await act(async () => {
      result.current[1](false);
    });

    expect(result.current[0]).toBe(false);
    expect(save).toHaveBeenCalledWith({ expanded: false });
  });
});
