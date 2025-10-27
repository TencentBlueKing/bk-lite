/**
 * 组织树工具函数
 * 提供树形数据处理的通用方法
 */

export interface TreeNode {
  key: number;
  value?: number;
  title: string;
  children?: TreeNode[];
  [key: string]: any;
}

/**
 * 获取节点的所有子节点ID（递归获取）
 * @param node 目标节点
 * @param includeParent 是否包含父节点自身
 * @returns 所有子节点ID数组
 */
export function getAllChildrenIds(
  node: TreeNode,
  includeParent: boolean = false
): number[] {
  const result: number[] = [];

  if (includeParent) {
    result.push(node.key);
  }

  const traverse = (currentNode: TreeNode) => {
    if (currentNode.children && currentNode.children.length > 0) {
      currentNode.children.forEach((child) => {
        result.push(child.key);
        traverse(child);
      });
    }
  };

  traverse(node);
  return result;
}

/**
 * 根据ID查找节点
 * @param treeData 树形数据
 * @param nodeId 目标节点ID
 * @returns 找到的节点或null
 */
export function findNodeById(
  treeData: TreeNode[],
  nodeId: number
): TreeNode | null {
  for (const node of treeData) {
    if (node.key === nodeId) {
      return node;
    }
    if (node.children && node.children.length > 0) {
      const found = findNodeById(node.children, nodeId);
      if (found) {
        return found;
      }
    }
  }
  return null;
}

/**
 * 获取节点的父级链路
 * @param treeData 树形数据
 * @param nodeId 目标节点ID
 * @returns 从根到目标节点的父级ID数组
 */
export function getParentChain(
  treeData: TreeNode[],
  nodeId: number
): number[] {
  const chain: number[] = [];

  const findChain = (nodes: TreeNode[], targetId: number, path: number[]): boolean => {
    for (const node of nodes) {
      const currentPath = [...path, node.key];
      
      if (node.key === targetId) {
        chain.push(...currentPath.slice(0, -1)); // 不包含自身
        return true;
      }
      
      if (node.children && node.children.length > 0) {
        if (findChain(node.children, targetId, currentPath)) {
          return true;
        }
      }
    }
    return false;
  };

  findChain(treeData, nodeId, []);
  return chain;
}

/**
 * 判断节点是否全选（所有子节点都被选中）
 * @param node 目标节点
 * @param selectedIds 已选中的ID数组
 * @returns 是否全选
 */
export function isFullySelected(
  node: TreeNode,
  selectedIds: number[]
): boolean {
  if (!node.children || node.children.length === 0) {
    return selectedIds.includes(node.key);
  }

  return node.children.every((child) => isFullySelected(child, selectedIds));
}

/**
 * 判断节点是否有已选子节点
 * @param node 目标节点
 * @param selectedIds 已选中的ID数组
 * @returns 是否有已选子节点
 */
export function hasSelectedChildren(
  node: TreeNode,
  selectedIds: number[]
): boolean {
  if (!node.children || node.children.length === 0) {
    return false;
  }

  const allChildrenIds = getAllChildrenIds(node, false);
  return allChildrenIds.some((id) => selectedIds.includes(id));
}

/**
 * 获取树的所有叶子节点ID
 * @param treeData 树形数据
 * @returns 所有叶子节点ID数组
 */
export function getAllLeafNodeIds(treeData: TreeNode[]): number[] {
  const leafIds: number[] = [];

  const traverse = (nodes: TreeNode[]) => {
    nodes.forEach((node) => {
      if (!node.children || node.children.length === 0) {
        leafIds.push(node.key);
      } else {
        traverse(node.children);
      }
    });
  };

  traverse(treeData);
  return leafIds;
}

/**
 * 判断节点是否为叶子节点
 * @param node 目标节点
 * @returns 是否为叶子节点
 */
export function isLeafNode(node: TreeNode): boolean {
  return !node.children || node.children.length === 0;
}

/**
 * 获取树中所有节点的ID
 * @param treeData 树形数据
 * @returns 所有节点ID数组
 */
export function getAllNodeIds(treeData: TreeNode[]): number[] {
  const ids: number[] = [];

  const traverse = (nodes: TreeNode[]) => {
    nodes.forEach((node) => {
      ids.push(node.key);
      if (node.children && node.children.length > 0) {
        traverse(node.children);
      }
    });
  };

  traverse(treeData);
  return ids;
}

/**
 * 检查一个节点是否是另一个节点的祖先
 * @param treeData 树形数据
 * @param ancestorId 祖先节点ID
 * @param descendantId 后代节点ID
 * @returns 是否为祖先关系
 */
export function isAncestor(
  treeData: TreeNode[],
  ancestorId: number,
  descendantId: number
): boolean {
  const ancestorNode = findNodeById(treeData, ancestorId);
  if (!ancestorNode) {
    return false;
  }

  const allChildrenIds = getAllChildrenIds(ancestorNode, false);
  return allChildrenIds.includes(descendantId);
}
