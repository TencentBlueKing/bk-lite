import { create } from 'zustand'
import type { SavedFilterItem } from '@/app/cmdb/api/userConfig';
import type { TreeNode } from '@/app/cmdb/types/autoDiscovery';

export interface FilterItem {
  field: string;
  type: string;
  value?: string | number | boolean | (string | number)[];
  start?: string;
  end?: string;
}

export type SavedFilter = SavedFilterItem;

interface UserConfigs {
  cmdb_saved_filters?: Record<string, SavedFilterItem[]>;
  [key: string]: unknown;
}

interface AssetDataStore {
  query_list: FilterItem[];
  searchAttr: string;
  case_sensitive: boolean;
  cloud_list: { proxy_id: string; proxy_name: string }[];
  // Given 实例页需要显示采集任务名称，When 仅有 collect_task id，Then 通过该映射展示任务名。
  collectTaskMap: Record<string, string>;
  // Given 跳转采集详情必须带 plugin，When 已拿到 taskId，Then 通过该映射查到 plugin。
  collectTaskPluginMap: Record<string, string>;
  // Given 跳转采集详情必须带 category，When 已拿到 plugin，Then 通过该映射查到 category。
  collectPluginCategoryMap: Record<string, string>;
  // Given 某些场景只有 modelId，When 缺少 task->plugin，Then 用 model->plugin 作为兜底。
  collectModelPluginMap: Record<string, string>;
  // Given collect_model_tree 在页面生命周期内稳定，When 已拉取一次，Then 缓存在 store 复用。
  collectModelTree: TreeNode[];
  user_configs: UserConfigs;
  needRefresh: boolean;
  add: (item: FilterItem) => FilterItem[];
  remove: (index: number) => FilterItem[];
  clear: () => FilterItem[];
  update: (index: number, item: FilterItem) => FilterItem[];
  setCaseSensitive: (value: boolean) => void;
  setQueryList: (items: FilterItem[]) => FilterItem[];
  setCloudList: (list: { proxy_id: string; proxy_name: string }[]) => void;
  setCollectTaskMap: (map: Record<string, string>) => void;
  setCollectTaskPluginMap: (map: Record<string, string>) => void;
  setCollectTaskPlugin: (taskId: string, pluginId: string) => void;
  setCollectPluginCategoryMap: (map: Record<string, string>) => void;
  setCollectModelPluginMap: (map: Record<string, string>) => void;
  setCollectModelTree: (tree: TreeNode[]) => void;
  setUserConfigs: (configs: UserConfigs) => void;
  updateUserConfig: (key: string, value: unknown) => void;
  getSavedFilters: (modelId: string) => SavedFilterItem[];
  applySavedFilter: (filter: SavedFilter) => FilterItem[];
  setNeedRefresh: (value: boolean) => void;
}

const useAssetDataStore = create<AssetDataStore>((set, get) => ({
  query_list: [],
  searchAttr: "inst_name",
  case_sensitive: false,
  cloud_list: [],
  collectTaskMap: {},
  collectTaskPluginMap: {},
  collectPluginCategoryMap: {},
  collectModelPluginMap: {},
  collectModelTree: [],
  user_configs: {},
  needRefresh: false,

  add: (item: FilterItem) => {
    set((state) => ({ query_list: [...state.query_list, item] }));
    return get().query_list;
  },
  remove: (index: number) => {
    set((state) => ({
      query_list: state.query_list.filter((_, i) => i !== index),
    }));
    return get().query_list;
  },
  clear: () => {
    set({ query_list: [] });
    return get().query_list;
  },
  update: (index: number, item: FilterItem) => {
    set((state) => {
      const newList = [...state.query_list];
      newList[index] = item;
      return { query_list: newList };
    });
    return get().query_list;
  },
  setCaseSensitive: (value: boolean) => {
    set({ case_sensitive: value });
  },
  setQueryList: (items: FilterItem[]) => {
    set({ query_list: items });
    return get().query_list;
  },
  setCloudList: (list: { proxy_id: string; proxy_name: string }[]) => {
    set({ cloud_list: list });
  },

  setCollectTaskMap: (map: Record<string, string>) => {
    set({ collectTaskMap: map });
  },

  setCollectTaskPluginMap: (map: Record<string, string>) => {
    set({ collectTaskPluginMap: map });
  },

  setCollectTaskPlugin: (taskId: string, pluginId: string) => {
    set((state) => ({
      collectTaskPluginMap: {
        ...state.collectTaskPluginMap,
        [taskId]: pluginId,
      },
    }));
  },

  setCollectPluginCategoryMap: (map: Record<string, string>) => {
    set({ collectPluginCategoryMap: map });
  },

  setCollectModelPluginMap: (map: Record<string, string>) => {
    set({ collectModelPluginMap: map });
  },

  setCollectModelTree: (tree: TreeNode[]) => {
    set({ collectModelTree: tree });
  },

  setUserConfigs: (configs: UserConfigs) => {
    set({ user_configs: configs });
  },

  updateUserConfig: (key: string, value: unknown) => {
    set((state) => ({
      user_configs: { ...state.user_configs, [key]: value },
    }));
  },

  getSavedFilters: (modelId: string) => {
    const savedFilters = get().user_configs.cmdb_saved_filters;
    return savedFilters?.[modelId] || [];
  },

  applySavedFilter: (filter: SavedFilter) => {
    set({ query_list: filter.filters as FilterItem[] });
    return filter.filters as FilterItem[];
  },

  setNeedRefresh: (value: boolean) => {
    set({ needRefresh: value });
  },
}))

export default useAssetDataStore;
