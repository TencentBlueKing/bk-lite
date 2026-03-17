import useAssetDataStore from '@/app/cmdb/store/useAssetDataStore';
import type { TreeNode } from '@/app/cmdb/types/autoDiscovery';

interface CollectTaskItem {
  id: number | string;
  name: string;
  plugin?: string;
  model_id?: string;
}

interface CollectTaskRouteItem {
  id: number | string;
  model_id?: string;
}

type CollectTaskMap = Record<string, string>;
type CollectTaskPluginMap = Record<string, string>;
type CollectPluginCategoryMap = Record<string, string>;
type CollectModelPluginMap = Record<string, string>;

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
  const map: CollectTaskPluginMap = {};
  for (const item of items) {
    if (item?.id === undefined || item?.id === null) {
      continue;
    }
    // Given 后端可能逐步灰度 plugin 字段，When plugin 缺失，Then 回退 model_id 保持兼容。
    const plugin = item?.plugin || item?.model_id;
    if (!plugin) {
      continue;
    }
    map[String(item.id)] = String(plugin);
  }
  return map;
};

const buildCollectPluginRouteMaps = (
  tree: TreeNode[]
): {
  pluginCategoryMap: CollectPluginCategoryMap;
  modelPluginMap: CollectModelPluginMap;
} => {
  const pluginCategoryMap: CollectPluginCategoryMap = {};
  const modelPluginMap: CollectModelPluginMap = {};

  const visit = (node: TreeNode, categoryId: string, isCategory = false) => {
    const hasChildren = Boolean(node.children?.length);
    const isPluginNode = !isCategory && (!hasChildren || Boolean(node.model_id));

    if (isPluginNode) {
      const pluginId = String(node.id);
      // Given 详情路由依赖 category/plugin，When 命中插件节点，Then 记录 plugin->category。
      pluginCategoryMap[pluginId] = categoryId;
      if (node.model_id) {
        // Given 某些页面仅有 model_id，When 缺少 task->plugin，Then 使用 model->plugin 兜底。
        modelPluginMap[String(node.model_id)] = pluginId;
      }
    }

    if (hasChildren) {
      node.children?.forEach((child) => visit(child, categoryId));
    }
  };

  tree.forEach((root) => {
    const categoryId = String(root.id);
    root.children?.forEach((child) => visit(child, categoryId));
  });

  return { pluginCategoryMap, modelPluginMap };
};

export const ensureCollectTaskMap = async (
  fetcher: () => Promise<CollectTaskItem[]>
) => {
  const items = await fetcher();
  const safeItems = Array.isArray(items) ? items : [];
  const map = normalizeCollectTaskMap(safeItems);
  const pluginMap = normalizeCollectTaskPluginMap(safeItems);
  useAssetDataStore.getState().setCollectTaskMap(map);
  useAssetDataStore.getState().setCollectTaskPluginMap(pluginMap);
  return map;
};

export const setCollectTaskPluginMapByTasks = (
  tasks: CollectTaskRouteItem[]
) => {
  const pluginMap: CollectTaskPluginMap = {};
  for (const task of tasks) {
    if (task?.id === undefined || task?.id === null || !task?.model_id) {
      continue;
    }
    pluginMap[String(task.id)] = String(task.model_id);
  }
  useAssetDataStore.getState().setCollectTaskPluginMap(pluginMap);
  return pluginMap;
};

export const ensureCollectModelTreeCache = async (
  fetcher: () => Promise<TreeNode[]>
) => {
  const tree = await fetcher();
  const safeTree = Array.isArray(tree) ? tree : [];
  const { pluginCategoryMap, modelPluginMap } = buildCollectPluginRouteMaps(safeTree);
  const store = useAssetDataStore.getState();
  // Given 页面内多次点击 collect_task，When tree 已加载，Then 直接复用缓存减少请求。
  store.setCollectModelTree(safeTree);
  store.setCollectPluginCategoryMap(pluginCategoryMap);
  store.setCollectModelPluginMap(modelPluginMap);
  return safeTree;
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
  value: unknown,
  pluginIdHint?: string
) => {
  const state = useAssetDataStore.getState();
  const taskMap = state.collectTaskMap;
  const taskPluginMap = state.collectTaskPluginMap;
  const pluginCategoryMap = state.collectPluginCategoryMap;
  const modelPluginMap = state.collectModelPluginMap;

  if (value === undefined || value === null || value === '') {
    return {
      displayText: '--',
      clickable: false,
    } as const;
  }

  const taskId = String(value);
  const taskName = taskMap[taskId];
  const displayText = taskName ? `${taskName}` : `未找到任务(${taskId})`;
  const resolvePluginId = (id?: string) => {
    if (!id) {
      return '';
    }
    return modelPluginMap[id] || id;
  };

  // Given 同时存在任务插件与页面 hint，When 生成跳转，Then 优先任务插件保证准确性。
  const pluginIdFromTask = resolvePluginId(taskPluginMap[taskId]);
  const pluginIdFromHint = resolvePluginId(pluginIdHint);
  const pluginId = pluginIdFromTask || pluginIdFromHint;
  const categoryId = pluginId ? pluginCategoryMap[pluginId] : '';

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
