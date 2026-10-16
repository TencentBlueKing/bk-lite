/**
 * 监控对象动态工具函数
 *
 * 这些函数基于 API 返回的 objects 数据动态计算，替代硬编码常量。
 *
 * API 数据结构:
 * - level: 'base' | 'derivative' - 基础对象或派生对象
 * - type: string - 对象类型分组（如 'Container Management', 'K8S', 'VMWare'）
 * - parent: number | null - 派生对象的父对象 ID
 *
 * 复合对象页签按插件家族（parent）划分，而不是按 type。
 * type 只表示侧边栏分类；多个平台可以共用同一个 type（如 Cloud）。
 */

import { ObjectItem } from '@/app/monitor/types';

const objectLevel = (obj: ObjectItem): 'base' | 'derivative' =>
  obj.level === 'derivative' ? 'derivative' : 'base';

const resolveObject = (
  objectOrName: ObjectItem | string,
  objects: ObjectItem[]
): ObjectItem | undefined => {
  if (typeof objectOrName === 'string') {
    return objects.find((obj) => obj.name === objectOrName);
  }
  return objectOrName;
};

const baseObjectsOfType = (type: string, objects: ObjectItem[]): ObjectItem[] =>
  objects.filter((obj) => obj.type === type && objectLevel(obj) === 'base');

const sortPluginFamily = (family: ObjectItem[]): ObjectItem[] =>
  [...family].sort((left, right) => {
    const leftRank = objectLevel(left) === 'base' ? 0 : 1;
    const rightRank = objectLevel(right) === 'base' ? 0 : 1;
    if (leftRank !== rightRank) return leftRank - rightRank;
    return left.id - right.id;
  });

const familyRootId = (target: ObjectItem): number =>
  objectLevel(target) === 'base' || target.parent == null
    ? target.id
    : target.parent;

/**
 * 判断对象是否为派生对象（level === 'derivative'）
 *
 * 派生对象是从基础对象派生出来的子对象，如：
 * - Docker Container（派生自 Docker）
 * - ESXI/VM/DataStorage（派生自 vCenter）
 * - Pod/Node（派生自 Cluster）
 * - CVM（派生自 TCP）
 * - SangforSCPHost/SangforSCPVM（派生自 SangforSCP）
 */
export const isDerivativeObject = (
  objectOrName: ObjectItem | string,
  objects?: ObjectItem[]
): boolean => {
  if (typeof objectOrName === 'string') {
    if (!objects) return false;
    const obj = objects.find((item) => item.name === objectOrName);
    return obj?.level === 'derivative';
  }
  return objectOrName?.level === 'derivative';
};

export const CISCO_MERAKI_OBJECT_NAME = 'Cisco Meraki';

const MERAKI_DERIVATIVE_OBJECT_NAMES = new Set([
  'Meraki Network',
  'Meraki Device',
  'Meraki Wireless AP',
  'Meraki Switch',
  'Meraki Appliance'
]);

/**
 * 视图 / 专业大盘侧栏把 Cisco Meraki 的派生对象挂到父节点下。
 * 名称集合覆盖内置五个子对象；parent 指向 Cisco Meraki 时也认，避免漏挂。
 * 云族挂父见 isCloudFamilySidebarType / buildMonitorObjectSidebarTree；
 * 禁止借此全局去掉 isDerivativeObject（VMware / K8s 等非云派生仍隐藏）。
 */
export const isMerakiSidebarDerivative = (
  item: ObjectItem,
  objects: ObjectItem[]
): boolean => {
  if (MERAKI_DERIVATIVE_OBJECT_NAMES.has(item.name)) {
    return true;
  }
  if (item.parent == null) {
    return false;
  }
  return objects.some(
    (obj) => obj.id === item.parent && obj.name === CISCO_MERAKI_OBJECT_NAME
  );
};

export const attachMerakiSidebarChildren = <T extends { label?: string; children: T[] }>(
  groups: Record<string, { children: T[] }>,
  merakiDerivatives: ObjectItem[],
  toNode: (item: ObjectItem) => T
): void => {
  attachSidebarChildrenByParentLabel(
    groups,
    merakiDerivatives,
    toNode,
    CISCO_MERAKI_OBJECT_NAME
  );
};

/**
 * 把派生节点挂到分组内 label 匹配的父叶子下（Meraki / 云族共用）。
 */
export const attachSidebarChildrenByParentLabel = <T extends { label?: string; children: T[] }>(
  groups: Record<string, { children: T[] }>,
  derivatives: ObjectItem[],
  toNode: (item: ObjectItem) => T,
  parentLabel: string
): void => {
  if (!derivatives.length) {
    return;
  }
  for (const group of Object.values(groups)) {
    const parent = group.children.find((child) => child.label === parentLabel);
    if (!parent) {
      continue;
    }
    parent.children = derivatives.map(toNode);
    return;
  }
};

/** 演进现有 type=Cloud 作为唯一「云」总根；腾讯云 / 阿里云 type 并入其下。 */
export const UNIFIED_CLOUD_ROOT_TYPE = 'Cloud';

const CLOUD_FAMILY_SIDEBAR_TYPES = new Set([
  UNIFIED_CLOUD_ROOT_TYPE,
  'Tencent Cloud',
  'Aliyun Cloud'
]);

const CLOUD_L2_TYPE_DISPLAYS = new Set([
  '腾讯云',
  '阿里云',
  'Tencent Cloud',
  'Aliyun Cloud'
]);

export const isCloudFamilySidebarType = (type?: string | null): boolean =>
  Boolean(type && CLOUD_FAMILY_SIDEBAR_TYPES.has(type));

/**
 * 获取所有派生对象的名称列表
 */
export const getDerivativeObjectNames = (objects: ObjectItem[]): string[] => {
  return objects
    .filter((obj) => objectLevel(obj) === 'derivative')
    .map((obj) => obj.name);
};

/**
 * 判断对象是否需要标签入口（即基础对象，且有本插件家族的派生对象）
 *
 * 需要标签入口的对象特点：
 * - level === 'base'
 * - 存在 parent 指向它的派生对象；若 parent 未写入，仅当该 type 只有一个基础对象时回退到同 type
 *
 * 例如：Docker, Cluster, vCenter, TCP, SangforSCP
 * 这些对象的指标页面需要显示 Segmented tabs 来切换不同子对象
 */
export const needsTagsEntry = (
  objectOrName: ObjectItem | string,
  objects: ObjectItem[]
): boolean => {
  const targetObj = resolveObject(objectOrName, objects);

  if (!targetObj || objectLevel(targetObj) !== 'base') {
    return false;
  }

  if (objects.some((obj) => obj.parent === targetObj.id)) {
    return true;
  }

  if (baseObjectsOfType(targetObj.type, objects).length !== 1) {
    return false;
  }

  return objects.some(
    (obj) => obj.type === targetObj.type && objectLevel(obj) === 'derivative'
  );
};

/**
 * 获取所有需要标签入口的对象名称列表
 */
export const getNeedsTagsEntryObjectNames = (
  objects: ObjectItem[]
): string[] => {
  return objects
    .filter((obj) => needsTagsEntry(obj, objects))
    .map((obj) => obj.name);
};

/**
 * 根据对象名称获取其 type
 */
export const getObjectTypeByName = (
  name: string,
  objects: ObjectItem[]
): string | undefined => {
  return objects.find((obj) => obj.name === name)?.type;
};

/**
 * 获取同一类型下的所有对象
 */
export const getObjectsByType = (
  type: string,
  objects: ObjectItem[]
): ObjectItem[] => {
  return objects.filter((obj) => obj.type === type);
};

/**
 * 获取某个对象所属插件家族（基础对象 + 其子对象）。
 *
 * 优先用 parent；parent 缺失时，仅当该 type 只有一个基础对象才按 type 回退。
 * 多个平台共用 type（如 Cloud 下的 SangforSCP 与 CNware）时不会混在一起。
 */
export const getPluginFamilyObjects = (
  objectOrName: ObjectItem | string,
  objects: ObjectItem[]
): ObjectItem[] => {
  const target = resolveObject(objectOrName, objects);
  if (!target) return [];

  const rootId = familyRootId(target);
  const familyByParent = objects.filter(
    (obj) => obj.id === rootId || obj.parent === rootId
  );
  if (
    familyByParent.length > 1 ||
    objects.some((obj) => obj.parent === rootId)
  ) {
    return sortPluginFamily(familyByParent);
  }

  if (baseObjectsOfType(target.type, objects).length === 1) {
    return sortPluginFamily(objects.filter((obj) => obj.type === target.type));
  }

  return [target];
};

/**
 * 获取某个对象的基础对象（父对象）
 *
 * 如果对象本身是 base 类型，返回自身
 * 如果对象是 derivative 类型，返回 parent 指向的基础对象
 */
export const getBaseObject = (
  objectOrName: ObjectItem | string,
  objects: ObjectItem[]
): ObjectItem | undefined => {
  const targetObj = resolveObject(objectOrName, objects);

  if (!targetObj) return undefined;

  if (objectLevel(targetObj) === 'base') {
    return targetObj;
  }

  if (targetObj.parent != null) {
    return objects.find((obj) => obj.id === targetObj.parent);
  }

  const bases = baseObjectsOfType(targetObj.type, objects);
  return bases.length === 1 ? bases[0] : undefined;
};

/**
 * 获取某个基础对象的所有派生对象
 */
export const getDerivativeObjects = (
  baseObjectOrName: ObjectItem | string,
  objects: ObjectItem[]
): ObjectItem[] => {
  const baseObj = resolveObject(baseObjectOrName, objects);

  if (!baseObj) return [];

  const children = objects.filter((obj) => obj.parent === baseObj.id);
  if (children.length) {
    return children;
  }

  if (baseObjectsOfType(baseObj.type, objects).length !== 1) {
    return [];
  }

  return objects.filter(
    (obj) => obj.type === baseObj.type && objectLevel(obj) === 'derivative'
  );
};

/**
 * 构建对象名称到类型的映射（仅包含需要标签入口的对象）
 */
export const buildObjectNameToTypeMap = (
  objects: ObjectItem[]
): Record<string, string> => {
  const map: Record<string, string> = {};

  objects
    .filter((obj) => needsTagsEntry(obj, objects))
    .forEach((obj) => {
      map[obj.name] = obj.type;
    });

  return map;
};

/**
 * 过滤不可见对象，以及父对象已隐藏的子对象。
 * 对象管理页可单独关掉父对象可见性；子对象自身 is_visible 可能仍为 true。
 */
export const filterVisibleMonitorObjects = (
  objects: ObjectItem[]
): ObjectItem[] => {
  const hiddenIds = new Set(
    objects
      .filter((item) => item.is_visible === false)
      .map((item) => item.id)
  );
  let grew = true;
  while (grew) {
    grew = false;
    for (const item of objects) {
      if (hiddenIds.has(item.id)) continue;
      if (item.parent != null && hiddenIds.has(item.parent)) {
        hiddenIds.add(item.id);
        grew = true;
      }
    }
  }
  return objects.filter((item) => !hiddenIds.has(item.id));
};

const isCloudFamilyPlatformBase = (item: ObjectItem): boolean =>
  isCloudFamilySidebarType(item.type) && objectLevel(item) === 'base';

/**
 * 云族派生的父平台：优先 parent / getBaseObject，缺失时按名称前缀
 * （SangforSCPHost → SangforSCP，CNwareVM → CNware）。CVM 不依赖前缀，走 parent。
 */
export const resolveCloudFamilyParent = (
  item: ObjectItem,
  objects: ObjectItem[]
): ObjectItem | undefined => {
  if (isCloudFamilyPlatformBase(item) && item.parent == null) {
    return undefined;
  }
  const byParent = getBaseObject(item, objects);
  if (
    byParent &&
    byParent.id !== item.id &&
    isCloudFamilySidebarType(byParent.type)
  ) {
    return byParent;
  }
  return objects
    .filter(isCloudFamilyPlatformBase)
    .find(
      (platform) =>
        platform.id !== item.id &&
        (item.parent === platform.id ||
          (item.name !== platform.name && item.name.startsWith(platform.name)))
    );
};

export const isCloudFamilySidebarDerivative = (
  item: ObjectItem,
  objects: ObjectItem[]
): boolean => {
  if (!isCloudFamilySidebarType(item.type)) {
    return false;
  }
  if (objectLevel(item) === 'derivative') {
    return true;
  }
  return Boolean(resolveCloudFamilyParent(item, objects));
};

export const resolveUnifiedCloudRootTitle = (objects: ObjectItem[]): string => {
  const cloudType = objects.find(
    (item) =>
      item.type === UNIFIED_CLOUD_ROOT_TYPE &&
      item.display_type &&
      !CLOUD_L2_TYPE_DISPLAYS.has(item.display_type)
  );
  if (cloudType?.display_type) {
    return cloudType.display_type;
  }
  const looksZh = objects.some((item) =>
    /[\u4e00-\u9fff]/.test(String(item.display_name || item.display_type || ''))
  );
  return looksZh ? '云' : 'Cloud';
};

const cloudPlatformNodeTitle = (
  item: ObjectItem,
  fallbackTitle: string
): string => {
  if (item.type === 'Tencent Cloud' || item.type === 'Aliyun Cloud') {
    return item.display_type || fallbackTitle || item.name;
  }
  return fallbackTitle || item.display_name || item.name;
};

interface SidebarTreeNode {
  title?: unknown;
  label?: string;
  key?: string | number;
  children: SidebarTreeNode[];
}

const buildUnifiedCloudRoot = <T extends SidebarTreeNode>(
  cloudFamilyItems: ObjectItem[],
  objects: ObjectItem[],
  toNode: (item: ObjectItem) => T
): T => {
  const platforms = cloudFamilyItems.filter(
    (item) => !isCloudFamilySidebarDerivative(item, objects)
  );
  const derivatives = cloudFamilyItems.filter((item) =>
    isCloudFamilySidebarDerivative(item, objects)
  );
  const childrenByParentId = new Map<number, ObjectItem[]>();
  const unattached: ObjectItem[] = [];
  for (const item of derivatives) {
    const parent = resolveCloudFamilyParent(item, objects);
    if (!parent) {
      unattached.push(item);
      continue;
    }
    const siblings = childrenByParentId.get(parent.id) || [];
    siblings.push(item);
    childrenByParentId.set(parent.id, siblings);
  }

  const platformNodes = platforms.map((platform) => {
    const node = toNode(platform);
    node.title = cloudPlatformNodeTitle(platform, String(node.title || ''));
    const childItems = childrenByParentId.get(platform.id) || [];
    node.children = childItems.map(toNode);
    childrenByParentId.delete(platform.id);
    return node;
  });

  for (const [parentId, childItems] of childrenByParentId) {
    const parent = objects.find((item) => item.id === parentId);
    if (!parent) {
      unattached.push(...childItems);
      continue;
    }
    const node = toNode(parent);
    node.title = cloudPlatformNodeTitle(parent, String(node.title || ''));
    node.children = childItems.map(toNode);
    platformNodes.push(node);
  }

  platformNodes.push(...unattached.map(toNode));

  return {
    title: resolveUnifiedCloudRootTitle(objects),
    key: UNIFIED_CLOUD_ROOT_TYPE,
    children: platformNodes
  } as T;
};

/**
 * 视图 / 专业大盘对象树：
 * - 云族白名单（Cloud / Tencent Cloud / Aliyun Cloud）挂到唯一「云」根下，派生挂父；
 * - Meraki 维持挂父；
 * - 其余 type 仍按 #6351 隐藏派生，禁止全局去掉 isDerivativeObject。
 */
export const buildMonitorObjectSidebarTree = <T extends SidebarTreeNode>(
  objects: ObjectItem[],
  toNode: (item: ObjectItem) => T
): T[] => {
  const groups: Record<string, T> = {};
  const typeOrder: string[] = [];
  const merakiDerivatives: ObjectItem[] = [];
  const cloudFamilyItems: ObjectItem[] = [];

  const ensureGroup = (item: ObjectItem): T => {
    if (!groups[item.type]) {
      groups[item.type] = {
        title: item.display_type || '--',
        key: item.type,
        children: []
      } as T;
      typeOrder.push(item.type);
    }
    return groups[item.type];
  };

  for (const item of objects) {
    if (isCloudFamilySidebarType(item.type)) {
      if (!typeOrder.includes(UNIFIED_CLOUD_ROOT_TYPE)) {
        typeOrder.push(UNIFIED_CLOUD_ROOT_TYPE);
      }
      cloudFamilyItems.push(item);
      continue;
    }
    if (isMerakiSidebarDerivative(item, objects)) {
      ensureGroup(item);
      merakiDerivatives.push(item);
      continue;
    }
    if (isDerivativeObject(item, objects)) {
      continue;
    }
    ensureGroup(item).children.push(toNode(item));
  }

  attachMerakiSidebarChildren(groups, merakiDerivatives, toNode);

  if (cloudFamilyItems.length) {
    groups[UNIFIED_CLOUD_ROOT_TYPE] = buildUnifiedCloudRoot(
      cloudFamilyItems,
      objects,
      toNode
    );
  }

  const tree = typeOrder
    .map((type) => groups[type])
    .filter((group): group is T => Boolean(group));

  const otherGroup = groups.Other;
  if (otherGroup) {
    otherGroup.children = otherGroup.children.filter(
      (item) => item.label !== 'SNMP Trap'
    );
  }

  return tree;
};

const POD_MONITOR_OBJECT_NAMES = new Set(['Pod', 'K3SPod']);

export const isPodMonitorObject = (name?: string | null): boolean =>
  Boolean(name && POD_MONITOR_OBJECT_NAMES.has(name));
