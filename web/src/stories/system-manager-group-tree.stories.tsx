import type { Meta, StoryObj } from '@storybook/nextjs';
import GroupTree from '@/app/system-manager/components/user/GroupTree';
import { groupTreeData, mockT, noop } from './system-manager-user-org.fixtures';

const searchTreeData = [
  {
    ...groupTreeData[0],
    children: groupTreeData[0].children?.filter((node) => node.title === 'Frontend Team'),
  },
];

const meta = {
  title: 'System Manager/User Org/GroupTree',
  component: GroupTree,
  parameters: { layout: 'padded' },
} satisfies Meta<typeof GroupTree>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    treeData: groupTreeData,
    searchValue: '',
    onSearchChange: noop,
    onAddRootGroup: noop,
    onTreeSelect: noop,
    onGroupAction: noop,
    t: mockT,
    loading: false,
  },
};

export const Loading: Story = {
  args: {
    ...Default.args,
    loading: true,
  },
};

export const SearchState: Story = {
  args: {
    ...Default.args,
    searchValue: 'Front',
    treeData: searchTreeData,
  },
};
