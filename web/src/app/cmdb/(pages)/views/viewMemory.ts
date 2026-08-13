import type { ViewFocus, ViewRecentItem, ViewType } from './viewTypes';

const STORAGE_KEY_PREFIX = 'bk-lite:cmdb:views:v1:';
const MAX_RECENT_ITEMS = 10;

interface StorageLike {
  getItem: (key: string) => string | null;
  setItem: (key: string, value: string) => void;
}

interface StoredViewMemory {
  focus?: ViewFocus;
  recent?: ViewRecentItem[];
}

export const getViewMemoryStorageKey = (
  userId: string | number,
  viewType: ViewType
): string => `${STORAGE_KEY_PREFIX}${String(userId)}:${viewType}`;

const readStoredMemory = (
  storage: Pick<StorageLike, 'getItem'> | null,
  userId: string | number,
  viewType: ViewType
): StoredViewMemory => {
  try {
    if (!storage) return {};
    const rawValue = storage.getItem(getViewMemoryStorageKey(userId, viewType));
    if (!rawValue) return {};
    const parsed = JSON.parse(rawValue) as StoredViewMemory;
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
};

const writeStoredMemory = (
  storage: Pick<StorageLike, 'setItem'> | null,
  userId: string | number,
  viewType: ViewType,
  memory: StoredViewMemory
): boolean => {
  try {
    if (!storage) return false;
    storage.setItem(getViewMemoryStorageKey(userId, viewType), JSON.stringify(memory));
    return true;
  } catch {
    return false;
  }
};

const isValidFocus = (value: unknown): value is ViewFocus => {
  if (!value || typeof value !== 'object') return false;
  const focus = value as ViewFocus;
  return typeof focus.model_id === 'string'
    && typeof focus.inst_id === 'string';
};

const normalizeRecent = (value: unknown): ViewRecentItem[] => {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is ViewRecentItem => {
    if (!item || typeof item !== 'object') return false;
    const recent = item as ViewRecentItem;
    return isValidFocus(recent) && typeof recent.viewedAt === 'number';
  });
};

const recentItemKey = (item: ViewFocus): string =>
  `${item.model_id}:${item.inst_id}`;

export const readViewFocus = (
  storage: Pick<StorageLike, 'getItem'> | null,
  userId: string | number,
  viewType: ViewType
): ViewFocus | null => {
  const { focus } = readStoredMemory(storage, userId, viewType);
  return focus && isValidFocus(focus) ? focus : null;
};

export const writeViewFocus = (
  storage: Pick<StorageLike, 'setItem' | 'getItem'> | null,
  userId: string | number,
  viewType: ViewType,
  focus: ViewFocus
): boolean => {
  const memory = readStoredMemory(storage, userId, viewType);
  return writeStoredMemory(storage, userId, viewType, { ...memory, focus });
};

export const clearViewFocus = (
  storage: Pick<StorageLike, 'setItem' | 'getItem'> | null,
  userId: string | number,
  viewType: ViewType
): boolean => {
  const memory = readStoredMemory(storage, userId, viewType);
  return writeStoredMemory(storage, userId, viewType, {
    recent: memory.recent,
  });
};

export const readViewRecent = (
  storage: Pick<StorageLike, 'getItem'> | null,
  userId: string | number,
  viewType: ViewType
): ViewRecentItem[] => normalizeRecent(readStoredMemory(storage, userId, viewType).recent);

export const pushViewRecent = (
  storage: Pick<StorageLike, 'setItem' | 'getItem'> | null,
  userId: string | number,
  viewType: ViewType,
  focus: ViewFocus
): boolean => {
  const memory = readStoredMemory(storage, userId, viewType);
  const existing = normalizeRecent(memory.recent);
  const key = recentItemKey(focus);
  const filtered = existing.filter((item) => recentItemKey(item) !== key);
  const nextRecent: ViewRecentItem[] = [
    { ...focus, viewedAt: Date.now() },
    ...filtered,
  ].slice(0, MAX_RECENT_ITEMS);
  return writeStoredMemory(storage, userId, viewType, { ...memory, recent: nextRecent });
};
