import type { DataNode as TreeDataNode } from 'antd/lib/tree';
import type { DataItem, DataPermission, PermissionRuleItem } from '@/app/system-manager/types/permission';
import type { SystemSettings } from '@/app/system-manager/types/security';

export const permissionNode: TreeDataNode = {
  key: 11,
  title: 'Backend Team',
};

export const permissionRules = {
  monitor: 2,
  cmdb: 3,
};

export const groupDataRuleResponse: Array<DataPermission & { app: string }> = [
  { id: '1', name: 'Dashboard Readonly', app: 'monitor', view: true, operate: false },
  { id: '2', name: 'Dashboard Admin', app: 'monitor', view: true, operate: true },
  { id: '3', name: 'Topology Readonly', app: 'cmdb', view: true, operate: false },
];

export const groupRuleResponse = groupDataRuleResponse;

export const groupDataRulePageResponse: { count: number; items: DataItem[] } = {
  count: 2,
  items: [
    {
      id: 'rule-1',
      name: 'Backend data rules',
      description: 'Monitor permissions for the backend organization',
      group_id: '11',
      group_name: 'Backend Team',
      rules: {
        monitor: [
          { id: '1', name: 'Dashboard Readonly', permission: ['View'] },
          { id: '2', name: 'Dashboard Admin', permission: ['View', 'Operate'] },
        ] satisfies PermissionRuleItem[],
      },
    },
    {
      id: 'rule-2',
      name: 'Frontend data rules',
      description: 'CMDB permissions for the frontend organization',
      group_id: '12',
      group_name: 'Frontend Team',
      rules: {
        cmdb: [
          { id: '3', name: 'Topology Readonly', permission: ['View'] },
        ],
      },
    },
  ],
};

export const passwordSettings: SystemSettings = {
  enable_otp: '1',
  login_expired_time: '12',
  pwd_set_validity_period: '90',
  pwd_set_required_char_types: 'uppercase,lowercase,digit',
  pwd_set_min_length: '10',
  pwd_set_max_length: '20',
  pwd_set_max_retry_count: '5',
  pwd_set_lock_duration: '30',
  pwd_set_expiry_reminder_days: '7',
};

export const groupRoleTree: TreeDataNode[] = [
  {
    key: 101,
    title: 'Monitor',
    children: [
      { key: 1001, title: 'View Dashboard' },
      { key: 1002, title: 'Edit Dashboard' },
    ],
  },
  {
    key: 102,
    title: 'CMDB',
    children: [
      { key: 2001, title: 'View Topology' },
      { key: 2002, title: 'Edit Model' },
    ],
  },
];

export interface RoleTreeResponseNode {
  id: number;
  name: string;
  is_build_in: boolean;
  children: Array<{
    id: number;
    name: string;
  }>;
}

const toRoleTreeResponseNode = (node: TreeDataNode): RoleTreeResponseNode => ({
  id: Number(node.key),
  name: String(node.title),
  is_build_in: Number(node.key) === 101,
  children: (node.children || []).map((child) => ({
    id: Number(child.key),
    name: String(child.title),
  })),
});

export const roleTreeResponse: RoleTreeResponseNode[] = groupRoleTree.map(toRoleTreeResponseNode);

export interface GroupDetailWithRoles {
  group_id: number;
  group_name: string;
  allow_inherit_roles: boolean;
  own_role_ids: number[];
  inherited_role_ids: number[];
  inherited_role_source: string;
  inherited_role_source_map: Record<string, string>;
}

export const groupDetailWithRoles: GroupDetailWithRoles = {
  group_id: 11,
  group_name: 'Backend Team',
  allow_inherit_roles: true,
  own_role_ids: [1002],
  inherited_role_ids: [2001],
  inherited_role_source: 'Default',
  inherited_role_source_map: {
    '2001': 'Default / Frontend Team',
  },
};

let roleListLoadingArmed = false;

export const armRoleListLoadingMock = () => {
  roleListLoadingArmed = true;
};

export const resetRoleListLoadingMock = () => {
  roleListLoadingArmed = false;
};

export const consumeRoleListLoadingMock = () => {
  const shouldDelay = roleListLoadingArmed;
  roleListLoadingArmed = false;
  return shouldDelay;
};
