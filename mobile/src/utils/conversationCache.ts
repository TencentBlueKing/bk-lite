const SESSIONS_CACHE_KEY = 'bk_lite_sessions_cache';
const SCROLL_POSITION_KEY = 'bk_lite_sidebar_scroll_position';
const HAS_FETCHED_KEY = 'bk_lite_sessions_has_fetched';
const NEED_REFRESH_KEY = 'bk_lite_sessions_need_refresh';

export const CONVERSATION_SESSION_CACHE_KEYS = {
  sessions: SESSIONS_CACHE_KEY,
  scrollPosition: SCROLL_POSITION_KEY,
  hasFetched: HAS_FETCHED_KEY,
  needRefresh: NEED_REFRESH_KEY,
} as const;

const CACHE_PREFIXES = Object.values(CONVERSATION_SESSION_CACHE_KEYS);

interface SessionsCacheScopeInput {
  botId?: string | number | null;
  nodeId?: string | null;
  accountId?: string | number | null;
  teamId?: string | number | null;
}

function encodeScopePart(value: string | number): string {
  return encodeURIComponent(String(value));
}

export function buildSessionsCacheScope({
  botId,
  nodeId,
  accountId,
  teamId,
}: SessionsCacheScopeInput): string {
  if (!botId || !nodeId || !accountId) {
    return 'unresolved';
  }

  return [
    `account=${encodeScopePart(accountId)}`,
    `team=${encodeScopePart(teamId || 'none')}`,
    `bot=${encodeScopePart(botId)}`,
    `node=${encodeScopePart(nodeId)}`,
  ].join('|');
}

export function scopedConversationCacheKey(baseKey: string, scope: string): string {
  return `${baseKey}:${scope}`;
}

export function clearConversationSessionCache(storage?: Storage): void {
  try {
    const targetStorage = storage
      ?? (typeof window !== 'undefined' ? window.sessionStorage : undefined);
    if (!targetStorage) return;

    const keysToRemove: string[] = [];
    for (let index = 0; index < targetStorage.length; index += 1) {
      const key = targetStorage.key(index);
      if (key && CACHE_PREFIXES.some((prefix) => key === prefix || key.startsWith(`${prefix}:`))) {
        keysToRemove.push(key);
      }
    }

    keysToRemove.forEach((key) => targetStorage.removeItem(key));
  } catch (error) {
    console.error('Failed to clear conversation session cache:', error);
  }
}
