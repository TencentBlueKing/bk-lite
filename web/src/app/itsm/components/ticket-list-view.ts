import type { TicketCenterFilters } from '../types';

const VIEW_KEY = 'itsm.ticketListView';

export const TICKET_LIST_RETURN = '/itsm/tickets?restore=1';

export interface TicketListView {
  tab: string;
  query: TicketCenterFilters;
  draft: TicketCenterFilters;
  page: number;
  pageSize: number;
  scrollTop: number;
  scrollLeft: number;
}

export function rememberTicketListView(view: TicketListView) {
  window.history.replaceState({ ...window.history.state, [VIEW_KEY]: view }, '');
  try {
    window.sessionStorage.setItem(VIEW_KEY, JSON.stringify(view));
  } catch {
    // 浏览器禁用会话存储时，浏览器历史记录仍可恢复当前列表。
  }
}

export function readTicketListView(restore: boolean): TicketListView | undefined {
  const historyView = window.history.state?.[VIEW_KEY] as TicketListView | undefined;
  if (historyView) return historyView;
  if (!restore) return;
  try {
    const raw = window.sessionStorage.getItem(VIEW_KEY);
    return raw ? JSON.parse(raw) as TicketListView : undefined;
  } catch {
    return undefined;
  }
}
