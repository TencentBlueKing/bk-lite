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
