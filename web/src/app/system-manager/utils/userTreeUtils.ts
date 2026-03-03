/**
 * User Tree Utilities
 * Pure functions for tree traversal and filtering in user structure page
 */

import type { DataNode as TreeDataNode } from 'antd/lib/tree';
import type { OriginalGroup } from '@/app/system-manager/types/group';

export interface ExtendedTreeDataNode extends TreeDataNode {
  hasAuth?: boolean;
  isVirtual?: boolean;
  roleIds?: number[];
  children?: ExtendedTreeDataNode[];
}

/**
 * Convert API group response to tree data nodes
 */
export function convertGroupsToTreeData(groups: OriginalGroup[]): ExtendedTreeDataNode[] {
  return groups.map((group) => {
    const currentIsVirtual = group.is_virtual === true;
    return {
      key: group.id,
      title: group.name,
      hasAuth: group.hasAuth,
      isVirtual: currentIsVirtual,
      roleIds: group.role_ids || [],
      children: group.subGroups ? convertGroupsToTreeData(group.subGroups) : [],
    };
  });
}

/**
 * Check if a node with given key exists in the tree
 */
export function nodeExistsInTree(tree: ExtendedTreeDataNode[], key: React.Key): boolean {
  for (const node of tree) {
    if (node.key === key) return true;
    if (node.children && node.children.length > 0) {
      if (nodeExistsInTree(node.children, key)) return true;
    }
  }
  return false;
}

/**
 * Find a node by key in the tree
 */
export function findNodeByKey(tree: ExtendedTreeDataNode[], key: number): ExtendedTreeDataNode | undefined {
  for (const node of tree) {
    if (node.key === key) return node;
    if (node.children) {
      const found = findNodeByKey(node.children, key);
      if (found) return found;
    }
  }
  return undefined;
}

/**
 * Filter tree data by search query (recursive)
 */
export function filterTreeBySearch(data: ExtendedTreeDataNode[], searchQuery: string): ExtendedTreeDataNode[] {
  if (!searchQuery) return data;
  
  return data.reduce<ExtendedTreeDataNode[]>((acc, item) => {
    const children = item.children ? filterTreeBySearch(item.children, searchQuery) : [];
    if ((item.title as string).toLowerCase().includes(searchQuery.toLowerCase()) || children.length) {
      acc.push({ ...item, children });
    }
    return acc;
  }, []);
}

/**
 * Check if a node has children
 */
export function hasChildren(node: ExtendedTreeDataNode): boolean {
  return !!(node.children && node.children.length > 0);
}
