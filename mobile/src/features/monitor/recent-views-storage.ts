import { MAX_RECENT_VIEWS, normalizeRecentViews, type MonitorRecentViewsConfig } from '@/features/monitor/model';

const STORAGE_PREFIX = 'bk_lite_mobile_monitor_recent_views';

function storageKey(userId: number | string, teamId: string) {
  return `${STORAGE_PREFIX}:${userId}:${teamId}`;
}

export function readRecentViews(userId: number | string, teamId: string): MonitorRecentViewsConfig {
  if (typeof window === 'undefined') return { items: [] };
  try {
    const raw = window.localStorage.getItem(storageKey(userId, teamId));
    if (!raw) return { items: [] };
    return normalizeRecentViews(JSON.parse(raw));
  } catch {
    return { items: [] };
  }
}

export function recordRecentView(
  userId: number | string,
  teamId: string,
  objectId: number,
  instanceId: string,
) {
  if (typeof window === 'undefined') return;
  const trimmedId = instanceId.trim();
  if (!Number.isFinite(objectId) || objectId <= 0 || !trimmedId) return;

  const config = readRecentViews(userId, teamId);
  const viewedAt = new Date().toISOString();
  const items = [
    { objectId, instanceId: trimmedId, viewedAt },
    ...config.items.filter((item) => !(item.objectId === objectId && item.instanceId === trimmedId)),
  ].slice(0, MAX_RECENT_VIEWS);

  try {
    window.localStorage.setItem(storageKey(userId, teamId), JSON.stringify({ items }));
  } catch {
    // Quota or privacy mode — ignore silently.
  }
}
