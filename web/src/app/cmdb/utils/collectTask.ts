import useAssetDataStore from '@/app/cmdb/store/useAssetDataStore';

interface CollectTaskItem {
  id: number | string;
  name: string;
}

type CollectTaskMap = Record<string, string>;

interface CollectTaskCache {
  expiresAt: number;
  data: CollectTaskMap;
}

const CACHE_KEY = 'cmdb_collect_task_name_map';
const CACHE_TTL_MS = 60 * 60 * 1000;

const isBrowser = () => typeof window !== 'undefined';

const readCache = (): CollectTaskMap | null => {
  if (!isBrowser()) return null;
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as CollectTaskCache;
    if (!parsed?.expiresAt || !parsed?.data) return null;
    if (Date.now() > parsed.expiresAt) return null;
    return parsed.data;
  } catch {
    return null;
  }
};

const writeCache = (data: CollectTaskMap) => {
  if (!isBrowser()) return;
  const payload: CollectTaskCache = {
    expiresAt: Date.now() + CACHE_TTL_MS,
    data,
  };
  localStorage.setItem(CACHE_KEY, JSON.stringify(payload));
};

const normalizeCollectTaskMap = (items: CollectTaskItem[]) => {
  const map: CollectTaskMap = {};
  for (const item of items) {
    if (item?.id === undefined || item?.id === null) {
      continue;
    }
    if (!item?.name) {
      continue;
    }
    map[String(item.id)] = String(item.name);
  }
  return map;
};

export const ensureCollectTaskMap = async (
  fetcher: () => Promise<CollectTaskItem[]>
) => {
  const cached = readCache();
  if (cached) {
    useAssetDataStore.getState().setCollectTaskMap(cached);
    return cached;
  }

  const items = await fetcher();
  const map = normalizeCollectTaskMap(Array.isArray(items) ? items : []);
  useAssetDataStore.getState().setCollectTaskMap(map);
  writeCache(map);
  return map;
};

export const formatCollectTaskDisplay = (
  value: unknown,
  taskMap: CollectTaskMap
) => {
  if (value === undefined || value === null || value === '') {
    return '--';
  }
  const id = String(value);
  const name = taskMap[id];
  if (name) {
    return `${name}(${id})`;
  }
  return `未找到任务(${id})`;
};
