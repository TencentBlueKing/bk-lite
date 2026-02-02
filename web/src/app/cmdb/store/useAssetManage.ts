import { create } from 'zustand'//导入依赖


// 定义 Store 类型
interface AssetManageStore {
  editingId: number | null;
  scan_cycle_type: string | null;
  setEditingId: (id: number | null) => void;
  setScanCycleType: (type: string | null) => void;
}

//创建store
const useAssetManageStore = create<AssetManageStore>((set) => ({
  //创建数据
  editingId: null, // 编辑任务id
  scan_cycle_type: null, // 扫描周期类型

  // 方法
  setEditingId: (id: number | null) => {
    set({ editingId: id });
  },

  setScanCycleType: (type: string | null) => {
    set({ scan_cycle_type: type });
  },
}))

//导出store
export default useAssetManageStore;