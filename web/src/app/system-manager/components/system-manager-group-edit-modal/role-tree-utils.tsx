import React from 'react';
import SourceOriginBadge from '@/components/source-origin-badge';
import type { DataNode as TreeDataNode } from 'antd/lib/tree';

export interface RoleTreeItem {
  id: number;
  name: string;
  is_build_in?: boolean;
  children: Array<{ id: number; name: string }>;
}

export function processRoleTreeData(
  roleData: RoleTreeItem[],
  externalAppLabel = 'External App'
): TreeDataNode[] {
  return roleData.map((item) => ({
    key: item.id,
    title: item.is_build_in === false
      ? React.createElement(
        'span',
        null,
        item.name,
        React.createElement(SourceOriginBadge, {
          kind: 'external',
          label: externalAppLabel,
          className: 'ml-1',
        })
      )
      : item.name,
    selectable: false,
    children: item.children.map((child) => ({
      key: child.id,
      title: child.name,
      selectable: true,
    })),
  }));
}
