import { create } from 'zustand'//导入依赖
import { CollectTask } from '@/app/cmdb/types/autoDiscovery'


// 定义 Store 类型
interface AssetManageStore {
  editingId: number | null;
  scan_cycle_type: string | null;
  copyTaskData: CollectTask | null;
  setEditingId: (id: number | null) => void;
  setScanCycleType: (type: string | null) => void;
  setCopyTaskData: (data: CollectTask | null) => void;
}

//创建store
const useAssetManageStore = create<AssetManageStore>((set) => ({
  //创建数据
  editingId: null, // 编辑任务id
  scan_cycle_type: null, // 扫描周期类型
  copyTaskData: null, // 复制任务数据

  // 方法
  setEditingId: (id: number | null) => {
    set({ editingId: id });
  },

  setScanCycleType: (type: string | null) => {
    set({ scan_cycle_type: type });
  },

  setCopyTaskData: (data: CollectTask | null) => {
    set({ copyTaskData: data });
  },
}))

//导出store
export default useAssetManageStore;