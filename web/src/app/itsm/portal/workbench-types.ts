export type WidgetType = 'stats' | 'services' | 'todo' | 'tickets' | 'trend' | 'announcements' | 'quick' | 'recents' | 'favorites';
export interface PortalWidget { type: WidgetType; width: 6 | 12 }
export interface PortalLayout { title: string; subtitle: string; background: string; widgets: PortalWidget[] }
export interface PortalTicket { id: number; sn: string; title: string; status: string; created_at: string }
export interface PortalDashboard {
  stats: { total: number; todo: number; active: number; finished: number };
  tickets: PortalTicket[]; todo: PortalTicket[];
  trend: { date: string; created: number; finished: number }[];
  announcements: { id: number; title: string; content: string; created_at: string }[];
  can_view_tickets?: boolean;
}
export const widgetNames: Record<WidgetType, string> = {
  stats: '工单统计', services: '服务目录', todo: '我的待办', tickets: '工单列表', trend: '完成情况趋势',
  announcements: '公告', quick: '快速提单', recents: '最近使用', favorites: '我的收藏',
};
