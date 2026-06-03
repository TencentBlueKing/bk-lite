import type { Meta, StoryObj } from '@storybook/nextjs';
import React, { useState } from 'react';
import { expect, userEvent, within } from 'storybook/test';
import RoleTransfer from '@/app/system-manager/components/user/roleTransfer';
import {
  groupTreeData,
  inheritedRoleIds,
  inheritedRoleSourceMap,
  noop,
  organizationRoleIds,
  organizationRoleSourceMap,
  personalRoleIds,
  roleTreeData,
} from './system-manager-user-org.fixtures';

const meta = {
  title: 'System Manager/User Org/RoleTransfer',
  component: RoleTransfer,
  parameters: { layout: 'padded' },
} satisfies Meta<typeof RoleTransfer>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    treeData: roleTreeData,
    selectedKeys: ['monitor.view', 'monitor.edit', 'cmdb.view'],
    personalRoleIds,
    organizationRoleIds,
    organizationRoleSourceMap,
    inheritedRoleIds,
    inheritedRoleSourceMap,
    onChange: noop,
  },
  render: (args) => {
    const [selectedKeys, setSelectedKeys] = useState<React.Key[]>(args.selectedKeys);

    return (
      <div style={{ width: 960 }}>
        <RoleTransfer
          {...args}
          selectedKeys={selectedKeys}
          onChange={setSelectedKeys}
        />
      </div>
    );
  },
  play: async ({ canvasElement }) => {
    const lists = canvasElement.querySelectorAll('.ant-transfer-list');
    await expect(lists).toHaveLength(2);

    const leftList = lists[0] as HTMLElement;
    const rightList = lists[1] as HTMLElement;

    const rightRow = within(rightList).getByText('Edit Dashboard').closest('.ant-tree-treenode') as HTMLElement;
    const rightDelete = rightRow.querySelector('.anticon-delete') as HTMLElement;
    await userEvent.click(rightDelete);
    await expect(within(rightList).queryByText('Edit Dashboard')).toBeNull();

    const leftRow = within(leftList).getByText('Edit Dashboard').closest('.ant-tree-treenode') as HTMLElement;
    const leftCheckbox = leftRow.querySelector('.ant-checkbox') as HTMLElement;
    await userEvent.click(leftCheckbox);
    await expect(within(rightList).getByText('Edit Dashboard')).toBeInTheDocument();
  },
};

export const GroupMode: Story = {
  args: {
    treeData: groupTreeData,
    selectedKeys: [11],
    mode: 'group',
    enableSubGroupSelect: true,
    onChange: noop,
  },
  render: (args) => {
    const [selectedKeys, setSelectedKeys] = useState<React.Key[]>(args.selectedKeys);

    return (
      <div style={{ width: 960 }}>
        <RoleTransfer
          {...args}
          selectedKeys={selectedKeys}
          onChange={setSelectedKeys}
        />
      </div>
    );
  },
  play: async ({ canvasElement }) => {
    const lists = canvasElement.querySelectorAll('.ant-transfer-list');
    await expect(lists).toHaveLength(2);

    const leftList = lists[0] as HTMLElement;
    const rightList = lists[1] as HTMLElement;

    const leftRow = within(leftList).getByText('Backend Team').closest('.ant-tree-treenode') as HTMLElement;
    const leftCheckbox = leftRow.querySelector('.ant-checkbox') as HTMLElement;
    await userEvent.click(leftCheckbox);
    await expect(within(rightList).queryByText('Backend Team')).toBeNull();

    await userEvent.click(leftCheckbox);
    await expect(within(rightList).getByText('Backend Team')).toBeInTheDocument();
  },
};

export const Loading: Story = {
  args: {
    treeData: roleTreeData,
    selectedKeys: [],
    personalRoleIds,
    organizationRoleIds,
    organizationRoleSourceMap,
    inheritedRoleIds,
    inheritedRoleSourceMap,
    loading: true,
    onChange: noop,
  },
  render: (args) => (
    <div style={{ width: 960 }}>
      <RoleTransfer {...args} />
    </div>
  ),
};
