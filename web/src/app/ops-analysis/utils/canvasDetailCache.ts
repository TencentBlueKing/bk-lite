import type { CanvasType } from '@/app/ops-analysis/constants/canvasTypes';

/**
 * 成功的画布详情在内存里保留 45 秒（规格允许 30–60 秒）。
 * 预取、切入确认和播放态首屏读的是同一份 body；过期后下一次再请求。
 * 取消进行中的请求不会删掉已经写入的成功条目。
 */
export const CANVAS_DETAIL_CACHE_TTL_MS = 45_000;

interface CacheEntry {
  detail: unknown;
  expiresAt: number;
}

interface Flight {
  promise: Promise<unknown>;
  controller: AbortController;
  waiters: number;
}

const cache = new Map<string, CacheEntry>();
const flights = new Map<string, Flight>();

const cacheKey = (resourceType: CanvasType, canvasId: number): string => (
  `${resourceType}:${canvasId}`
);

const abortError = (): Error => {
  const error = new Error('The operation was aborted');
  error.name = 'AbortError';
  return error;
};

export const clearCanvasDetailCache = (): void => {
  cache.clear();
  for (const flight of flights.values()) {
    flight.controller.abort();
  }
  flights.clear();
};

export const readCachedCanvasDetail = (
  resourceType: CanvasType,
  canvasId: number,
  now = Date.now(),
): { hit: true; detail: unknown } | { hit: false } => {
  const key = cacheKey(resourceType, canvasId);
  const entry = cache.get(key);
  if (!entry || entry.expiresAt <= now) {
    if (entry) {
      cache.delete(key);
    }
    return { hit: false };
  }
  return { hit: true, detail: entry.detail };
};

const rememberCanvasDetail = (
  resourceType: CanvasType,
  canvasId: number,
  detail: unknown,
  now: number,
): void => {
  cache.set(cacheKey(resourceType, canvasId), {
    detail,
    expiresAt: now + CANVAS_DETAIL_CACHE_TTL_MS,
  });
};

/** 切入确认已经拿到的 body 补进缓存，不延长已有条目的 TTL。 */
export const rememberCanvasDetailIfAbsent = (
  resourceType: CanvasType,
  canvasId: number,
  detail: unknown,
  now = Date.now(),
): void => {
  if (readCachedCanvasDetail(resourceType, canvasId, now).hit) {
    return;
  }
  rememberCanvasDetail(resourceType, canvasId, detail, now);
};

export const fetchSharedCanvasDetail = async (
  resourceType: CanvasType,
  canvasId: number,
  fetcher: (signal: AbortSignal) => Promise<unknown>,
  callerSignal?: AbortSignal,
  now: () => number = Date.now,
): Promise<unknown> => {
  if (callerSignal?.aborted) {
    throw abortError();
  }
  const key = cacheKey(resourceType, canvasId);
  const cached = readCachedCanvasDetail(resourceType, canvasId, now());
  if (cached.hit) {
    return cached.detail;
  }

  let flight = flights.get(key);
  if (!flight) {
    const controller = new AbortController();
    const promise = Promise.resolve()
      .then(() => fetcher(controller.signal))
      .then((detail) => {
        rememberCanvasDetail(resourceType, canvasId, detail, now());
        return detail;
      })
      .finally(() => {
        const current = flights.get(key);
        if (current?.promise === promise) {
          flights.delete(key);
        }
      });
    flight = { promise, controller, waiters: 0 };
    flights.set(key, flight);
  }

  const active = flight;
  active.waiters += 1;
  let released = false;
  const release = (aborting: boolean) => {
    if (released) {
      return;
    }
    released = true;
    active.waiters -= 1;
    if (aborting && active.waiters <= 0) {
      active.controller.abort();
      if (flights.get(key)?.promise === active.promise) {
        flights.delete(key);
      }
    }
  };

  return new Promise((resolve, reject) => {
    const onAbort = () => {
      release(true);
      reject(abortError());
    };
    callerSignal?.addEventListener('abort', onAbort, { once: true });
    active.promise.then(
      (detail) => {
        callerSignal?.removeEventListener('abort', onAbort);
        if (callerSignal?.aborted) {
          return;
        }
        release(false);
        resolve(detail);
      },
      (error: unknown) => {
        callerSignal?.removeEventListener('abort', onAbort);
        if (callerSignal?.aborted) {
          return;
        }
        release(false);
        reject(error);
      },
    );
  });
};
