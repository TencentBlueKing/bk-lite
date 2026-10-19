/**
 * 全浏览器共享的监控查询槽位。
 * 多 Tab / 弹窗 / 看板合计最多 N 路（默认 8），避免一人叠请求打满 PG。
 */

export const SITE_METRIC_REQUEST_SLOT_LIMIT = readSlotLimit(
  process.env.NEXT_PUBLIC_MONITOR_METRIC_SLOT_LIMIT,
  8
);
export const SITE_METRIC_REQUEST_SLOT_HOLD_TIMEOUT_MS = 60_000;
const SLOT_LOCK_PREFIX = 'bklite-monitor-metric-slot-';

type SlotRelease = () => void;

type LocalWaiter = {
  resolve: (release: SlotRelease) => void;
  reject: (error: unknown) => void;
  signal?: AbortSignal;
  onAbort?: () => void;
};

let localInFlight = 0;
const localWaiters: LocalWaiter[] = [];
let acquiredTotal = 0;
let recycledTotal = 0;
let busyTotal = 0;

function readSlotLimit(raw: string | undefined, fallback: number): number {
  const parsed = raw == null || raw === '' ? fallback : Number(raw);
  if (!Number.isFinite(parsed)) {
    return fallback;
  }
  return Math.min(16, Math.max(1, Math.floor(parsed)));
}

function abortError(): DOMException {
  return new DOMException('The operation was aborted.', 'AbortError');
}

export function getSiteMetricInFlightCount(): number {
  return localInFlight;
}

export function getSiteMetricRequestSlotStats() {
  return {
    limit: SITE_METRIC_REQUEST_SLOT_LIMIT,
    inFlight: localInFlight,
    queued: localWaiters.length,
    acquiredTotal,
    recycledTotal,
    busyTotal,
  };
}

export function shouldLimitMonitorQueryUrl(url?: string): boolean {
  if (!url) {
    return false;
  }
  const path = url.split('?')[0];
  return (
    /\/monitor\/api\/metrics_instance\/query_by_metric(_range)?\/?$/.test(path) ||
    /\/monitor\/api\/monitor_instance\/[^/]+\/(list|search|effective_plugins)\/?$/.test(path) ||
    /\/monitor\/api\/metrics\/[^/]+\/vm-fields\/?$/.test(path) ||
    /\/monitor\/api\/metrics\/?$/.test(path) ||
    /\/monitor\/api\/monitor_plugin\/?$/.test(path)
  );
}

export function shouldSkipPeriodicRefresh(inFlight: boolean): boolean {
  if (typeof document !== 'undefined' && document.hidden) {
    return true;
  }
  return inFlight;
}

function grantLocal(waiter?: LocalWaiter): SlotRelease {
  localInFlight += 1;
  acquiredTotal += 1;
  let released = false;
  const timer = setTimeout(() => {
    recycledTotal += 1;
    release();
  }, SITE_METRIC_REQUEST_SLOT_HOLD_TIMEOUT_MS);
  const release = () => {
    if (released) {
      return;
    }
    released = true;
    clearTimeout(timer);
    localInFlight = Math.max(0, localInFlight - 1);
    pumpLocal();
  };
  waiter?.resolve(release);
  return release;
}

function pumpLocal() {
  while (localInFlight < SITE_METRIC_REQUEST_SLOT_LIMIT && localWaiters.length) {
    const next = localWaiters.shift();
    if (!next) {
      break;
    }
    if (next.signal?.aborted) {
      next.reject(abortError());
      continue;
    }
    if (next.onAbort) {
      next.signal?.removeEventListener('abort', next.onAbort);
    }
    grantLocal(next);
  }
}

function acquireLocalSlot(signal?: AbortSignal): Promise<SlotRelease> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(abortError());
      return;
    }
    const waiter: LocalWaiter = { resolve, reject, signal };
    waiter.onAbort = () => {
      const index = localWaiters.indexOf(waiter);
      if (index >= 0) {
        localWaiters.splice(index, 1);
      }
      reject(abortError());
    };
    signal?.addEventListener('abort', waiter.onAbort);
    if (localInFlight < SITE_METRIC_REQUEST_SLOT_LIMIT) {
      signal?.removeEventListener('abort', waiter.onAbort);
      grantLocal(waiter);
      return;
    }
    busyTotal += 1;
    localWaiters.push(waiter);
  });
}

function acquireWebLockSlot(signal?: AbortSignal): Promise<SlotRelease> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(abortError());
      return;
    }
    const siblingAbort = new AbortController();
    const onUserAbort = () => siblingAbort.abort();
    signal?.addEventListener('abort', onUserAbort);

    let settled = false;
    const fail = (error: unknown) => {
      if (settled) {
        return;
      }
      settled = true;
      signal?.removeEventListener('abort', onUserAbort);
      reject(error);
    };
    const succeed = (release: SlotRelease) => {
      if (settled) {
        return;
      }
      settled = true;
      signal?.removeEventListener('abort', onUserAbort);
      resolve(release);
    };

    for (let index = 0; index < SITE_METRIC_REQUEST_SLOT_LIMIT; index += 1) {
      void navigator.locks
        .request(
          `${SLOT_LOCK_PREFIX}${index}`,
          { mode: 'exclusive', signal: siblingAbort.signal },
          () =>
            new Promise<void>((releaseLock) => {
              siblingAbort.abort();
              acquiredTotal += 1;
              localInFlight += 1;
              let released = false;
              const timer = window.setTimeout(() => {
                recycledTotal += 1;
                release();
              }, SITE_METRIC_REQUEST_SLOT_HOLD_TIMEOUT_MS);
              const release = () => {
                if (released) {
                  return;
                }
                released = true;
                window.clearTimeout(timer);
                localInFlight = Math.max(0, localInFlight - 1);
                releaseLock();
              };
              succeed(release);
            })
        )
        .catch(() => {
          if (signal?.aborted) {
            fail(abortError());
          }
        });
    }
  });
}

export async function acquireMetricRequestSlot(options?: {
  signal?: AbortSignal;
}): Promise<SlotRelease> {
  if (options?.signal?.aborted) {
    throw abortError();
  }
  if (typeof navigator !== 'undefined' && navigator.locks?.request) {
    try {
      return await acquireWebLockSlot(options?.signal);
    } catch (error) {
      if (options?.signal?.aborted) {
        throw error;
      }
      // locks 不可用或被中断时回退到页内队列，仍保证本页不超过 N。
    }
  }
  return acquireLocalSlot(options?.signal);
}

export async function waitForSiteMetricSlot(
  isCurrentGeneration: () => boolean,
  options?: { intervalMs?: number; sleep?: (ms: number) => Promise<void>; signal?: AbortSignal }
): Promise<boolean> {
  const intervalMs = options?.intervalMs ?? 30;
  const sleep =
    options?.sleep ??
    ((ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms)));
  while (getSiteMetricInFlightCount() >= SITE_METRIC_REQUEST_SLOT_LIMIT) {
    if (options?.signal?.aborted || !isCurrentGeneration()) {
      return false;
    }
    await sleep(intervalMs);
  }
  return isCurrentGeneration() && !options?.signal?.aborted;
}
