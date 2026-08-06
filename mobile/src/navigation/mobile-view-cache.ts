interface StoredMobileViewSnapshot<T> {
  data: T;
  scrollTop: number;
  savedAt: number;
}

export interface MobileViewSnapshot<T> {
  data: T;
  scrollTop: number;
}

const MAX_ENTRIES = 24;
const MAX_AGE_MS = 5 * 60 * 1000;
const snapshots = new Map<string, StoredMobileViewSnapshot<unknown>>();
const staleKeys = new Set<string>();

function entryKey(scope: string, view: string) {
  return `${scope}::${view}`;
}

function prune(now: number) {
  for (const [key, snapshot] of snapshots) {
    if (now - snapshot.savedAt > MAX_AGE_MS) snapshots.delete(key);
  }
  while (snapshots.size > MAX_ENTRIES) {
    const oldestKey = snapshots.keys().next().value as string | undefined;
    if (!oldestKey) break;
    snapshots.delete(oldestKey);
  }
}

export function readMobileViewSnapshot<T>(scope: string, view: string): MobileViewSnapshot<T> | null {
  const now = Date.now();
  prune(now);
  const key = entryKey(scope, view);
  const snapshot = snapshots.get(key) as StoredMobileViewSnapshot<T> | undefined;
  if (!snapshot) return null;
  snapshots.delete(key);
  snapshots.set(key, snapshot);
  return { data: snapshot.data, scrollTop: snapshot.scrollTop };
}

export function writeMobileViewSnapshot<T>(scope: string, view: string, data: T, scrollTop = 0) {
  const key = entryKey(scope, view);
  snapshots.delete(key);
  snapshots.set(key, { data, scrollTop, savedAt: Date.now() });
  prune(Date.now());
}

/** 标记视图缓存已脏；保留 snapshot 供先渲染，列表页再静默刷新。 */
export function invalidateMobileViewSnapshot(scope: string, view: string) {
  staleKeys.add(entryKey(scope, view));
}

export function invalidateMobileViewSnapshots(scope: string, views: readonly string[]) {
  for (const view of views) invalidateMobileViewSnapshot(scope, view);
}

export function isMobileViewStale(scope: string, view: string) {
  return staleKeys.has(entryKey(scope, view));
}

export function clearMobileViewStale(scope: string, view: string) {
  staleKeys.delete(entryKey(scope, view));
}

export function restoreMobileViewScroll(element: HTMLElement | null, scrollTop = 0) {
  if (!element || scrollTop <= 0) return;
  window.requestAnimationFrame(() => {
    window.requestAnimationFrame(() => element.scrollTo({ top: scrollTop, behavior: 'auto' }));
  });
}

export function clearMobileViewCache() {
  snapshots.clear();
  staleKeys.clear();
}
