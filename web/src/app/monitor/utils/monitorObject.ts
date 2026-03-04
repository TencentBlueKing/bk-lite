/**
 * 监控对象动态工具函数
 *
 * 这些函数基于 API 返回的 objects 数据动态计算，替代硬编码常量。
 *
 * API 数据结构:
 * - level: 'base' | 'derivative' - 基础对象或派生对象
 * - type: string - 对象类型分组（如 'Container Management', 'K8S', 'VMWare'）
 * - parent: number | null - 派生对象的父对象 ID
 */

import { ObjectItem } from '@/app/monitor/types';

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
    const obj = objects.find((o) => o.name === objectOrName);
    return obj?.level === 'derivative';
  }
  return objectOrName?.level === 'derivative';
};

/**
 * 获取所有派生对象的名称列表
 */
export const getDerivativeObjectNames = (objects: ObjectItem[]): string[] => {
  return objects
    .filter((obj) => obj.level === 'derivative')
    .map((obj) => obj.name);
};

/**
 * 判断对象是否需要标签入口（即基础对象，且有派生对象）
 *
 * 需要标签入口的对象特点：
 * - level === 'base'
 * - 存在同 type 的派生对象
 *
 * 例如：Docker, Cluster, vCenter, TCP, SangforSCP
 * 这些对象的指标页面需要显示 Segmented tabs 来切换不同子对象
 */
export const needsTagsEntry = (
  objectOrName: ObjectItem | string,
  objects: ObjectItem[]
): boolean => {
  let targetObj: ObjectItem | undefined;

  if (typeof objectOrName === 'string') {
    targetObj = objects.find((o) => o.name === objectOrName);
  } else {
    targetObj = objectOrName;
  }

  if (!targetObj || targetObj.level !== 'base') {
    return false;
  }

  // 检查是否有同 type 的派生对象
  return objects.some(
    (obj) => obj.type === targetObj!.type && obj.level === 'derivative'
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
 * 获取某个对象的基础对象（父对象）
 *
 * 如果对象本身是 base 类型，返回自身
 * 如果对象是 derivative 类型，返回同 type 的 base 对象
 */
export const getBaseObject = (
  objectOrName: ObjectItem | string,
  objects: ObjectItem[]
): ObjectItem | undefined => {
  let targetObj: ObjectItem | undefined;

  if (typeof objectOrName === 'string') {
    targetObj = objects.find((o) => o.name === objectOrName);
  } else {
    targetObj = objectOrName;
  }

  if (!targetObj) return undefined;

  if (targetObj.level === 'base') {
    return targetObj;
  }

  return objects.find(
    (obj) => obj.type === targetObj!.type && obj.level === 'base'
  );
};

/**
 * 获取某个基础对象的所有派生对象
 */
export const getDerivativeObjects = (
  baseObjectOrName: ObjectItem | string,
  objects: ObjectItem[]
): ObjectItem[] => {
  let baseObj: ObjectItem | undefined;

  if (typeof baseObjectOrName === 'string') {
    baseObj = objects.find((o) => o.name === baseObjectOrName);
  } else {
    baseObj = baseObjectOrName;
  }

  if (!baseObj) return [];

  return objects.filter(
    (obj) => obj.type === baseObj!.type && obj.level === 'derivative'
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
