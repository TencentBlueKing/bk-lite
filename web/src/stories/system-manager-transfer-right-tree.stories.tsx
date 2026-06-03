import type { Meta, StoryObj } from '@storybook/nextjs';
import { expect, fn, userEvent, within } from 'storybook/test';
import TransferRightTree from '@/app/system-manager/components/user/TransferRightTree';
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

export const RoleMode: Story = {
  args: {
    ...GroupMode.args,
    treeData: roleTreeData,
    filteredRightData: roleTreeData,
    selectedKeys: ['monitor.view', 'monitor.edit', 'cmdb.view'],
    personalRoleIds,
    organizationRoleIds,
    organizationRoleSourceMap,
    inheritedRoleIds,
    inheritedRoleSourceMap,
    mode: 'role',
    forceOrganizationRole: false,
    rightExpandedKeys: ['app-monitor', 'app-cmdb'],
    onChange: fn(),
  },
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);

    await expect(canvas.getByText('system.role.inheritedRole')).toBeInTheDocument();
    await expect(canvas.getByText('system.role.organizationRole')).toBeInTheDocument();
    await expect(canvas.getByText('system.role.personalRole')).toBeInTheDocument();

    const deleteButton = canvasElement.querySelector('.anticon-delete');
    await expect(deleteButton).not.toBeNull();

    await userEvent.click(deleteButton as HTMLElement);
    await expect(args.onChange).toHaveBeenCalledWith([]);
  },
};
