export const APP_TOPO_EXPAND_DEPTH_OPTIONS = [1, 2, 3, 4, 5] as const;

export type AppTopoExpandDepth = (typeof APP_TOPO_EXPAND_DEPTH_OPTIONS)[number];

export const APP_TOPO_DEFAULT_EXPAND_DEPTH: AppTopoExpandDepth = 3;

export const APP_TOPO_EXPAND_DEPTH_STORAGE_KEY =
  'bk-lite:cmdb:app-topo-expand-depth';

export const isAppTopoExpandDepth = (
  value: unknown
): value is AppTopoExpandDepth =>
  APP_TOPO_EXPAND_DEPTH_OPTIONS.includes(value as AppTopoExpandDepth);

export const parseAppTopoExpandDepth = (
  value: unknown,
  fallback: AppTopoExpandDepth = APP_TOPO_DEFAULT_EXPAND_DEPTH
): AppTopoExpandDepth => {
  const numeric = typeof value === 'string' ? Number(value) : value;
  return isAppTopoExpandDepth(numeric) ? numeric : fallback;
};

interface StorageLike {
  getItem: (key: string) => string | null;
  setItem: (key: string, value: string) => void;
}

export const readAppTopoExpandDepth = (
  storage: Pick<StorageLike, 'getItem'> | null | undefined
): AppTopoExpandDepth => {
  try {
    if (!storage) return APP_TOPO_DEFAULT_EXPAND_DEPTH;
    return parseAppTopoExpandDepth(storage.getItem(APP_TOPO_EXPAND_DEPTH_STORAGE_KEY));
  } catch {
    return APP_TOPO_DEFAULT_EXPAND_DEPTH;
  }
};

export const writeAppTopoExpandDepth = (
  storage: Pick<StorageLike, 'setItem'> | null | undefined,
  depth: AppTopoExpandDepth
): boolean => {
  try {
    if (!storage) return false;
    storage.setItem(APP_TOPO_EXPAND_DEPTH_STORAGE_KEY, String(depth));
    return true;
  } catch {
    return false;
  }
};
