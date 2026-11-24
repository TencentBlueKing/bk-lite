import { setTimeout as wait } from 'node:timers/promises';
import { setFlagsFromString } from 'node:v8';
import { runInNewContext } from 'node:vm';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  CANVAS_DETAIL_CACHE_TTL_MS,
  clearCanvasDetailCache,
  fetchSharedCanvasDetail,
  readCachedCanvasDetail,
  rememberCanvasDetailIfAbsent,
} from '@/app/ops-analysis/utils/canvasDetailCache';

setFlagsFromString('--expose-gc');
const collectGarbage: () => void = runInNewContext('gc');

const remember = (id: number, now?: number) => {
  const detail = { payload: new Uint8Array(4096) };
  rememberCanvasDetailIfAbsent('dashboard', id, detail, now);
  return new WeakRef(detail);
};

const collect = async () => {
  for (let attempt = 0; attempt < 3; attempt += 1) {
    await wait(0);
    collectGarbage();
  }
  await wait(0);
};

describe('canvas detail resource lifetime', () => {
  beforeEach(() => {
    clearCanvasDetailCache();
    vi.useFakeTimers();
  });

  afterEach(() => {
    clearCanvasDetailCache();
    vi.useRealTimers();
  });

  it('releases expired bodies without another cache read', async () => {
    const reference = remember(1);
    await collect();
    expect(reference.deref()).toBeDefined();
    await vi.advanceTimersByTimeAsync(CANVAS_DETAIL_CACHE_TTL_MS);
    await collect();
    expect(reference.deref()).toBeUndefined();
    expect(vi.getTimerCount()).toBe(0);
  });

  it('clears bodies and their scheduled expiry on repeated clear', async () => {
    const references = [remember(1), remember(2)];
    clearCanvasDetailCache();
    clearCanvasDetailCache();
    await collect();
    expect(references.every((reference) => reference.deref() === undefined)).toBe(true);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('does not let the previous expiry remove a replacement', async () => {
    remember(1, 1000);
    await vi.advanceTimersByTimeAsync(1000);
    remember(1, 1000 + CANVAS_DETAIL_CACHE_TTL_MS);
    await vi.advanceTimersByTimeAsync(CANVAS_DETAIL_CACHE_TTL_MS - 1000);
    expect(readCachedCanvasDetail('dashboard', 1, 1000 + CANVAS_DETAIL_CACHE_TTL_MS).hit).toBe(true);
    await vi.advanceTimersByTimeAsync(1000);
    expect(readCachedCanvasDetail('dashboard', 1, 1000 + CANVAS_DETAIL_CACHE_TTL_MS).hit).toBe(false);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('does not extend a successful entry when remembering it again', async () => {
    const reference = remember(1);
    await vi.advanceTimersByTimeAsync(1000);
    remember(1);
    await vi.advanceTimersByTimeAsync(CANVAS_DETAIL_CACHE_TTL_MS - 1000);
    await collect();
    expect(reference.deref()).toBeUndefined();
    expect(vi.getTimerCount()).toBe(0);
  });

  it('gives a completed fetch its own expiry when it replaces an earlier remembered body', async () => {
    let finish: (body: unknown) => void = () => undefined;
    const pending = fetchSharedCanvasDetail('dashboard', 1, () => new Promise((resolve) => {
      finish = resolve;
    }));
    await Promise.resolve();
    remember(1);
    await vi.advanceTimersByTimeAsync(1000);
    const fetched = { source: 'fetch' };
    finish(fetched);
    await expect(pending).resolves.toBe(fetched);
    expect(vi.getTimerCount()).toBe(1);
    await vi.advanceTimersByTimeAsync(CANVAS_DETAIL_CACHE_TTL_MS - 1000);
    expect(readCachedCanvasDetail('dashboard', 1)).toEqual({ hit: true, detail: fetched });
    await vi.advanceTimersByTimeAsync(1000);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('does not retain a timed-out fetch and allows a later retry', async () => {
    const pending = fetchSharedCanvasDetail('dashboard', 1, () => new Promise((_resolve, reject) => {
      setTimeout(() => reject(Object.assign(new Error('timed out'), { name: 'TimeoutError' })), 1000);
    }));
    const rejected = expect(pending).rejects.toMatchObject({ name: 'TimeoutError' });
    await vi.advanceTimersByTimeAsync(1000);
    await rejected;
    expect(vi.getTimerCount()).toBe(0);
    const fetched = { source: 'retry' };
    await expect(fetchSharedCanvasDetail('dashboard', 1, async () => fetched)).resolves.toBe(fetched);
    expect(readCachedCanvasDetail('dashboard', 1)).toEqual({ hit: true, detail: fetched });
  });

});
