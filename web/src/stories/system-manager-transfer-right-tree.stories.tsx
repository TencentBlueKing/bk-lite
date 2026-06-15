import type { Meta, StoryObj } from '@storybook/nextjs';
import { expect, fn, userEvent, within } from 'storybook/test';
import TransferRightTree from '@/app/system-manager/components/user/TransferRightTree';
import { filterTreeData } from '@/app/system-manager/utils/roleTreeUtils';
import {
  groupTreeData,
  roleTreeData,
  mockT,
  noop,
  inheritedRoleIds,
  inheritedRoleSourceMap,
  organizationRoleIds,
  organizationRoleSourceMap,
  personalRoleIds,
} from './system-manager-user-org.fixtures';

const meta = {
  title: 'System Manager/User Org/TransferRightTree',
  component: TransferRightTree,
  parameters: { layout: 'padded' },
} satisfies Meta<typeof TransferRightTree>;

export default meta;
type Story = StoryObj<typeof meta>;

export const GroupMode: Story = {
  args: {
    treeData: groupTreeData,
    filteredRightData: groupTreeData,
    selectedKeys: [11, 12],
    personalRoleIds: [],
    organizationRoleIds: [],
    organizationRoleSourceMap: {},
    inheritedRoleIds: [],
    inheritedRoleSourceMap: {},
    rightSearchValue: '',
    rightExpandedKeys: [1, 2],
    disabled: false,
    loading: false,
    mode: 'group',
    forceOrganizationRole: false,
    t: mockT,
    onSearchChange: noop,
    onExpandedKeysChange: noop,
    onChange: noop,
    onPermissionSetting: noop,
  },
};

const roleSelectedKeys = ['monitor.view', 'monitor.edit', 'cmdb.view'];
const roleFilteredRightData = filterTreeData(
  roleTreeData,
  [...new Map([...roleSelectedKeys, ...inheritedRoleIds].map(key => [String(key), key])).values()]
);

export const RoleMode: Story = {
  args: {
    ...GroupMode.args,
    treeData: roleTreeData,
    selectedKeys: roleSelectedKeys,
    personalRoleIds,
    organizationRoleIds,
    organizationRoleSourceMap,
    inheritedRoleIds,
    inheritedRoleSourceMap,
    mode: 'role',
    forceOrganizationRole: false,
    rightExpandedKeys: ['app-monitor', 'app-cmdb'],
    filteredRightData: roleFilteredRightData,
    onChange: fn(),
  },
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    const getTreeNode = (label: string) => canvas.getByText(label).closest('.ant-tree-treenode');

    const inheritedRow = getTreeNode('View Dashboard');
    const organizationRow = getTreeNode('View Topology');
    const personalRow = getTreeNode('Edit Dashboard');

    await expect(inheritedRow).toBeTruthy();
    await expect(within(inheritedRow as HTMLElement).getByText('system.role.inheritedRole')).toBeInTheDocument();
    await expect(within(inheritedRow as HTMLElement).queryByText('system.role.organizationRole')).toBeNull();
    await expect(within(inheritedRow as HTMLElement).queryByText('system.role.personalRole')).toBeNull();
    await expect(inheritedRow?.querySelector('.anticon-delete')).toBeNull();

    await expect(organizationRow).toBeTruthy();
    await expect(within(organizationRow as HTMLElement).getByText('system.role.organizationRole')).toBeInTheDocument();
    await expect(within(organizationRow as HTMLElement).queryByText('system.role.inheritedRole')).toBeNull();
    await expect(within(organizationRow as HTMLElement).queryByText('system.role.personalRole')).toBeNull();
    await expect(organizationRow?.querySelector('.anticon-delete')).toBeNull();

    await expect(personalRow).toBeTruthy();
    await expect(within(personalRow as HTMLElement).getByText('system.role.personalRole')).toBeInTheDocument();
    await expect(within(personalRow as HTMLElement).queryByText('system.role.inheritedRole')).toBeNull();
    await expect(within(personalRow as HTMLElement).queryByText('system.role.organizationRole')).toBeNull();

    const deleteButton = personalRow?.querySelector('.anticon-delete');
    await expect(deleteButton).not.toBeNull();

    await userEvent.click(deleteButton as HTMLElement);
    await expect(args.onChange).toHaveBeenCalledWith([]);
  },
};
