import {
  MAX_SEARCH_LENGTH,
  buildAttrSearchCondition,
  type AttrSearchClause,
} from './attrSearchCondition';

const STORAGE_KEY_PREFIX = 'bk-lite:cmdb:tag-view-search:v1:';

interface StorageLike {
  getItem: (key: string) => string | null;
  setItem: (key: string, value: string) => void;
  removeItem?: (key: string) => void;
}

export interface ModelSearchPreference {
  field: string;
  value?: unknown;
  exact?: boolean;
  clause?: AttrSearchClause | null;
}

export const getTagViewSearchStorageKey = (viewId: number | string): string =>
  `${STORAGE_KEY_PREFIX}${viewId}`;

export const normalizeKeyword = (value: unknown): string => {
  if (typeof value !== 'string') return '';
  return value.trim().slice(0, MAX_SEARCH_LENGTH);
};

const fromLegacyKeyword = (keyword: string): ModelSearchPreference | null => {
  const value = normalizeKeyword(keyword);
  if (!value) return null;
  return {
    field: 'inst_name',
    value,
    exact: false,
    clause: { field: 'inst_name', type: 'str*', value },
  };
};

export const parseModelSearchPreference = (
  raw: unknown
): ModelSearchPreference | null => {
  if (typeof raw === 'string') return fromLegacyKeyword(raw);
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null;
  const item = raw as Record<string, unknown>;
  const field = typeof item.field === 'string' ? item.field.trim() : '';
  if (!field) return null;
  const exact = item.exact === true;
  const value = 'value' in item ? item.value : undefined;
  const storedClause =
    item.clause && typeof item.clause === 'object' && !Array.isArray(item.clause)
      ? (item.clause as AttrSearchClause)
      : null;
  const clause =
    storedClause && storedClause.field && storedClause.type
      ? storedClause
      : buildAttrSearchCondition(
        {
          attr_id: field,
          attr_name: field,
          attr_type: 'str',
          is_required: false,
          editable: false,
          option: [],
        },
        value,
        exact
      );
  return { field, value, exact, clause };
};

export const parseModelSearches = (
  raw: unknown
): Record<string, ModelSearchPreference> => {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return {};
  const next: Record<string, ModelSearchPreference> = {};
  for (const [modelId, spec] of Object.entries(raw as Record<string, unknown>)) {
    const key = String(modelId || '').trim();
    if (!key) continue;
    const preference = parseModelSearchPreference(spec);
    if (!preference) continue;
    next[key] = preference;
  }
  return next;
};

export const toSearchPayload = (
  searches: Record<string, ModelSearchPreference>
): Record<string, AttrSearchClause> => {
  const next: Record<string, AttrSearchClause> = {};
  for (const [modelId, preference] of Object.entries(searches)) {
    if (preference.clause) next[modelId] = preference.clause;
  }
  return next;
};

export const browserStorage = (): StorageLike | null => {
  try {
    if (typeof window === 'undefined') return null;
    return window.localStorage;
  } catch {
    return null;
  }
};

export const readModelSearches = (
  storage: Pick<StorageLike, 'getItem'> | null,
  viewId: number | string
): Record<string, ModelSearchPreference> => {
  try {
    if (!storage) return {};
    const rawValue = storage.getItem(getTagViewSearchStorageKey(viewId));
    return rawValue ? parseModelSearches(JSON.parse(rawValue)) : {};
  } catch {
    return {};
  }
};

const persistModelSearches = (
  storage: StorageLike | null,
  viewId: number | string,
  searches: Record<string, ModelSearchPreference>
): void => {
  try {
    if (!storage) return;
    const storageKey = getTagViewSearchStorageKey(viewId);
    if (Object.keys(searches).length === 0) {
      storage.removeItem?.(storageKey);
      return;
    }
    storage.setItem(storageKey, JSON.stringify(searches));
  } catch {
    // private mode / quota
  }
};

export const writeModelSearch = (
  storage: StorageLike | null,
  viewId: number | string,
  modelId: string,
  preference: ModelSearchPreference | null
): Record<string, ModelSearchPreference> => {
  const key = String(modelId || '').trim();
  const next = { ...readModelSearches(storage, viewId) };
  if (!key) return next;
  if (!preference?.field) delete next[key];
  else next[key] = preference;
  persistModelSearches(storage, viewId, next);
  return next;
};
