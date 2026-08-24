export const TODO_PAGE_SIZE = 20;
export const ACTIVE_ALERT_STATUSES = ['unassigned', 'pending', 'processing'] as const;

/** 与 Web `useNotifiedStateMap` 对齐：空值视为未通知 */
export function alertNotifyStatusKey(status: string | null | undefined): 'not_notified' | 'success' | 'failed' | 'partial_success' | string {
  const normalized = (status || '').trim();
  if (!normalized) return 'not_notified';
  return normalized;
}

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

/** Server 告警等级 ID：0 是合法最高等级，空值不得被 Number() 误转为 0。 */
export function parseAlertLevelId(value: unknown): number | null {
  if (typeof value !== 'number' && typeof value !== 'string') return null;
  if (typeof value === 'string' && !value.trim()) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
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

export type AlertEventPaginationStatus = 'idle' | 'loading' | 'ready' | 'error';

export interface AlertEventPaginationState {
  items: AlertEvent[];
  count: number;
  page: number;
  generation: number;
  status: AlertEventPaginationStatus;
  loadingMore: boolean;
  failedPage: number | null;
}

export type AlertEventPaginationAction =
  | { type: 'reset'; generation: number }
  | { type: 'load-started'; generation: number; page: number; append: boolean }
  | { type: 'load-succeeded'; generation: number; page: number; append: boolean; result: PageResult<AlertEvent> }
  | { type: 'load-failed'; generation: number; page: number; append: boolean };

export const INITIAL_ALERT_EVENT_PAGINATION_STATE: AlertEventPaginationState = {
  items: [],
  count: 0,
  page: 0,
  generation: 0,
  status: 'idle',
  loadingMore: false,
  failedPage: null,
};

/** 事件列表首屏失败可整区重试；追加失败必须保留已加载页和失败页码。 */
export function reduceAlertEventPagination(
  state: AlertEventPaginationState,
  action: AlertEventPaginationAction,
): AlertEventPaginationState {
  if (action.type === 'reset') {
    return { ...INITIAL_ALERT_EVENT_PAGINATION_STATE, items: [], generation: action.generation };
  }
  if (action.generation !== state.generation) return state;
  if (action.type === 'load-started') {
    return action.append
      ? { ...state, loadingMore: true }
      : { ...state, status: 'loading', loadingMore: false, failedPage: null };
  }
  if (action.type === 'load-succeeded') {
    return {
      items: action.append
        ? mergePage(state.items, action.result.items, (item) => item.id)
        : action.result.items,
      count: action.result.count,
      page: action.page,
      generation: state.generation,
      status: 'ready',
      loadingMore: false,
      failedPage: null,
    };
  }
  return action.append
    ? { ...state, status: 'ready', loadingMore: false, failedPage: action.page }
    : { ...state, status: 'error', loadingMore: false, failedPage: action.page };
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
