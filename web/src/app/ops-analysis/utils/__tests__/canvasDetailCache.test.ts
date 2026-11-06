import { renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useCarouselApi } from '@/app/ops-analysis/api/carousel';
import { loadPlaybackCanvasDetail } from '@/app/ops-analysis/context/playbackInitialDetail';
import {
  CANVAS_DETAIL_CACHE_TTL_MS,
  clearCanvasDetailCache,
  fetchSharedCanvasDetail,
  readCachedCanvasDetail,
} from '@/app/ops-analysis/utils/canvasDetailCache';

const api = vi.hoisted(() => ({
  get: vi.fn(async () => ({ id: 4, name: 'cached' })),
}));

vi.mock('@/utils/request', () => ({
  default: () => ({
    get: api.get,
    post: vi.fn(),
    patch: vi.fn(),
    del: vi.fn(),
  }),
}));

const deferred = () => {
  let resolve: (value: unknown) => void = () => undefined;
  let reject: (error: unknown) => void = () => undefined;
  const promise = new Promise((next, fail) => {
    resolve = next;
    reject = fail;
  });
  return { promise, resolve, reject };
};

describe('canvas detail cache', () => {
  beforeEach(() => {
    clearCanvasDetailCache();
    api.get.mockReset();
    api.get.mockResolvedValue({ id: 4, name: 'cached' });
  });

  it('reuses one successful body for prefetch and playback enter', async () => {
    const { result } = renderHook(() => useCarouselApi());
    const first = await result.current.prefetchCanvasDetail('dashboard', 4);
    const second = await result.current.prefetchCanvasDetail('dashboard', 4);
    const fetchDetail = vi.fn(async () => ({ id: 4, name: 'other' }));
    const entered = await loadPlaybackCanvasDetail(null, 'dashboard', '4', fetchDetail);

    expect(api.get).toHaveBeenCalledTimes(1);
    expect(String(api.get.mock.calls[0][0])).toBe('/operation_analysis/api/dashboard/4/');
    expect(second).toBe(first);
    expect(entered).toBe(first);
    expect(fetchDetail).not.toHaveBeenCalled();
  });

  it('keeps entries isolated by resource type and canvas id', async () => {
    const dashboard = { id: 7, name: 'dash' };
    const topology = { id: 7, name: 'topo' };
    const other = { id: 8, name: 'other' };
    await fetchSharedCanvasDetail('dashboard', 7, async () => dashboard);
    await fetchSharedCanvasDetail('topology', 7, async () => topology);
    await fetchSharedCanvasDetail('dashboard', 8, async () => other);

    const fetcher = vi.fn(async () => ({ id: 0 }));
    expect(await fetchSharedCanvasDetail('dashboard', 7, fetcher)).toBe(dashboard);
    expect(await fetchSharedCanvasDetail('topology', 7, fetcher)).toBe(topology);
    expect(await fetchSharedCanvasDetail('dashboard', 8, fetcher)).toBe(other);
    expect(fetcher).not.toHaveBeenCalled();
  });

  it('refetches after the 45s ttl and does not keep a failed response', async () => {
    let now = 1_000;
    const clock = () => now;
    const fetcher = vi.fn(async () => ({ id: now }));
    const first = await fetchSharedCanvasDetail('screen', 3, fetcher, undefined, clock);
    expect(await fetchSharedCanvasDetail('screen', 3, fetcher, undefined, clock)).toBe(first);
    expect(fetcher).toHaveBeenCalledTimes(1);

    now += CANVAS_DETAIL_CACHE_TTL_MS;
    expect(readCachedCanvasDetail('screen', 3, now).hit).toBe(false);
    const second = await fetchSharedCanvasDetail('screen', 3, fetcher, undefined, clock);
    expect(second).toEqual({ id: now });
    expect(fetcher).toHaveBeenCalledTimes(2);

    fetcher.mockRejectedValueOnce({ status: 500 });
    await expect(fetchSharedCanvasDetail('report', 9, fetcher, undefined, clock)).rejects.toEqual({ status: 500 });
    fetcher.mockResolvedValueOnce({ id: 9 });
    await fetchSharedCanvasDetail('report', 9, fetcher, undefined, clock);
    expect(fetcher).toHaveBeenCalledTimes(4);
  });

  it('dedupes an in-flight detail and still resolves the other waiter after one abort', async () => {
    const gate = deferred();
    let calls = 0;
    let requestSignal: AbortSignal | undefined;
    const fetcher = (signal: AbortSignal) => {
      calls += 1;
      requestSignal = signal;
      return gate.promise;
    };
    const aborted = new AbortController();
    const staying = new AbortController();
    const left = fetchSharedCanvasDetail('architecture', 2, fetcher, aborted.signal);
    const right = fetchSharedCanvasDetail('architecture', 2, fetcher, staying.signal);
    await Promise.resolve();
    expect(calls).toBe(1);

    aborted.abort();
    await expect(left).rejects.toMatchObject({ name: 'AbortError' });
    expect(requestSignal?.aborted).toBe(false);

    const body = { id: 2, name: 'arch' };
    gate.resolve(body);
    await expect(right).resolves.toBe(body);
    expect(readCachedCanvasDetail('architecture', 2)).toEqual({ hit: true, detail: body });
  });

  it('does not drop a successful entry when a later request is aborted', async () => {
    const saved = { id: 1, name: 'kept' };
    await fetchSharedCanvasDetail('dashboard', 1, async () => saved);
    const controller = new AbortController();
    let requestSignal: AbortSignal | undefined;
    const pending = fetchSharedCanvasDetail('networkTopology', 6, (signal) => new Promise((_resolve, reject) => {
      requestSignal = signal;
      signal.addEventListener('abort', () => {
        reject(Object.assign(new Error('aborted'), { name: 'AbortError' }));
      });
    }), controller.signal);
    controller.abort();
    await expect(pending).rejects.toMatchObject({ name: 'AbortError' });
    expect(requestSignal?.aborted).toBe(true);
    await Promise.resolve();
    expect(readCachedCanvasDetail('dashboard', 1)).toEqual({ hit: true, detail: saved });
    expect(readCachedCanvasDetail('networkTopology', 6).hit).toBe(false);

    const controllerAfterHit = new AbortController();
    const hit = await fetchSharedCanvasDetail('dashboard', 1, async () => ({ id: 1, name: 'fresh' }));
    controllerAfterHit.abort();
    expect(hit).toBe(saved);
    expect(readCachedCanvasDetail('dashboard', 1)).toEqual({ hit: true, detail: saved });
  });
});
