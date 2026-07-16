import type { DataNode as TreeDataNode } from 'antd/lib/tree';

export const mockT = (key: string) => key;
export const noop = () => {};

export interface ExtendedGroupTreeDataNode extends TreeDataNode {
  hasAuth?: boolean;
  isVirtual?: boolean;
  children?: ExtendedGroupTreeDataNode[];
}

export const groupTreeData: ExtendedGroupTreeDataNode[] = [
  {
    key: 1,
    title: 'Default',
    isVirtual: false,
    hasAuth: true,
    children: [
      { key: 11, title: 'Backend Team', hasAuth: true },
      { key: 12, title: 'Frontend Team', hasAuth: true },
    ],
  },
  {
    key: 2,
    title: 'Virtual Root',
    isVirtual: true,
    hasAuth: true,
    children: [
      { key: 21, title: 'Shared Ops', hasAuth: true },
      { key: 22, title: 'No Auth Team', hasAuth: false },
    ],
  },
];

export const roleTreeData: (TreeDataNode & { display_name?: string })[] = [
  {
    key: 'app-monitor',
    title: 'monitor',
    display_name: 'Monitor',
    children: [
      { key: 'monitor.view', title: 'View Dashboard' },
      { key: 'monitor.edit', title: 'Edit Dashboard' },
    ],
  },
  {
    key: 'app-cmdb',
    title: 'cmdb',
    display_name: 'CMDB',
    children: [
      { key: 'cmdb.view', title: 'View Topology' },
      { key: 'cmdb.edit', title: 'Edit Model' },
    ],
  },
];

export const inheritedRoleIds = ['monitor.view'];
export const organizationRoleIds = ['cmdb.view'];
export const personalRoleIds = ['monitor.edit'];

export const inheritedRoleSourceMap = {
  'monitor.view': 'Default / Backend Team',
};

export const organizationRoleSourceMap = {
  'cmdb.view': 'Frontend Team',
};

export const roleTransferSelectedKeys: React.Key[] = ['role-1', 'role-2'];

export const roleTransferFilteredRightData: { key: string; title: string }[] = [
  { key: 'role-1', title: 'Role One' },
  { key: 'role-2', title: 'Role Two' },
];
