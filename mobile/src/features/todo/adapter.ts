import { apiGet, apiPost } from '@/api/request';
import type {
  AlertAction,
  AlertAssignee,
  AlertChange,
  AlertEvent,
  AlertLevel,
  AlertListQuery,
  PageResult,
  TodoAlert,
} from './model';

interface ApiEnvelope<T> {
  result: boolean;
  data: T;
  message?: string;
}

function record(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null ? value as Record<string, unknown> : {};
}

function text(value: unknown) {
  return value === null || value === undefined ? '' : String(value);
}

function number(value: unknown) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function stringList(value: unknown) {
  return Array.isArray(value) ? value.map(text).filter(Boolean) : [];
}

function unwrap<T>(value: unknown): T {
  const envelope = record(value);
  if (typeof envelope.result !== 'boolean') return value as T;
  if (!envelope.result) throw new Error(text(envelope.message) || 'Server returned an error');
  return envelope.data as T;
}

function pageItems(value: unknown) {
  const data = record(unwrap<unknown>(value));
  return {
    count: number(data.count),
    items: Array.isArray(data.items) ? data.items : [],
  };
}

function mapAlert(value: unknown): TodoAlert {
  const item = record(value);
  return {
    id: number(item.id),
    alertId: text(item.alert_id),
    title: text(item.title),
    content: text(item.content),
    status: text(item.status),
    levelId: text(item.level),
    duration: text(item.duration),
    operators: stringList(item.operator),
    operatorDisplay: text(item.operator_user),
    sourceName: text(item.source_name),
    resourceId: text(item.resource_id),
    resourceName: text(item.resource_name),
    resourceType: text(item.resource_type),
    notifyStatus: text(item.notify_status),
    createdAt: text(item.created_at),
    updatedAt: text(item.updated_at),
    firstEventTime: text(item.first_event_time),
    lastEventTime: text(item.last_event_time),
    eventCount: number(item.event_count),
  };
}

export async function listAlerts(query: AlertListQuery, signal?: AbortSignal): Promise<PageResult<TodoAlert>> {
  const page = pageItems(await apiGet<unknown>('/alerts/api/alerts/', query, { signal }));
  return { count: page.count, items: page.items.map(mapAlert) };
}

export async function getAlert(id: number, signal?: AbortSignal) {
  return mapAlert(unwrap<unknown>(await apiGet<unknown>(`/alerts/api/alerts/${id}/`, undefined, { signal })));
}

export async function listAlertLevels(signal?: AbortSignal): Promise<AlertLevel[]> {
  const raw = unwrap<unknown>(await apiGet<unknown>('/alerts/api/level/', { type: 'alert' }, { signal }));
  const items = Array.isArray(raw) ? raw : pageItems(raw).items;
  return items.map((value) => {
    const item = record(value);
    return {
      id: number(item.id),
      levelId: number(item.level_id),
      displayName: text(item.level_display_name || item.level_name),
      color: text(item.color),
      icon: text(item.icon),
    };
  });
}

export async function listAlertEvents(id: number, signal?: AbortSignal): Promise<PageResult<AlertEvent>> {
  const page = pageItems(await apiGet<unknown>(`/alerts/api/alerts/${id}/events/`, {
    page: 1,
    page_size: 100,
  }, { signal }));
  return {
    count: page.count,
    items: page.items.map((value) => {
      const item = record(value);
      return {
        id: number(item.id),
        eventId: text(item.event_id),
        title: text(item.title),
        description: text(item.description),
        levelId: text(item.level),
        status: text(item.status),
        sourceName: text(item.source_name),
        resourceName: text(item.resource_name),
        receivedAt: text(item.received_at),
        startTime: text(item.start_time),
        endTime: text(item.end_time),
      };
    }),
  };
}

export async function listAlertChanges(alertId: string, signal?: AbortSignal): Promise<PageResult<AlertChange>> {
  const page = pageItems(await apiGet<unknown>('/alerts/api/log/', {
    target_id: alertId,
    page: 1,
    page_size: 10000,
  }, { signal }));
  return {
    count: page.count,
    items: page.items.map((value) => {
      const item = record(value);
      return {
        id: number(item.id),
        action: text(item.action),
        operator: text(item.operator),
        operatorObject: text(item.operator_object),
        overview: text(item.overview),
        createdAt: text(item.created_at),
      };
    }),
  };
}

export async function listAssignees(search: string, signal?: AbortSignal): Promise<PageResult<AlertAssignee>> {
  const data = record(unwrap<unknown>(await apiGet<unknown>('/core/api/user_group/user_list/', {
    search,
    page: 1,
    page_size: 50,
  }, { signal })));
  const users = Array.isArray(data.users) ? data.users : [];
  return {
    count: number(data.count),
    items: users.map((value) => {
      const item = record(value);
      return {
        id: text(item.id || item.username),
        username: text(item.username),
        displayName: text(item.display_name || item.username),
      };
    }).filter((item) => item.username),
  };
}

export async function performAlertAction(
  action: AlertAction,
  alertId: string,
  assignees: string[] = [],
): Promise<string> {
  const raw = await apiPost<unknown>(`/alerts/api/alerts/operator/${action}/`, {
    alert_id: [alertId],
    ...(assignees.length ? { assignee: assignees } : {}),
  });
  const envelope = record(raw) as unknown as ApiEnvelope<unknown>;
  const resultMap = record(unwrap<unknown>(envelope));
  const result = record(resultMap[alertId]);
  if (result.result === false) throw new Error(text(result.message) || 'Operation failed');
  return text(result.message);
}
