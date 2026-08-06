export const TODO_PAGE_SIZE = 20;
export const ACTIVE_ALERT_STATUSES = ['unassigned', 'pending', 'processing'] as const;

export type TodoViewKey = 'mine' | 'open' | 'high';
export type AlertStatus = typeof ACTIVE_ALERT_STATUSES[number] | 'closed' | string;
export type AlertAction = 'assign' | 'acknowledge' | 'reassign' | 'close';
export type AlertSearchField = 'title' | 'content' | 'alert_id';

export interface AlertLevel {
  id: number;
  levelId: number;
  displayName: string;
  color: string;
  icon: string;
}

export interface TodoAlert {
  id: number;
  alertId: string;
  title: string;
  content: string;
  status: AlertStatus;
  levelId: string;
  duration: string;
  operators: string[];
  operatorDisplay: string;
  sourceName: string;
  resourceId: string;
  resourceName: string;
  resourceType: string;
  notifyStatus: string;
  createdAt: string;
  updatedAt: string;
  firstEventTime: string;
  lastEventTime: string;
  eventCount: number;
}

export interface AlertEvent {
  id: number;
  eventId: string;
  title: string;
  description: string;
  levelId: string;
  status: string;
  sourceName: string;
  resourceName: string;
  receivedAt: string;
  startTime: string;
  endTime: string;
}

export interface AlertChange {
  id: number;
  action: string;
  operator: string;
  operatorObject: string;
  overview: string;
  createdAt: string;
}

export interface AlertAssignee {
  id: string;
  username: string;
  displayName: string;
}

export interface PageResult<T> {
  count: number;
  items: T[];
}

export interface AlertListQuery {
  page: number;
  page_size: number;
  activate?: string;
  my_alert?: string;
  level?: string;
  title?: string;
  content?: string;
  alert_id?: string;
}

export function buildPresetQuery(
  view: TodoViewKey,
  page: number,
  highestLevelId?: number | null,
): AlertListQuery | null {
  const base: AlertListQuery = { page, page_size: TODO_PAGE_SIZE, activate: 'true' };
  if (view === 'mine') return { ...base, my_alert: 'true' };
  if (view === 'open') return base;
  if (highestLevelId === null || highestLevelId === undefined) return null;
  return { ...base, level: String(highestLevelId) };
}

export function buildSearchQuery(
  field: AlertSearchField,
  keyword: string,
  page: number,
): AlertListQuery | null {
  const value = keyword.trim();
  if (!value) return null;
  return {
    page,
    page_size: TODO_PAGE_SIZE,
    [field]: value,
  };
}

export function selectHighestLevel(levels: readonly AlertLevel[]): AlertLevel | null {
  return levels
    .filter((level) => Number.isFinite(level.levelId))
    .slice()
    .sort((left, right) => left.levelId - right.levelId)[0] ?? null;
}

export function mergePage<T>(current: readonly T[], next: readonly T[], keyOf: (item: T) => string | number) {
  const merged = new Map(current.map((item) => [keyOf(item), item]));
  for (const item of next) merged.set(keyOf(item), item);
  return Array.from(merged.values());
}

export function availableAlertActions(
  alert: Pick<TodoAlert, 'status' | 'operators'>,
  username: string,
  canEdit: boolean,
): AlertAction[] {
  if (!canEdit) return [];
  if (alert.status === 'unassigned') return ['assign'];
  const isOperator = alert.operators.includes(username);
  if (alert.status === 'pending' && isOperator) return ['acknowledge'];
  if (alert.status === 'processing' && isOperator) return ['reassign', 'close'];
  return [];
}

const PRIMARY_ACTION_ORDER: AlertAction[] = ['acknowledge', 'assign', 'close', 'reassign'];

/** 在可用动作中选出唯一主操作，其余作为次要操作展示。 */
export function primaryAlertAction(actions: readonly AlertAction[]): AlertAction | null {
  return PRIMARY_ACTION_ORDER.find((action) => actions.includes(action)) ?? null;
}

export function formatAlertCount(count: number): string {
  if (!Number.isFinite(count) || count <= 0) return '';
  return count > 99 ? '99+' : String(count);
}

export function alertRequestErrorKind(error: unknown): 'forbidden' | 'missing' | 'error' {
  if (!(error instanceof Error)) return 'error';
  if (/API Error:\s*403\b/.test(error.message)) return 'forbidden';
  if (/API Error:\s*404\b/.test(error.message)) return 'missing';
  return 'error';
}

export function isPermissionDenied(error: unknown) {
  return alertRequestErrorKind(error) === 'forbidden';
}
