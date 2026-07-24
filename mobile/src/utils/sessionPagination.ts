import type { SessionItem } from '@/types/conversation';

export const MOBILE_SESSION_PAGE_SIZE = 20;

export function mergeSessionItems(current: SessionItem[], incoming: SessionItem[]): SessionItem[] {
  const seen = new Set(current.map((item) => item.session_id));
  return [
    ...current,
    ...incoming.filter((item) => {
      if (seen.has(item.session_id)) return false;
      seen.add(item.session_id);
      return true;
    }),
  ];
}

export function hasMoreSessions(items: SessionItem[], count: number): boolean {
  return items.length < count;
}

export function shouldShowSessionPagination(
  count: number | null,
  loadedCount: number,
  pageSize = MOBILE_SESSION_PAGE_SIZE,
): boolean {
  return count === null ? loadedCount >= pageSize : count > pageSize;
}
