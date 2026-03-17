import useAssetDataStore from '@/app/cmdb/store/useAssetDataStore';

interface CollectTaskItem {
  id: number | string;
  name: string;
  plugin?: string;
  category?: string;
}

type CollectTaskMap = Record<string, string>;
type CollectTaskRouteMap = Record<string, { plugin: string; category: string }>;

const COLLECTION_PATH = '/cmdb/assetManage/autoDiscovery/collection';

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

const normalizeCollectTaskPluginMap = (items: CollectTaskItem[]) => {
  const map: CollectTaskRouteMap = {};
  for (const item of items) {
    if (item?.id === undefined || item?.id === null) {
      continue;
    }
    const plugin = item?.plugin;
    const category = item?.category;
    if (!plugin || !category) {
      continue;
    }
    map[String(item.id)] = {
      plugin: String(plugin),
      category: String(category),
    };
  }
  return map;
};

export const ensureCollectTaskMap = async (
  fetcher: () => Promise<CollectTaskItem[]>
) => {
  const items = await fetcher();
  const safeItems = Array.isArray(items) ? items : [];
  const map = normalizeCollectTaskMap(safeItems);
  const routeMap = normalizeCollectTaskPluginMap(safeItems);
  useAssetDataStore.getState().setCollectTaskMap(map);
  useAssetDataStore.getState().setCollectTaskRouteMap(routeMap);
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
    return `${name}`;
  }
  return `未找到任务(${id})`;
};

export const buildCollectTaskDetailUrl = (params: {
  taskId: string;
  pluginId: string;
  categoryId: string;
}) => {
  const searchParams = new URLSearchParams();
  searchParams.set('category', params.categoryId);
  searchParams.set('plugin', params.pluginId);
  searchParams.set('taskId', params.taskId);
  return `${COLLECTION_PATH}?${searchParams.toString()}`;
};

export const getCollectTaskLinkMeta = (
  value: unknown
) => {
  const state = useAssetDataStore.getState();
  const taskMap = state.collectTaskMap;
  const taskRouteMap = state.collectTaskRouteMap;

  if (value === undefined || value === null || value === '') {
    return {
      displayText: '--',
      clickable: false,
    } as const;
  }

  const taskId = String(value);
  const taskName = taskMap[taskId];
  const displayText = taskName ? `${taskName}` : `未找到任务(${taskId})`;
  const route = taskRouteMap[taskId];
  const pluginId = route?.plugin || '';
  const categoryId = route?.category || '';

  if (!taskName || !pluginId || !categoryId) {
    return {
      displayText,
      clickable: false,
    } as const;
  }

  return {
    displayText,
    clickable: true,
    href: buildCollectTaskDetailUrl({
      taskId,
      pluginId,
      categoryId,
    }),
  } as const;
};
