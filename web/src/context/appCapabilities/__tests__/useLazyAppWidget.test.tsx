import { renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { useLazyAppWidget } from '../useLazyAppWidget';

describe('useLazyAppWidget', () => {
  it('does not import until the host first activates the widget', async () => {
    const loadWidget = vi.fn(async () => ({ default: () => null }));

    const { result, rerender } = renderHook(
      ({ active }: { active: boolean }) =>
        useLazyAppWidget({ loadWidget, active }),
      { initialProps: { active: false } },
    );

    expect(loadWidget).not.toHaveBeenCalled();
    expect(result.current.Widget).toBeNull();

    rerender({ active: true });
    await waitFor(() => {
      expect(result.current.Widget).toBeTruthy();
    });
    expect(loadWidget).toHaveBeenCalledTimes(1);

    rerender({ active: false });
    rerender({ active: true });
    expect(loadWidget).toHaveBeenCalledTimes(1);
    expect(result.current.Widget).toBeTruthy();
  });

  it('does not drop a loaded widget when the loader identity changes', async () => {
    const first = vi.fn(async () => ({ default: () => null }));
    const second = vi.fn(async () => ({ default: () => null }));

    const { result, rerender } = renderHook(
      ({ loadWidget }: { loadWidget: () => Promise<{ default: unknown }> }) =>
        useLazyAppWidget({ loadWidget, active: true }),
      { initialProps: { loadWidget: first } },
    );

    await waitFor(() => {
      expect(result.current.Widget).toBeTruthy();
    });
    expect(first).toHaveBeenCalledTimes(1);

    rerender({ loadWidget: second });
    expect(second).not.toHaveBeenCalled();
    expect(result.current.Widget).toBeTruthy();
    expect(result.current.loadFailed).toBe(false);
  });

  it('does not drop a loaded widget when the loader becomes null', async () => {
    const loadWidget = vi.fn(async () => ({ default: () => null }));

    const { result, rerender } = renderHook(
      ({
        loader,
      }: {
        loader: (() => Promise<{ default: unknown }>) | null;
      }) => useLazyAppWidget({ loadWidget: loader, active: true }),
      { initialProps: { loader: loadWidget as (() => Promise<{ default: unknown }>) | null } },
    );

    await waitFor(() => {
      expect(result.current.Widget).toBeTruthy();
    });

    rerender({ loader: null });
    expect(result.current.Widget).toBeTruthy();
    expect(result.current.loadFailed).toBe(false);
    expect(loadWidget).toHaveBeenCalledTimes(1);
  });

  it('reimports after an explicit reload', async () => {
    const loadWidget = vi.fn(async () => ({ default: () => null }));

    const { result, rerender } = renderHook(
      ({ reloadKey }: { reloadKey: number }) =>
        useLazyAppWidget({ loadWidget, active: true, reloadKey }),
      { initialProps: { reloadKey: 0 } },
    );

    await waitFor(() => {
      expect(result.current.Widget).toBeTruthy();
    });
    expect(loadWidget).toHaveBeenCalledTimes(1);

    rerender({ reloadKey: 1 });
    await waitFor(() => {
      expect(loadWidget).toHaveBeenCalledTimes(2);
    });
  });
});
