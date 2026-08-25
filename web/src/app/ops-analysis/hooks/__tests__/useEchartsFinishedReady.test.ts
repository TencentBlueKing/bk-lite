import { act, renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { useEchartsFinishedReady } from '@/app/ops-analysis/hooks/useEchartsFinishedReady';

describe('useEchartsFinishedReady', () => {
  it('does not report ready until the chart finished event fires', () => {
    const onReady = vi.fn();
    const { result } = renderHook(() =>
      useEchartsFinishedReady({
        loading: false,
        isDataReady: true,
        onReady,
      }),
    );

    expect(onReady).not.toHaveBeenCalled();

    act(() => {
      result.current.onEvents.finished();
    });

    expect(onReady).toHaveBeenCalledTimes(1);
    expect(onReady).toHaveBeenCalledWith(true);
  });

  it('reports empty immediately without waiting for finished', () => {
    const onReady = vi.fn();
    renderHook(() =>
      useEchartsFinishedReady({
        loading: false,
        isDataReady: false,
        onReady,
      }),
    );

    expect(onReady).toHaveBeenCalledWith(false);
  });

  it('ignores finished while loading', () => {
    const onReady = vi.fn();
    const { result } = renderHook(() =>
      useEchartsFinishedReady({
        loading: true,
        isDataReady: true,
        onReady,
      }),
    );

    act(() => {
      result.current.onEvents.finished();
    });

    expect(onReady).not.toHaveBeenCalled();
  });

  it('waits for canReportReady after the chart has already finished', () => {
    const onReady = vi.fn();
    const { result, rerender } = renderHook(
      ({ canReportReady }) =>
        useEchartsFinishedReady({
          loading: false,
          isDataReady: true,
          canReportReady,
          onReady,
        }),
      { initialProps: { canReportReady: false } },
    );

    act(() => {
      result.current.onEvents.finished();
    });
    expect(onReady).not.toHaveBeenCalled();

    rerender({ canReportReady: true });
    expect(onReady).toHaveBeenCalledTimes(1);
    expect(onReady).toHaveBeenCalledWith(true);
  });
});
