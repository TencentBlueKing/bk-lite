import { findByMonitorId, toMonitorIdString } from '@/app/monitor/utils/monitorIds';

export const VIEW_OBJECT_QUERY_PARAM = 'object_id';
export const MODULE_OBJECT_QUERY_PARAM = 'objId';
export const LAST_MONITOR_OBJECT_STORAGE_KEY = 'bk-lite.monitor.lastObjectId';

type SearchParamsLike = Pick<URLSearchParams, 'get' | 'toString'>;

export interface MemoryStorageLike {
  getItem: (key: string) => string | null;
  setItem: (key: string, value: string) => void;
}

const OBJECT_PARAM_NAMES = [
  MODULE_OBJECT_QUERY_PARAM,
  VIEW_OBJECT_QUERY_PARAM
] as const;

export const isConcreteMonitorObjectId = (id: unknown): boolean => {
  const value = toMonitorIdString(id).trim();
  return /^\d+$/.test(value);
};

/**
 * 集成列表左侧树：一级分类 key 为 MonitorObjectType.id（非纯数字，
 * 如 "Network Device"），叶子为监控对象数字 id。
 * 判定不得依赖 objects 已加载，否则 URL 回退竞态会把分类 id 当成对象 id。
 */
export const isMonitorObjectTypeQueryKey = (id: unknown): boolean => {
  const value = toMonitorIdString(id).trim();
  if (!value || value === 'all') return false;
  return !isConcreteMonitorObjectId(value);
};

export const readMonitorObjectQueryId = (
  params: Pick<URLSearchParams, 'get'> | null | undefined,
  preferredParam?: string
): string => {
  if (!params) return '';
  const preferred = preferredParam
    ? String(params.get(preferredParam) || '').trim()
    : '';
  if (preferred) return preferred;
  return String(
    params.get(MODULE_OBJECT_QUERY_PARAM) ||
      params.get(VIEW_OBJECT_QUERY_PARAM) ||
      ''
  ).trim();
};

export const rememberMonitorObjectId = (
  objectId: unknown,
  storage?: MemoryStorageLike | null
) => {
  if (!isConcreteMonitorObjectId(objectId)) return;
  const target = storage ?? getSessionStorage();
  if (!target) return;
  try {
    target.setItem(LAST_MONITOR_OBJECT_STORAGE_KEY, toMonitorIdString(objectId));
  } catch {
    // sessionStorage 可能被禁用，忽略即可。
  }
};

export const recallMonitorObjectId = (
  storage?: MemoryStorageLike | null
): string => {
  const target = storage ?? getSessionStorage();
  if (!target) return '';
  try {
    return String(target.getItem(LAST_MONITOR_OBJECT_STORAGE_KEY) || '').trim();
  } catch {
    return '';
  }
};

const acceptMonitorObjectQueryId = (
  objectId: string,
  options: {
    objects?: Array<{ id?: unknown; type?: unknown }> | null;
    allowAll?: boolean;
    allowTypeKeys?: boolean;
  }
): string => {
  const value = toMonitorIdString(objectId).trim();
  if (!value) return '';
  if (options.allowAll && value === 'all') return 'all';
  const objects = options.objects || [];
  if (!objects.length) {
    if (value === 'all') return options.allowAll ? 'all' : '';
    return value;
  }
  if (
    options.allowTypeKeys &&
    objects.some((item) => String(item.type || '') === value)
  ) {
    return value;
  }
  return findByMonitorId(objects, value) ? toMonitorIdString(value) : '';
};

export const resolveMonitorObjectQueryId = (options: {
  searchParams?: Pick<URLSearchParams, 'get'> | null;
  objects?: Array<{ id?: unknown; type?: unknown }> | null;
  allowAll?: boolean;
  allowTypeKeys?: boolean;
  fallback?: unknown;
  recalledId?: string;
  storage?: MemoryStorageLike | null;
}): string => {
  const fromUrl = acceptMonitorObjectQueryId(
    readMonitorObjectQueryId(options.searchParams),
    options
  );
  if (fromUrl) return fromUrl;
  const recalled = acceptMonitorObjectQueryId(
    options.recalledId ?? recallMonitorObjectId(options.storage),
    {
      ...options,
      allowAll: false,
      allowTypeKeys: false
    }
  );
  if (recalled) return recalled;
  if (options.fallback != null && options.fallback !== '') {
    return toMonitorIdString(options.fallback);
  }
  if (options.allowAll) return 'all';
  return toMonitorIdString(options.objects?.[0]?.id);
};

export const resolveMonitorObjectTreeKey = (
  objects: Array<{ id?: unknown }> | null | undefined,
  resolvedId: string,
  fallback?: unknown
): string | number => {
  const matched = findByMonitorId(objects, resolvedId);
  if (matched?.id != null && matched.id !== '') {
    return matched.id as string | number;
  }
  if (resolvedId === 'all') return 'all';
  if (fallback != null && fallback !== '') {
    return fallback as string | number;
  }
  return resolvedId;
};

export const buildMonitorObjectSearch = (
  current: URLSearchParams | SearchParamsLike | string,
  objectId: unknown,
  paramName:
    | typeof VIEW_OBJECT_QUERY_PARAM
    | typeof MODULE_OBJECT_QUERY_PARAM = MODULE_OBJECT_QUERY_PARAM
): string => {
  const next = new URLSearchParams(
    typeof current === 'string' ? current : current.toString()
  );
  for (const name of OBJECT_PARAM_NAMES) {
    next.delete(name);
  }
  const normalized = toMonitorIdString(objectId).trim();
  if (normalized) {
    next.set(paramName, normalized);
  }
  const query = next.toString();
  return query ? `?${query}` : '';
};

export const buildMonitorObjectUrl = (
  pathname: string,
  current: URLSearchParams | SearchParamsLike | string,
  objectId: unknown,
  paramName:
    | typeof VIEW_OBJECT_QUERY_PARAM
    | typeof MODULE_OBJECT_QUERY_PARAM = MODULE_OBJECT_QUERY_PARAM
): string => `${pathname || ''}${buildMonitorObjectSearch(current, objectId, paramName)}`;

export const shouldSyncMonitorObjectUrl = (
  params: Pick<URLSearchParams, 'get'> | null | undefined,
  objectId: unknown,
  paramName:
    | typeof VIEW_OBJECT_QUERY_PARAM
    | typeof MODULE_OBJECT_QUERY_PARAM
): boolean => {
  const normalized = toMonitorIdString(objectId).trim();
  const currentNative = String(params?.get(paramName) || '').trim();
  const otherName =
    paramName === VIEW_OBJECT_QUERY_PARAM
      ? MODULE_OBJECT_QUERY_PARAM
      : VIEW_OBJECT_QUERY_PARAM;
  const currentOther = String(params?.get(otherName) || '').trim();
  return currentNative !== normalized || !!currentOther;
};

const getSessionStorage = (): MemoryStorageLike | null => {
  try {
    if (typeof sessionStorage === 'undefined') return null;
    return sessionStorage;
  } catch {
    return null;
  }
};
