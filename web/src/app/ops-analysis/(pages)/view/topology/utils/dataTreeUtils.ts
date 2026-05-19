/**
 * 数据树构建工具函数
 * 用于将数据源返回的数据结构转换为 Tree 组件所需的树形结构
 */

import type { TreeNode } from '@/app/ops-analysis/types/topology';
import type { ResponseFieldDefinition } from '@/app/ops-analysis/types/dataSource';

/**
 * 根据 field_schema 生成带备注的显示标题
 */
function getDisplayTitle(key: string, fieldSchema?: ResponseFieldDefinition[]): string {
  if (!fieldSchema || fieldSchema.length === 0) return key;
  const field = fieldSchema.find((f) => f.key === key);
  if (field && field.title) {
    return `${key}（${field.title}）`;
  }
  return key;
}

/**
 * 构建树形数据结构
 * @param obj 原始数据对象或数组
 * @param fieldSchema 可选，数据源定义的字段描述
 * @returns 树形节点数组
 */
export const buildTreeData = (obj: unknown, fieldSchema?: ResponseFieldDefinition[]): TreeNode[] => {
  if (typeof obj !== 'object' || obj === null) {
    return [];
  }

  const treeNodes: TreeNode[] = [];

  if (Array.isArray(obj) && obj.length > 0) {
    const firstElement = obj[0];
    if (typeof firstElement === 'object' && firstElement !== null) {
      return buildTreeData(firstElement, fieldSchema);
    } else {
      return [
        {
          title: '',
          key: 'value',
          value: 'value',
          isLeaf: true,
        },
      ];
    }
  }

  // 普通对象处理
  Object.keys(obj).forEach((key) => {
    const value = (obj as Record<string, unknown>)[key];

    if (
      typeof value === 'object' &&
      value !== null &&
      !Array.isArray(value)
    ) {
      const children = buildTreeData(value, fieldSchema);
      if (children.length > 0) {
        treeNodes.push({
          title: getDisplayTitle(key, fieldSchema),
          key: key,
          children: children.map((child) => ({
            ...child,
            key: `${key}.${child.key}`,
            value: `${key}.${child.value || child.key}`,
          })),
        });
      }
    } else {
      treeNodes.push({
        title: getDisplayTitle(key, fieldSchema),
        key: key,
        value: key,
        isLeaf: true,
      });
    }
  });

  return treeNodes;
};
