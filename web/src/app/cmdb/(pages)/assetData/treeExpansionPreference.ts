const GROUP_KEY_PREFIX = 'group:';
const STORAGE_KEY_PREFIX = 'bk-lite:cmdb:asset-model-tree:v1:';

interface StorageLike {
  getItem: (key: string) => string | null;
  setItem: (key: string, value: string) => void;
}

interface StoredExpansionPreference {
  collapsedClassificationIds: string[];
}

export interface TreeExpansionPreferenceState {
  loadedUserId: string | null;
  collapsedClassificationIdsByUser: Record<string, string[]>;
  dirtyUserIds: string[];
  anonymousCollapsedClassificationIds: string[] | null;
  searchActive: boolean;
}

interface PreferenceWriteRequest {
  userId: string;
  collapsedClassificationIds: string[];
}

interface PreferenceTransition {
  state: TreeExpansionPreferenceState;
  collapsedClassificationIds: string[];
  expandedKeys: string[];
  writeRequest: PreferenceWriteRequest | null;
}

export const buildGroupKey = (classificationId: string): string =>
  `${GROUP_KEY_PREFIX}${classificationId}`;

export const getClassificationIdFromGroupKey = (key: string): string | null =>
  key.startsWith(GROUP_KEY_PREFIX) ? key.slice(GROUP_KEY_PREFIX.length) : null;

export const getAssetModelTreeStorageKey = (userId: string | number): string =>
  `${STORAGE_KEY_PREFIX}${String(userId)}`;

const normalizeCollapsedClassificationIds = (
  value: unknown,
  validClassificationIds: string[]
): string[] => {
  if (!value || typeof value !== 'object') return [];

  const collapsed = (value as { collapsedClassificationIds?: unknown })
    .collapsedClassificationIds;
  if (!Array.isArray(collapsed)) return [];

  const validIds = new Set(validClassificationIds);
  return Array.from(
    new Set(collapsed.filter((id): id is string => typeof id === 'string' && validIds.has(id)))
  );
};

export const readCollapsedClassificationIds = (
  storage: Pick<StorageLike, 'getItem'> | null,
  userId: string | number,
  validClassificationIds: string[]
): string[] => {
  try {
    if (!storage) return [];
    const rawValue = storage.getItem(getAssetModelTreeStorageKey(userId));
    return rawValue
      ? normalizeCollapsedClassificationIds(JSON.parse(rawValue), validClassificationIds)
      : [];
  } catch {
    return [];
  }
};

export const writeCollapsedClassificationIds = (
  storage: Pick<StorageLike, 'setItem'> | null,
  userId: string | number,
  collapsedClassificationIds: string[]
): boolean => {
  try {
    if (!storage) return false;
    const value: StoredExpansionPreference = { collapsedClassificationIds };
    storage.setItem(getAssetModelTreeStorageKey(userId), JSON.stringify(value));
    return true;
  } catch {
    // 浏览器禁用或限制 localStorage 时，只保留当前页面内存状态。
    return false;
  }
};

export const getExpandedGroupKeys = (
  validClassificationIds: string[],
  collapsedClassificationIds: string[]
): string[] => {
  const collapsedIds = new Set(collapsedClassificationIds);
  return validClassificationIds.filter((id) => !collapsedIds.has(id)).map(buildGroupKey);
};

export const updateCollapsedClassificationIds = (
  validClassificationIds: string[],
  collapsedClassificationIds: string[],
  classificationId: string,
  expanded: boolean
): string[] => {
  const validIds = new Set(validClassificationIds);
  const collapsedIds = new Set(collapsedClassificationIds.filter((id) => validIds.has(id)));
  if (!validIds.has(classificationId)) return Array.from(collapsedIds);

  if (expanded) collapsedIds.delete(classificationId);
  else collapsedIds.add(classificationId);
  return Array.from(collapsedIds);
};

const normalizeIds = (ids: string[], validClassificationIds: string[]): string[] => {
  const validIds = new Set(validClassificationIds);
  return Array.from(new Set(ids.filter((id) => validIds.has(id))));
};

const hasUserPreference = (
  state: TreeExpansionPreferenceState,
  userId: string
): boolean => Object.prototype.hasOwnProperty.call(
  state.collapsedClassificationIdsByUser,
  userId
);

export const selectCollapsedClassificationIds = (
  state: TreeExpansionPreferenceState,
  userId: string | null,
  validClassificationIds: string[]
): string[] => {
  if (userId && hasUserPreference(state, userId)) {
    return normalizeIds(
      state.collapsedClassificationIdsByUser[userId],
      validClassificationIds
    );
  }
  if (!userId && state.anonymousCollapsedClassificationIds !== null) {
    return normalizeIds(
      state.anonymousCollapsedClassificationIds,
      validClassificationIds
    );
  }
  if (state.loadedUserId && hasUserPreference(state, state.loadedUserId)) {
    return normalizeIds(
      state.collapsedClassificationIdsByUser[state.loadedUserId],
      validClassificationIds
    );
  }
  return [];
};

const buildTransition = (
  state: TreeExpansionPreferenceState,
  userId: string | null,
  validClassificationIds: string[],
  writeRequest: PreferenceWriteRequest | null = null
): PreferenceTransition => {
  const collapsedClassificationIds = selectCollapsedClassificationIds(
    state,
    userId,
    validClassificationIds
  );
  return {
    state,
    collapsedClassificationIds,
    expandedKeys: getExpandedGroupKeys(validClassificationIds, collapsedClassificationIds),
    writeRequest,
  };
};

export const createTreeExpansionPreferenceState = (): TreeExpansionPreferenceState => ({
  loadedUserId: null,
  collapsedClassificationIdsByUser: {},
  dirtyUserIds: [],
  anonymousCollapsedClassificationIds: null,
  searchActive: false,
});

export const reconcileTreeExpansionPreference = (
  state: TreeExpansionPreferenceState,
  userId: string | null,
  validClassificationIds: string[],
  storedCollapsedClassificationIds: string[]
): PreferenceTransition => {
  const collapsedClassificationIdsByUser = Object.fromEntries(
    Object.entries(state.collapsedClassificationIdsByUser).map(([storedUserId, ids]) => [
      storedUserId,
      normalizeIds(ids, validClassificationIds),
    ])
  );
  const normalizedState = { ...state, collapsedClassificationIdsByUser };

  if (!userId) {
    return buildTransition(normalizedState, null, validClassificationIds);
  }

  let collapsedClassificationIds: string[];
  let anonymousCollapsedClassificationIds = state.anonymousCollapsedClassificationIds;
  let dirtyUserIds = state.dirtyUserIds;

  if (anonymousCollapsedClassificationIds !== null) {
    collapsedClassificationIds = normalizeIds(
      anonymousCollapsedClassificationIds,
      validClassificationIds
    );
    anonymousCollapsedClassificationIds = null;
    dirtyUserIds = Array.from(new Set([...dirtyUserIds, userId]));
  } else if (hasUserPreference(normalizedState, userId)) {
    collapsedClassificationIds = collapsedClassificationIdsByUser[userId];
  } else {
    collapsedClassificationIds = normalizeIds(
      storedCollapsedClassificationIds,
      validClassificationIds
    );
  }

  const nextState = {
    ...normalizedState,
    loadedUserId: userId,
    anonymousCollapsedClassificationIds,
    dirtyUserIds,
    collapsedClassificationIdsByUser: {
      ...collapsedClassificationIdsByUser,
      [userId]: collapsedClassificationIds,
    },
  };
  const writeRequest = dirtyUserIds.includes(userId)
    ? { userId, collapsedClassificationIds }
    : null;
  return buildTransition(nextState, userId, validClassificationIds, writeRequest);
};

export const applyTreeExpansionPreferenceOperation = (
  state: TreeExpansionPreferenceState,
  userId: string | null,
  validClassificationIds: string[],
  collapsedClassificationIds: string[]
): PreferenceTransition => {
  const normalizedIds = normalizeIds(
    collapsedClassificationIds,
    validClassificationIds
  );
  const preferenceUserId = userId || state.loadedUserId;
  if (!preferenceUserId) {
    const nextState = {
      ...state,
      anonymousCollapsedClassificationIds: normalizedIds,
    };
    return buildTransition(nextState, null, validClassificationIds);
  }

  const nextState = {
    ...state,
    loadedUserId: preferenceUserId,
    dirtyUserIds: Array.from(new Set([...state.dirtyUserIds, preferenceUserId])),
    collapsedClassificationIdsByUser: {
      ...state.collapsedClassificationIdsByUser,
      [preferenceUserId]: normalizedIds,
    },
  };
  const writeRequest = userId
    ? { userId: preferenceUserId, collapsedClassificationIds: normalizedIds }
    : null;
  return buildTransition(
    nextState,
    preferenceUserId,
    validClassificationIds,
    writeRequest
  );
};

export const recordTreeExpansionPreferenceWrite = (
  state: TreeExpansionPreferenceState,
  userId: string,
  succeeded: boolean
): TreeExpansionPreferenceState => succeeded
  ? {
    ...state,
    dirtyUserIds: state.dirtyUserIds.filter((dirtyUserId) => dirtyUserId !== userId),
  }
  : state;

export const transitionTreeExpansionSearch = (
  state: TreeExpansionPreferenceState,
  userId: string | null,
  validClassificationIds: string[],
  searchExpandedKeys: string[] | null
): PreferenceTransition => {
  const nextState = { ...state, searchActive: searchExpandedKeys !== null };
  const transition = buildTransition(nextState, userId, validClassificationIds);
  return searchExpandedKeys === null
    ? transition
    : { ...transition, expandedKeys: searchExpandedKeys };
};
