import { memo, useSyncExternalStore } from 'react';
import { act, render, renderHook, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { CarouselRemainingClock } from '@/app/ops-analysis/utils/carouselRemainingClock';
import type { CanvasType } from '@/app/ops-analysis/constants/canvasTypes';
import { CAROUSEL_UNAVAILABLE_RETRY_MS } from '@/app/ops-analysis/utils/carouselPlayer';
import {
  CAROUSEL_PLAYBACK_TICK_MS,
  carouselPlaybackNeedsReset,
  useCarouselPlaybackSession,
  type CarouselPlaybackSlide,
} from '@/app/ops-analysis/components/carousel/useCarouselPlaybackSession';

interface Gate {
  promise: Promise<unknown>;
  resolve: (value?: unknown) => void;
  reject: (error: unknown) => void;
}

const deferred = (): Gate => {
  let resolve: Gate['resolve'] = () => undefined;
  let reject: Gate['reject'] = () => undefined;
  const promise = new Promise((next, fail) => {
    resolve = next;
    reject = fail;
  });
  return { promise, resolve, reject };
};

const slide = (
  key: string,
  dwellSeconds = 30,
  resourceType: CanvasType = 'dashboard',
): CarouselPlaybackSlide => ({
  key,
  available: true,
  dwellSeconds,
  resourceType,
  canvasId: Number(key.replace(/\D/g, '')) || 1,
});

const settle = async () => {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
  });
};

describe('useCarouselPlaybackSession', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'setTimeout', 'clearTimeout'] });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('does not start the dwell until the current slide is confirmed, including the first and a retry', async () => {
    const gates: Gate[] = [];
    const loadDetail = vi.fn(() => {
      const gate = deferred();
      gates.push(gate);
      return gate.promise;
    });
    const { result } = renderHook(() => useCarouselPlaybackSession({
      slides: [slide('s0'), slide('s1', 10)],
      enabled: true,
      loadDetail,
    }));

    expect(loadDetail).toHaveBeenCalledTimes(1);
    expect(loadDetail.mock.calls[0][0].key).toBe('s0');
    expect(result.current.confirming).toBe(true);
    expect(result.current.ready).toBe(false);

    await act(async () => {
      vi.advanceTimersByTime(5_000);
    });
    expect(result.current.player.remainingMs).toBe(30_000);
    expect(loadDetail).toHaveBeenCalledTimes(1);

    await act(async () => {
      gates[0].reject({ status: 500 });
    });
    expect(loadDetail).toHaveBeenCalledTimes(2);
    expect(result.current.confirming).toBe(true);
    await act(async () => {
      vi.advanceTimersByTime(5_000);
    });
    expect(result.current.player.index).toBe(0);
    expect(result.current.player.remainingMs).toBe(30_000);

    await act(async () => {
      gates[1].resolve({ refresh_interval: 60_000, name: '盘' });
    });
    expect(result.current.ready).toBe(true);
    expect(result.current.initialDetail).toEqual({ refresh_interval: 60_000, name: '盘' });
    expect(result.current.confirming).toBe(false);
    await act(async () => {
      vi.advanceTimersByTime(CAROUSEL_PLAYBACK_TICK_MS * 4);
    });
    expect(result.current.player.remainingMs).toBe(30_000);
    expect(result.current.remainingClock.getSnapshot()).toBe(30_000 - CAROUSEL_PLAYBACK_TICK_MS * 4);
  });

  it('skips a failed first slide and confirms the next one', async () => {
    const gates: Gate[] = [];
    const loadDetail = vi.fn((target: CarouselPlaybackSlide) => {
      if (target.key === 's0') {
        return Promise.reject({ status: 404 });
      }
      const gate = deferred();
      gates.push(gate);
      return gate.promise;
    });
    const { result } = renderHook(() => useCarouselPlaybackSession({
      slides: [slide('s0'), slide('s1', 12)],
      enabled: true,
      loadDetail,
    }));

    await settle();
    await settle();
    expect(result.current.player.index).toBe(1);
    expect(result.current.player.slides[0].available).toBe(false);
    expect(result.current.player.remainingMs).toBe(12_000);
    expect(result.current.confirming).toBe(true);
    await act(async () => {
      vi.advanceTimersByTime(3_000);
    });
    expect(result.current.player.remainingMs).toBe(12_000);
    expect(loadDetail).toHaveBeenCalledTimes(2);
  });

  it('confirms again after a manual switch and skips when that slide fails', async () => {
    const gates: Gate[] = [];
    const loadDetail = vi.fn(() => {
      const gate = deferred();
      gates.push(gate);
      return gate.promise;
    });
    const { result } = renderHook(() => useCarouselPlaybackSession({
      slides: [slide('s0'), slide('s1')],
      enabled: true,
      loadDetail,
    }));

    await act(async () => {
      gates[0].resolve({});
    });
    act(() => {
      result.current.dispatch({ type: 'next' });
    });
    expect(result.current.player.index).toBe(1);
    expect(loadDetail).toHaveBeenCalledTimes(2);
    expect(loadDetail.mock.calls[1][0].key).toBe('s1');
    const dwell = result.current.player.remainingMs;
    await act(async () => {
      vi.advanceTimersByTime(2_000);
    });
    expect(result.current.player.remainingMs).toBe(dwell);

    await act(async () => {
      gates[1].reject({ status: 403 });
    });
    await settle();
    expect(result.current.player.slides.find((item) => item.key === 's1')?.available).toBe(false);
    expect(result.current.player.index).toBe(0);
    expect(loadDetail.mock.calls.length).toBeGreaterThanOrEqual(3);
    expect(loadDetail.mock.calls.at(-1)?.[0].key).toBe('s0');
  });

  it('cancels an in-flight confirm on pause or manual switch and confirms again later', async () => {
    const gates: Gate[] = [];
    const loadDetail = vi.fn(() => {
      const gate = deferred();
      gates.push(gate);
      return gate.promise;
    });
    const { result } = renderHook(() => useCarouselPlaybackSession({
      slides: [slide('s0'), slide('s1')],
      enabled: true,
      loadDetail,
    }));

    const firstSignal = loadDetail.mock.calls[0][1] as AbortSignal;
    act(() => {
      result.current.dispatch({ type: 'togglePause' });
    });
    expect(firstSignal.aborted).toBe(true);
    await act(async () => {
      gates[0].reject({ status: 500 });
    });
    expect(result.current.player.index).toBe(0);
    expect(result.current.player.slides[0].available).toBe(true);
    expect(loadDetail).toHaveBeenCalledTimes(1);

    act(() => {
      result.current.dispatch({ type: 'togglePause' });
    });
    expect(loadDetail).toHaveBeenCalledTimes(2);
    expect((loadDetail.mock.calls[1][1] as AbortSignal).aborted).toBe(false);

    act(() => {
      result.current.dispatch({ type: 'next' });
    });
    expect((loadDetail.mock.calls[1][1] as AbortSignal).aborted).toBe(true);
    expect(loadDetail).toHaveBeenCalledTimes(3);
    expect(loadDetail.mock.calls[2][0].key).toBe('s1');
    await act(async () => {
      gates[1].reject({ status: 500 });
      gates[1].reject({ status: 500 });
    });
    expect(result.current.player.slides[0].available).toBe(true);
  });

  it('waits ten seconds when every slide fails, including a single-slide loop', async () => {
    const loadDetail = vi.fn(() => Promise.reject({ status: 404 }));
    const single = renderHook(() => useCarouselPlaybackSession({
      slides: [slide('s0')],
      enabled: true,
      loadDetail,
    }));
    await settle();
    await settle();
    expect(single.result.current.player.index).toBe(-1);
    expect(single.result.current.player.holdMs).toBe(CAROUSEL_UNAVAILABLE_RETRY_MS);
    expect(loadDetail).toHaveBeenCalledTimes(1);

    await act(async () => {
      vi.advanceTimersByTime(CAROUSEL_UNAVAILABLE_RETRY_MS - CAROUSEL_PLAYBACK_TICK_MS);
    });
    expect(single.result.current.player.index).toBe(-1);
    expect(loadDetail).toHaveBeenCalledTimes(1);

    await act(async () => {
      vi.advanceTimersByTime(CAROUSEL_PLAYBACK_TICK_MS);
    });
    await settle();
    expect(loadDetail).toHaveBeenCalledTimes(2);

    single.unmount();
    loadDetail.mockClear();
    const both = renderHook(() => useCarouselPlaybackSession({
      slides: [slide('s0'), slide('s1')],
      enabled: true,
      loadDetail,
    }));
    await settle();
    await settle();
    await settle();
    expect(both.result.current.player.index).toBe(-1);
    expect(loadDetail).toHaveBeenCalledTimes(2);
    await act(async () => {
      vi.advanceTimersByTime(CAROUSEL_UNAVAILABLE_RETRY_MS);
    });
    await settle();
    expect(loadDetail.mock.calls.length).toBeGreaterThan(2);
  });

  it('leaves a 401 to the global session handler', async () => {
    const loadDetail = vi.fn(() => Promise.reject({ status: 401 }));
    const { result } = renderHook(() => useCarouselPlaybackSession({
      slides: [slide('s0', 30), slide('s1')],
      enabled: true,
      loadDetail,
    }));
    await settle();
    await settle();
    expect(loadDetail).toHaveBeenCalledTimes(1);
    expect(result.current.player.index).toBe(0);
    expect(result.current.player.slides[0].available).toBe(true);
    expect(result.current.player.holdMs).toBe(0);
    expect(result.current.ready).toBe(false);
    await act(async () => {
      vi.advanceTimersByTime(5_000);
    });
    expect(result.current.player.remainingMs).toBe(30_000);
    expect(loadDetail).toHaveBeenCalledTimes(1);
  });

  it('keeps dwell, pause, and manual next once confirmation succeeds', async () => {
    const gates: Gate[] = [];
    const loadDetail = vi.fn(() => {
      const gate = deferred();
      gates.push(gate);
      return gate.promise;
    });
    const { result } = renderHook(() => useCarouselPlaybackSession({
      slides: [slide('s0'), slide('s1')],
      enabled: true,
      loadDetail,
    }));
    await act(async () => {
      gates[0].resolve({});
    });
    await act(async () => {
      vi.advanceTimersByTime(1_000);
    });
    const remaining = result.current.remainingClock.getSnapshot();
    expect(remaining).toBeLessThan(30_000);
    expect(result.current.player.remainingMs).toBe(30_000);
    act(() => {
      result.current.dispatch({ type: 'togglePause' });
    });
    expect(result.current.player.remainingMs).toBe(remaining);
    await act(async () => {
      vi.advanceTimersByTime(2_000);
    });
    expect(result.current.remainingClock.getSnapshot()).toBe(remaining);
    act(() => {
      result.current.dispatch({ type: 'togglePause' });
      result.current.dispatch({ type: 'next' });
    });
    expect(result.current.player.index).toBe(1);
    expect(result.current.ready).toBe(false);
    expect(loadDetail.mock.calls.at(-1)?.[0].key).toBe('s1');
  });

  it('drops an unfinished prefetch when playback pauses, then prefetches again', async () => {
    const gates: Gate[] = [];
    const loadDetail = vi.fn(() => {
      const gate = deferred();
      gates.push(gate);
      return gate.promise;
    });
    const { result } = renderHook(() => useCarouselPlaybackSession({
      slides: [slide('s0', 5), slide('s1')],
      enabled: true,
      loadDetail,
    }));
    await act(async () => {
      gates[0].resolve({});
    });
    await act(async () => {
      vi.advanceTimersByTime(3_000);
    });
    expect(loadDetail.mock.calls[1]?.[0].key).toBe('s1');
    const prefetchSignal = loadDetail.mock.calls[1][1] as AbortSignal;
    act(() => {
      result.current.dispatch({ type: 'togglePause' });
    });
    expect(prefetchSignal.aborted).toBe(true);
    act(() => {
      result.current.dispatch({ type: 'togglePause' });
    });
    expect(loadDetail.mock.calls.filter((call) => call[0].key === 's1')).toHaveLength(2);
    expect((loadDetail.mock.calls.at(-1)?.[1] as AbortSignal).aborted).toBe(false);
  });

  it('does not reconfirm the current slide when it is reordered or its dwell changes', async () => {
    const loadDetail = vi.fn(() => Promise.resolve({ id: 1 }));
    const { result, rerender } = renderHook(
      ({ slides }: { slides: CarouselPlaybackSlide[] }) => useCarouselPlaybackSession({
        slides,
        enabled: true,
        loadDetail,
        startPaused: true,
        confirmWhilePaused: true,
      }),
      { initialProps: { slides: [slide('s0', 30), slide('s1', 20)] } },
    );
    await settle();
    expect(loadDetail).toHaveBeenCalledTimes(1);
    expect(result.current.ready).toBe(true);
    const remaining = result.current.player.remainingMs;

    rerender({ slides: [slide('s1', 20), slide('s0', 45)] });
    await settle();

    expect(loadDetail).toHaveBeenCalledTimes(1);
    expect(result.current.ready).toBe(true);
    expect(result.current.confirming).toBe(false);
    expect(result.current.player.slides[result.current.player.index]?.key).toBe('s0');
    expect(result.current.player.slides[result.current.player.index]?.dwellSeconds).toBe(45);
    expect(result.current.player.remainingMs).toBe(remaining + 15_000);
  });

  it('does not rerender the playback host while only the dwell clock advances', async () => {
    const gates: Gate[] = [];
    const loadDetail = vi.fn(() => {
      const gate = deferred();
      gates.push(gate);
      return gate.promise;
    });
    let hostRenders = 0;
    let frameRenders = 0;
    const Frame = memo(function Frame({ visit }: { visit: number }) {
      frameRenders += 1;
      return <span data-testid="frame">{visit}</span>;
    });
    function Remaining({ clock }: { clock: CarouselRemainingClock }) {
      const remaining = useSyncExternalStore(clock.subscribe, clock.getSnapshot, clock.getSnapshot);
      return <span data-testid="remaining">{remaining}</span>;
    }
    function Host() {
      hostRenders += 1;
      const session = useCarouselPlaybackSession({
        slides: [slide('s0'), slide('s1')],
        enabled: true,
        loadDetail,
      });
      return (
        <>
          <Frame visit={session.player.visit} />
          <Remaining clock={session.remainingClock} />
        </>
      );
    }
    render(<Host />);
    await act(async () => {
      gates[0].resolve({ id: 1 });
      await Promise.resolve();
      await Promise.resolve();
    });
    const hostAfterReady = hostRenders;
    const frameAfterReady = frameRenders;
    await act(async () => {
      vi.advanceTimersByTime(CAROUSEL_PLAYBACK_TICK_MS * 4);
    });
    expect(hostRenders).toBe(hostAfterReady);
    expect(frameRenders).toBe(frameAfterReady);
    expect(screen.getByTestId('remaining').textContent).toBe(String(30_000 - CAROUSEL_PLAYBACK_TICK_MS * 4));
  });

  it('still reconfirms when the playlist is reloaded or the current slide becomes unavailable', () => {
    const current = { resetKey: '1', key: 's0', available: true };
    const slides = [{ key: 's0', available: true }, { key: 's1', available: true }];
    expect(carouselPlaybackNeedsReset(current, { resetKey: '1', slides })).toBe(false);
    expect(carouselPlaybackNeedsReset(current, {
      resetKey: '1',
      slides: [{ key: 's1', available: true }, { key: 's0', available: true }],
    })).toBe(false);
    expect(carouselPlaybackNeedsReset(current, { resetKey: '2', slides })).toBe(true);
    expect(carouselPlaybackNeedsReset(current, {
      resetKey: '1',
      slides: [{ key: 's0', available: false }],
    })).toBe(true);
    expect(carouselPlaybackNeedsReset(current, {
      resetKey: '1',
      slides: [{ key: 's1', available: true }],
    })).toBe(true);
  });
});
