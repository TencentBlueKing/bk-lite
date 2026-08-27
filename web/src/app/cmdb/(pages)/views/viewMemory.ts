import type { RackRoomMode, ViewFocus, ViewRecentItem, ViewType } from './viewTypes';

const STORAGE_KEY_PREFIX = 'bk-lite:cmdb:views:v1:';
const MAX_RECENT_ITEMS = 10;

interface StorageLike {
  getItem: (key: string) => string | null;
  setItem: (key: string, value: string) => void;
}

interface StoredViewMemory {
  focus?: ViewFocus;
  focuses?: ViewFocus[];
  /** rack-room: last instance(s) per mode (independent of current Segmented tab). */
  focusByMode?: Partial<Record<RackRoomMode, ViewFocus | ViewFocus[]>>;
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

const asFocusList = (value: unknown): ViewFocus[] => {
  if (Array.isArray(value)) return value.filter(isValidFocus);
  return isValidFocus(value) ? [value] : [];
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
): ViewFocus | null => readViewFocuses(storage, userId, viewType)[0] ?? null;

export const readViewFocuses = (
  storage: Pick<StorageLike, 'getItem'> | null,
  userId: string | number,
  viewType: ViewType
): ViewFocus[] => {
  const memory = readStoredMemory(storage, userId, viewType);
  const fromList = asFocusList(memory.focuses);
  if (fromList.length) return fromList;
  return asFocusList(memory.focus);
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
): ViewFocus | null => readViewFocusesForMode(storage, userId, viewType, mode)[0] ?? null;

/**
 * Read remembered instance list for a rack-room mode.
 * Accepts legacy single-object slots.
 */
export const readViewFocusesForMode = (
  storage: Pick<StorageLike, 'getItem'> | null,
  userId: string | number,
  viewType: ViewType,
  mode: RackRoomMode
): ViewFocus[] => {
  if (viewType !== 'rack-room') {
    return readViewFocuses(storage, userId, viewType);
  }
  const memory = readStoredMemory(storage, userId, viewType);
  const byMode = asFocusList(memory.focusByMode?.[mode]).map((item) =>
    normalizeModeFocus(item, mode)
  );
  if (byMode.length) return byMode;
  const top = asFocusList(memory.focuses?.length ? memory.focuses : memory.focus)
    .filter((item) => item.mode === mode)
    .map((item) => normalizeModeFocus(item, mode));
  return top;
};

export const writeViewFocus = (
  storage: Pick<StorageLike, 'setItem' | 'getItem'> | null,
  userId: string | number,
  viewType: ViewType,
  focus: ViewFocus
): boolean => writeViewFocuses(storage, userId, viewType, [focus]);

export const writeViewFocuses = (
  storage: Pick<StorageLike, 'setItem' | 'getItem'> | null,
  userId: string | number,
  viewType: ViewType,
  focuses: ViewFocus[]
): boolean => {
  const memory = readStoredMemory(storage, userId, viewType);
  const valid = asFocusList(focuses);
  if (!valid.length) {
    return writeStoredMemory(storage, userId, viewType, {
      recent: memory.recent,
      focusByMode: memory.focusByMode,
    });
  }
  const primary = valid[0];
  const next: StoredViewMemory = {
    ...memory,
    focus: primary,
    focuses: valid,
  };
  if (viewType === 'rack-room' && primary.mode) {
    next.focusByMode = {
      ...memory.focusByMode,
      [primary.mode]: valid.map((item) => normalizeModeFocus(item, primary.mode!)),
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
  const keptFocus = topMatchesMode || !memory.focus ? undefined : memory.focus;
  const keptFocuses = asFocusList(memory.focuses).filter((item) => item.mode !== mode);
  return writeStoredMemory(storage, userId, viewType, {
    recent: memory.recent,
    focusByMode,
    ...(keptFocus ? { focus: keptFocus } : {}),
    ...(keptFocuses.length ? { focuses: keptFocuses } : {}),
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
