import type { RackRoomMode, ViewFocus, ViewRecentItem, ViewType } from './viewTypes';

const STORAGE_KEY_PREFIX = 'bk-lite:cmdb:views:v1:';
const MAX_RECENT_ITEMS = 10;

interface StorageLike {
  getItem: (key: string) => string | null;
  setItem: (key: string, value: string) => void;
}

interface StoredViewMemory {
  focus?: ViewFocus;
  /** rack-room: last instance per mode (independent of current Segmented tab). */
  focusByMode?: Partial<Record<RackRoomMode, ViewFocus>>;
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
    && typeof focus.inst_uuid === 'string';
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
  `${item.model_id}:${item.inst_uuid}`;

const normalizeModeFocus = (
  focus: ViewFocus,
  mode: RackRoomMode
): ViewFocus => ({ ...focus, mode });

export const readViewFocus = (
  storage: Pick<StorageLike, 'getItem'> | null,
  userId: string | number,
  viewType: ViewType
): ViewFocus | null => {
  const { focus } = readStoredMemory(storage, userId, viewType);
  return focus && isValidFocus(focus) ? focus : null;
};

/**
 * Read the last remembered focus for a rack-room mode.
 * Falls back to top-level `focus` when it matches the requested mode.
 */
export const readViewFocusForMode = (
  storage: Pick<StorageLike, 'getItem'> | null,
  userId: string | number,
  viewType: ViewType,
  mode: RackRoomMode
): ViewFocus | null => {
  if (viewType !== 'rack-room') {
    return readViewFocus(storage, userId, viewType);
  }
  const memory = readStoredMemory(storage, userId, viewType);
  const byMode = memory.focusByMode?.[mode];
  if (byMode && isValidFocus(byMode)) {
    return normalizeModeFocus(byMode, mode);
  }
  if (memory.focus && isValidFocus(memory.focus) && memory.focus.mode === mode) {
    return normalizeModeFocus(memory.focus, mode);
  }
  return null;
};

export const writeViewFocus = (
  storage: Pick<StorageLike, 'setItem' | 'getItem'> | null,
  userId: string | number,
  viewType: ViewType,
  focus: ViewFocus
): boolean => {
  const memory = readStoredMemory(storage, userId, viewType);
  const next: StoredViewMemory = { ...memory, focus };
  if (viewType === 'rack-room' && focus.mode) {
    next.focusByMode = {
      ...memory.focusByMode,
      [focus.mode]: normalizeModeFocus(focus, focus.mode),
    };
  }
  return writeStoredMemory(storage, userId, viewType, next);
};

/**
 * Clear the active focus. For rack-room:
 * - with `mode`: clear only that mode's slot (keep the other mode)
 * - without `mode`: clear top-level focus only, keep per-mode slots
 */
export const clearViewFocus = (
  storage: Pick<StorageLike, 'setItem' | 'getItem'> | null,
  userId: string | number,
  viewType: ViewType,
  mode?: RackRoomMode
): boolean => {
  const memory = readStoredMemory(storage, userId, viewType);
  if (viewType !== 'rack-room') {
    return writeStoredMemory(storage, userId, viewType, {
      recent: memory.recent,
    });
  }

  if (!mode) {
    return writeStoredMemory(storage, userId, viewType, {
      recent: memory.recent,
      focusByMode: memory.focusByMode,
    });
  }

  const focusByMode = { ...memory.focusByMode };
  delete focusByMode[mode];
  const topMatchesMode = memory.focus?.mode === mode;
  return writeStoredMemory(storage, userId, viewType, {
    recent: memory.recent,
    focusByMode,
    ...(topMatchesMode || !memory.focus ? {} : { focus: memory.focus }),
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
