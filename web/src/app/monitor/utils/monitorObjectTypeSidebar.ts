import { TreeItem, TreeSortData } from '@/app/monitor/types';
import {
  isCloudFamilySidebarType,
  UNIFIED_CLOUD_ROOT_TYPE
} from '@/app/monitor/utils/monitorObject';

export interface MonitorObjectTypeSidebarItem {
  id: string;
  name: string;
  object_count?: number;
}

const typeLeaf = (type: MonitorObjectTypeSidebarItem): TreeItem => ({
  title: `${type.name}（${type.object_count || 0}）`,
  key: type.id,
  label: type.id,
  children: []
});

const resolveCloudTypeRootTitle = (
  types: MonitorObjectTypeSidebarItem[]
): string => {
  const cloud = types.find((item) => item.id === UNIFIED_CLOUD_ROOT_TYPE);
  if (cloud?.name) return cloud.name;
  const looksZh = types.some((item) => /[\u4e00-\u9fff]/.test(item.name || ''));
  return looksZh ? '云' : 'Cloud';
};

/**
 * 对象类型登记表侧栏：Tencent Cloud / Aliyun Cloud / Cloud 折成唯一「云」叶，无子行。
 * 点「云」用 key=Cloud；右侧按云族 type 聚合列平台对象。
 */
export const buildMonitorObjectTypeSidebarTree = (
  types: MonitorObjectTypeSidebarItem[]
): TreeItem[] => {
  const tree: Array<TreeItem | null> = [];
  const cloudFamily: MonitorObjectTypeSidebarItem[] = [];
  let cloudSlot = -1;

  for (const type of types) {
    if (isCloudFamilySidebarType(type.id)) {
      if (cloudSlot === -1) {
        cloudSlot = tree.length;
        tree.push(null);
      }
      cloudFamily.push(type);
      continue;
    }
    tree.push(typeLeaf(type));
  }

  if (!cloudFamily.length) {
    return tree.filter((item): item is TreeItem => Boolean(item));
  }

  const objectCount = cloudFamily.reduce(
    (sum, item) => sum + (item.object_count || 0),
    0
  );
  const root: TreeItem = {
    title: `${resolveCloudTypeRootTitle(cloudFamily)}（${objectCount}）`,
    key: UNIFIED_CLOUD_ROOT_TYPE,
    label: UNIFIED_CLOUD_ROOT_TYPE,
    children: []
  };
  if (cloudSlot === -1) {
    tree.push(root);
  } else {
    tree[cloudSlot] = root;
  }
  return tree.filter((item): item is TreeItem => Boolean(item));
};

/** 对象页拖拽：把唯一「云」叶展开回各原 type id，避免只写 type=Cloud。 */
export const expandCloudFamilyTypeSortData = (
  sortData: TreeSortData[],
  typeIds: string[]
): TreeSortData[] => {
  const familyIds = typeIds.filter((id) => isCloudFamilySidebarType(id));
  const expanded: TreeSortData[] = [];
  let familyInserted = false;
  for (const item of sortData) {
    if (item.type === 'all') {
      continue;
    }
    if (isCloudFamilySidebarType(item.type)) {
      if (familyInserted) continue;
      familyInserted = true;
      for (const id of familyIds) {
        expanded.push({ type: id, object_list: [] });
      }
      continue;
    }
    expanded.push(item);
  }
  return expanded;
};

export const resolveMonitorObjectTypeSelection = <T extends { id: string }>(
  key: string,
  types: T[]
): T | undefined => {
  const exact = types.find((item) => item.id === key);
  if (exact) return exact;
  if (key !== UNIFIED_CLOUD_ROOT_TYPE) return undefined;
  return types.find((item) => isCloudFamilySidebarType(item.id));
};

export const resolveMonitorObjectTypeTreeKey = (typeId?: string): string =>
  typeId && isCloudFamilySidebarType(typeId)
    ? UNIFIED_CLOUD_ROOT_TYPE
    : typeId || '';
