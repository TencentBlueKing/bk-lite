// @vitest-environment jsdom

import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useCanvasPeriodicRefresh } from '@/app/ops-analysis/hooks/useCanvasPeriodicRefresh';

const testState = vi.hoisted(() => ({
  messageError: vi.fn(),
}));

vi.mock('antd', async () => {
  const actual = await vi.importActual<typeof import('antd')>('antd');
  return {
    ...actual,
    message: {
      ...actual.message,
      error: testState.messageError,
    },
  };
});

vi.mock('@/utils/i18n', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const setDocumentHidden = (hidden: boolean) => {
  Object.defineProperty(document, 'hidden', {
    configurable: true,
    get: () => hidden,
  });
};

describe('useCanvasPeriodicRefresh', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    testState.messageError.mockReset();
    setDocumentHidden(false);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('drives the timer from the session override and does not patch without persist permission', async () => {
    const onPeriodicRefresh = vi.fn();
    const patchRefreshInterval = vi.fn();
    const { result } = renderHook(() =>
      useCanvasPeriodicRefresh({
        canvasId: 1,
        savedInterval: 0,
        canPersist: false,
        patchRefreshInterval,
        onPeriodicRefresh,
      }),
    );

    act(() => {
      result.current.handleFrequencyChange(60000);
    });

    expect(result.current.effectiveRefreshInterval).toBe(60000);
    expect(patchRefreshInterval).not.toHaveBeenCalled();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(60000);
    });
    expect(onPeriodicRefresh).toHaveBeenCalledTimes(1);
    expect(onPeriodicRefresh).toHaveBeenCalledWith('periodic');
  });

  it('rolls the dropdown and timer back to the saved interval when persist fails', async () => {
    const patchRefreshInterval = vi.fn().mockRejectedValue(new Error('fail'));
    const { result } = renderHook(() =>
      useCanvasPeriodicRefresh({
        canvasId: 1,
        savedInterval: 0,
        canPersist: true,
        patchRefreshInterval,
        onPeriodicRefresh: vi.fn(),
      }),
    );

    act(() => {
      result.current.handleFrequencyChange(60000);
    });
    expect(result.current.effectiveRefreshInterval).toBe(60000);

    await act(async () => {
      await Promise.resolve();
    });
    expect(result.current.effectiveRefreshInterval).toBe(0);
    expect(testState.messageError).toHaveBeenCalledWith('common.saveFailed');
  });

  it('does not fire a visibility refresh when the interval is off', () => {
    const onPeriodicRefresh = vi.fn();
    renderHook(() =>
      useCanvasPeriodicRefresh({
        canvasId: 1,
        savedInterval: 0,
        canPersist: false,
        onPeriodicRefresh,
      }),
    );

    setDocumentHidden(true);
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
    });
    setDocumentHidden(false);
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
    });

    expect(onPeriodicRefresh).not.toHaveBeenCalled();
  });

  it('silently refreshes once when becoming visible with an active interval', () => {
    const onPeriodicRefresh = vi.fn();
    const { result } = renderHook(() =>
      useCanvasPeriodicRefresh({
        canvasId: 1,
        savedInterval: 60000,
        canPersist: false,
        onPeriodicRefresh,
      }),
    );

    expect(result.current.effectiveRefreshInterval).toBe(60000);
    setDocumentHidden(true);
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
    });
    expect(onPeriodicRefresh).not.toHaveBeenCalled();

    setDocumentHidden(false);
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
    });
    expect(onPeriodicRefresh).toHaveBeenCalledTimes(1);
    expect(onPeriodicRefresh).toHaveBeenCalledWith('visibility');
  });

  it('keeps a session override when savedInterval later hydrates on the same canvas', () => {
    const { result, rerender } = renderHook(
      ({ savedInterval }) =>
        useCanvasPeriodicRefresh({
          canvasId: 1,
          savedInterval,
          canPersist: false,
          onPeriodicRefresh: vi.fn(),
        }),
      { initialProps: { savedInterval: 0 } },
    );

    act(() => {
      result.current.handleFrequencyChange(60000);
    });
    expect(result.current.effectiveRefreshInterval).toBe(60000);

    rerender({ savedInterval: 300000 });
    expect(result.current.effectiveRefreshInterval).toBe(60000);
  });

  it('still hydrates savedInterval when the user has not overridden this session', () => {
    const { result, rerender } = renderHook(
      ({ savedInterval }) =>
        useCanvasPeriodicRefresh({
          canvasId: 1,
          savedInterval,
          canPersist: false,
          onPeriodicRefresh: vi.fn(),
        }),
      { initialProps: { savedInterval: 0 } },
    );

    rerender({ savedInterval: 60000 });
    expect(result.current.effectiveRefreshInterval).toBe(60000);
  });

  it('resets a session override when the canvas id changes', () => {
    const { result, rerender } = renderHook(
      ({ canvasId, savedInterval }) =>
        useCanvasPeriodicRefresh({
          canvasId,
          savedInterval,
          canPersist: false,
          onPeriodicRefresh: vi.fn(),
        }),
      { initialProps: { canvasId: 1 as number | undefined, savedInterval: 0 } },
    );

    act(() => {
      result.current.handleFrequencyChange(60000);
    });
    expect(result.current.effectiveRefreshInterval).toBe(60000);

    rerender({ canvasId: 2, savedInterval: 0 });
    expect(result.current.effectiveRefreshInterval).toBe(0);

    rerender({ canvasId: 2, savedInterval: 300000 });
    expect(result.current.effectiveRefreshInterval).toBe(300000);
  });

  it('promotes a persisted interval to the saved baseline without rolling the session back', async () => {
    const onSavedIntervalChange = vi.fn();
    const patchRefreshInterval = vi.fn().mockResolvedValue(undefined);
    const { result, rerender } = renderHook(
      ({ savedInterval }) =>
        useCanvasPeriodicRefresh({
          canvasId: 1,
          savedInterval,
          canPersist: true,
          patchRefreshInterval,
          onPeriodicRefresh: vi.fn(),
          onSavedIntervalChange,
        }),
      { initialProps: { savedInterval: 0 } },
    );

    act(() => {
      result.current.handleFrequencyChange(60000);
    });
    expect(result.current.effectiveRefreshInterval).toBe(60000);

    await act(async () => {
      await Promise.resolve();
    });
    expect(patchRefreshInterval).toHaveBeenCalledWith(60000);
    expect(onSavedIntervalChange).toHaveBeenCalledWith(60000);
    expect(result.current.effectiveRefreshInterval).toBe(60000);

    rerender({ savedInterval: 60000 });
    expect(result.current.effectiveRefreshInterval).toBe(60000);
  });

  it('does not immediately request after turning the interval on', async () => {
    const onPeriodicRefresh = vi.fn();
    const { result } = renderHook(() =>
      useCanvasPeriodicRefresh({
        canvasId: 1,
        savedInterval: 0,
        canPersist: false,
        onPeriodicRefresh,
      }),
    );

    act(() => {
      result.current.handleFrequencyChange(60000);
    });
    expect(onPeriodicRefresh).not.toHaveBeenCalled();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(59999);
    });
    expect(onPeriodicRefresh).not.toHaveBeenCalled();
  });
});
