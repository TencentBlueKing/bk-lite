import type { Meta, StoryObj } from '@storybook/nextjs';
import type { DataNode as TreeDataNode } from 'antd/lib/tree';
import TransferLeftTree from '@/app/system-manager/components/user/TransferLeftTree';
import {
  groupTreeData,
  roleTreeData,
  mockT,
  noop,
  personalRoleIds,
  organizationRoleIds,
} from './system-manager-user-org.fixtures';

const meta = {
  title: 'System Manager/User Org/TransferLeftTree',
  component: TransferLeftTree,
  parameters: { layout: 'padded' },
} satisfies Meta<typeof TransferLeftTree>;

export default meta;
type Story = StoryObj<typeof meta>;

export const GroupMode: Story = {
  args: {
    treeData: groupTreeData,
    selectedKeys: [11],
    personalRoleIds: [],
    organizationRoleIds: [],
    leftSearchValue: '',
    leftExpandedKeys: [1, 2],
    disabled: false,
    loading: false,
    mode: 'group',
    enableSubGroupSelect: true,
    t: mockT,
    onSearchChange: noop,
    onExpandedKeysChange: noop,
    onChange: noop,
    onSubGroupToggle: noop,
  },
};

export const RoleMode: Story = {
  args: {
    ...GroupMode.args,
    treeData: roleTreeData,
    selectedKeys: [],
    personalRoleIds,
    organizationRoleIds,
    leftExpandedKeys: ['app-monitor', 'app-cmdb'],
    mode: 'role',
    enableSubGroupSelect: false,
  },
};

export const RoleModeDisplayNameMissing: Story = {
  // 应用层节点没有 display_name 时，应 fallback 到原 title（即 client_id）
  args: {
    ...RoleMode.args,
    treeData: roleTreeData.map<TreeDataNode>((node) =>
      'display_name' in node
        ? { key: node.key, title: node.title, children: node.children }
        : node,
    ),
  },
};
