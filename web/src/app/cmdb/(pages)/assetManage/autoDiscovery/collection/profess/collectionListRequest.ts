import { createLatestRequestGuard } from '@/context/latestRequestGuard';

export const COLLECTION_LIST_POLL_INTERVAL_MS = 30 * 1000;

export interface CollectionListPayload<T> {
  items?: T[] | null;
  count?: number | null;
}

export interface CollectionListView<T> {
  items: T[];
  listCount: number;
  total: number;
}

export interface CollectionListTimerApi {
  setTimeoutFn: (callback: () => void, ms: number) => unknown;
  clearTimeoutFn: (id: unknown) => void;
}

export interface CollectionListRequest {
  begin: () => number;
  commitSuccess: <T>(
    requestId: number,
    payload: CollectionListPayload<T>,
    apply: (view: CollectionListView<T>) => void,
  ) => boolean;
  commitSettled: (requestId: number, settle: () => void) => boolean;
  resetTimer: (onTick: () => void) => void;
  unmount: () => void;
  clearTimer: () => void;
}

export function buildCollectionListView<T>(
  payload: CollectionListPayload<T>,
): CollectionListView<T> {
  const items = payload.items || [];
  return {
    items,
    listCount: items.length,
    total: payload.count || 0,
  };
}

export function createCollectionListRequest(
  timers?: Partial<CollectionListTimerApi>,
): CollectionListRequest {
  const guard = createLatestRequestGuard();
  const setTimeoutFn =
    timers?.setTimeoutFn ?? ((callback, ms) => setTimeout(callback, ms));
  const clearTimeoutFn =
    timers?.clearTimeoutFn ??
    ((id) => {
      if (id != null) {
        clearTimeout(id as ReturnType<typeof setTimeout>);
      }
    });
  let timerId: unknown = null;

  const clearTimer = () => {
    if (timerId != null) {
      clearTimeoutFn(timerId);
      timerId = null;
    }
  };

  return {
    begin: () => {
      clearTimer();
      return guard.begin();
    },
    commitSuccess: (requestId, payload, apply) =>
      guard.commitIfCurrent(requestId, () => {
        apply(buildCollectionListView(payload));
      }),
    commitSettled: (requestId, settle) => guard.commitIfCurrent(requestId, settle),
    resetTimer: (onTick) => {
      clearTimer();
      timerId = setTimeoutFn(() => {
        timerId = null;
        onTick();
      }, COLLECTION_LIST_POLL_INTERVAL_MS);
    },
    unmount: () => {
      guard.invalidate();
      clearTimer();
    },
    clearTimer,
  };
}
