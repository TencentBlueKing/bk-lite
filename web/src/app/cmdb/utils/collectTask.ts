import useAssetDataStore from '@/app/cmdb/store/useAssetDataStore';

interface CollectTaskItem {
  id: number | string;
  name: string;
}

type CollectTaskMap = Record<string, string>;

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
  const items = await fetcher();
  const map = normalizeCollectTaskMap(Array.isArray(items) ? items : []);
  useAssetDataStore.getState().setCollectTaskMap(map);
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
