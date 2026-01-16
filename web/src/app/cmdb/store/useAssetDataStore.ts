import { create } from 'zustand'//导入依赖

// 定义筛选项类型
export interface FilterItem {
  field: string;
  type: string;
  value?: string | number | boolean | (string | number)[];
  start?: string;
  end?: string;
}

// 定义 Store 类型
interface AssetDataStore {
  query_list: FilterItem[];
  searchAttr: string;
  case_sensitive: boolean;
  add: (item: FilterItem) => FilterItem[];
  remove: (index: number) => FilterItem[];
  clear: () => FilterItem[];
  update: (index: number, item: FilterItem) => FilterItem[];
  setCaseSensitive: (value: boolean) => void;
}

//创建store
const useAssetDataStore = create<AssetDataStore>((set, get) => ({
  //创建数据
  query_list: [], // 筛选条件列表
  searchAttr: "inst_name", // 当前搜索字段
  case_sensitive: false, // 是否精确匹配（大小写敏感）

  // 方法
  add: (item: FilterItem) => {
    set((state) => ({ query_list: [...state.query_list, item] }));
    return get().query_list;
  },
  remove: (index: number) => {
    set((state) => ({
      query_list: state.query_list.filter((_, i) => i !== index),
      current_query: state.query_list[index] // 保留当前删除的筛选项
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
}))

//导出store
export default useAssetDataStore;