import React from 'react';
import type { DataNode as TreeDataNode } from 'antd/lib/tree';

export interface FlattenedRole {
  key: number;
  title: string;
}

export function flattenRoleData(nodes: TreeDataNode[]): FlattenedRole[] {
  return nodes?.reduce<FlattenedRole[]>((acc, node) => {
    if (node.selectable) {
      acc.push({ key: node.key as number, title: node.title as string });
    }
    if (node.children) {
      acc = acc.concat(flattenRoleData(node.children));
    }
    return acc;
  }, []);
}

export function filterTreeData(nodes: TreeDataNode[], selectedKeys: number[]): TreeDataNode[] {
  return nodes.reduce<TreeDataNode[]>((acc, node) => {
    const newNode = { ...node };
    if (node.children) {
      const filtered = filterTreeData(node.children, selectedKeys);
      if (filtered.length > 0) {
        newNode.children = filtered;
        acc.push(newNode);
      } else if (selectedKeys.includes(node.key as number)) {
        acc.push(newNode);
      }
    } else if (selectedKeys.includes(node.key as number)) {
      acc.push(newNode);
    }
    return acc;
  }, []);
}

export function getSubtreeKeys(node: TreeDataNode): number[] {
  const keys = [node.key as number];
  if (node.children && node.children.length > 0) {
    node.children.forEach(child => {
      keys.push(...getSubtreeKeys(child));
    });
  }
  return keys;
}

export function getDeletableSubtreeKeys(node: TreeDataNode, organizationRoleIds: number[]): number[] {
  const keys: number[] = [];

  if (!organizationRoleIds.includes(node.key as number)) {
    keys.push(node.key as number);
  }

  if (node.children && node.children.length > 0) {
    node.children.forEach(child => {
      keys.push(...getDeletableSubtreeKeys(child, organizationRoleIds));
    });
  }

  return keys;
}

export function cleanSelectedKeys(
  selected: number[],
  nodes: TreeDataNode[]
): number[] {
  let result = [...selected];
  nodes.forEach(node => {
    if (!node.selectable && node.children) {
      const childSelectable = flattenRoleData(node.children).map(item => Number(item.key));
      if (result.includes(node.key as number)) {
        if (!childSelectable.every(childKey => result.includes(childKey))) {
          result = result.filter(key => key !== node.key);
        }
      }
      result = cleanSelectedKeys(result, node.children);
    }
  });
  return result;
}

export function isFullySelected(node: TreeDataNode, selectedKeys: number[]): boolean {
  if (node.children && node.children.length > 0) {
    return node.children.every(child => isFullySelected(child, selectedKeys));
  }
  return selectedKeys.includes(node.key as number);
}

export function getAllKeys(nodes: TreeDataNode[]): number[] {
  return nodes.reduce<number[]>((acc, node) => {
    acc.push(node.key as number);
    if (node.children) {
      acc.push(...getAllKeys(node.children));
    }
    return acc;
  }, []);
}

export function isNodeDisabled(node: TreeDataNode): boolean {
  return node.disabled === true;
}

export function extractTextFromTitle(title: React.ReactNode | ((data: TreeDataNode) => React.ReactNode)): string {
  if (typeof title === 'function') {
    return '';
  }
  if (typeof title === 'string') {
    return title;
  }
  if (typeof title === 'number') {
    return String(title);
  }
  if (React.isValidElement(title)) {
    const props = title.props as Record<string, unknown>;
    if (props && props.children) {
      if (typeof props.children === 'string') {
        return props.children;
      }
      if (typeof props.children === 'number') {
        return String(props.children);
      }
      if (Array.isArray(props.children)) {
        return (props.children as unknown[])
          .map((child) => {
            if (typeof child === 'string' || typeof child === 'number') {
              return String(child);
            }
            if (React.isValidElement(child)) {
              return extractTextFromTitle(child);
            }
            return '';
          })
          .filter(Boolean)
          .join('');
      }
    }
  }
  return '';
}

export function filterTreeNode(node: TreeDataNode, searchValue: string): TreeDataNode | null {
  const nodeTitle = extractTextFromTitle(node.title);
  const match = nodeTitle.toLowerCase().includes(searchValue.toLowerCase());

  if (node.children && node.children.length > 0) {
    const filteredChildren = node.children
      .map(child => filterTreeNode(child, searchValue))
      .filter(Boolean) as TreeDataNode[];

    if (match || filteredChildren.length > 0) {
      return { ...node, children: filteredChildren };
    }
  }

  return match ? node : null;
}

export function getSearchExpandedKeys(nodes: TreeDataNode[], searchValue: string): React.Key[] {
  const keys: React.Key[] = [];

  const traverse = (node: TreeDataNode) => {
    if (node.children && node.children.length > 0) {
      const nodeTitle = extractTextFromTitle(node.title);
      const hasMatchInChildren = node.children.some(child => {
        const childTitle = extractTextFromTitle(child.title);
        return childTitle.toLowerCase().includes(searchValue.toLowerCase());
      });

      if (hasMatchInChildren || nodeTitle.toLowerCase().includes(searchValue.toLowerCase())) {
        keys.push(node.key);
      }

      node.children.forEach(traverse);
    }
  };

  nodes.forEach(traverse);
  return keys;
}

export function processLeftTreeData(nodes: TreeDataNode[], organizationRoleIds: number[]): TreeDataNode[] {
  return nodes.map(node => ({
    ...node,
    disabled: node.disabled || organizationRoleIds.includes(node.key as number),
    children: node.children ? processLeftTreeData(node.children, organizationRoleIds) : undefined
  }));
}

export function getAllLeafNodes(nodes: TreeDataNode[]): FlattenedRole[] {
  return nodes.reduce<FlattenedRole[]>((acc, node) => {
    if (!node.children || node.children.length === 0) {
      acc.push({ key: node.key as number, title: node.title as string });
    } else {
      acc = acc.concat(getAllLeafNodes(node.children));
    }
    return acc;
  }, []);
}
