/**
 * 本 Tab 内的监控查询槽位。
 * 弹窗 / 看板 / 列表合计最多 N 路（默认 8），避免一人叠请求打满 PG。
 */

export const SITE_METRIC_REQUEST_SLOT_LIMIT = readSlotLimit(
  process.env.NEXT_PUBLIC_MONITOR_METRIC_SLOT_LIMIT,
  8
);
export const SITE_METRIC_REQUEST_SLOT_HOLD_TIMEOUT_MS = 60_000;

type SlotRelease = () => void;

/** Axios GenericAbortSignal 与 DOM AbortSignal 的最小交集。 */
interface SlotAbortSignal {
  readonly aborted: boolean;
  addEventListener?: (type: 'abort', listener: () => void) => void;
  removeEventListener?: (type: 'abort', listener: () => void) => void;
}

interface LocalWaiter {
  resolve: (release: SlotRelease) => void;
  reject: (error: unknown) => void;
  signal?: SlotAbortSignal;
  onAbort?: () => void;
}

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
    /\/monitor\/api\/monitor_instance\/[^/]+\/(list|search|effective_plugins|display_metrics)\/?$/.test(
      path
    ) ||
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
      next.signal?.removeEventListener?.('abort', next.onAbort);
    }
    grantLocal(next);
  }
}

function acquireLocalSlot(signal?: SlotAbortSignal): Promise<SlotRelease> {
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
    signal?.addEventListener?.('abort', waiter.onAbort);
    if (localInFlight < SITE_METRIC_REQUEST_SLOT_LIMIT) {
      signal?.removeEventListener?.('abort', waiter.onAbort);
      grantLocal(waiter);
      return;
    }
    busyTotal += 1;
    localWaiters.push(waiter);
  });
}

export async function acquireMetricRequestSlot(options?: {
  signal?: SlotAbortSignal;
}): Promise<SlotRelease> {
  if (options?.signal?.aborted) {
    throw abortError();
  }
  return acquireLocalSlot(options?.signal);
}

export async function waitForSiteMetricSlot(
  isCurrentGeneration: () => boolean,
  options?: { intervalMs?: number; sleep?: (ms: number) => Promise<void>; signal?: SlotAbortSignal }
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
