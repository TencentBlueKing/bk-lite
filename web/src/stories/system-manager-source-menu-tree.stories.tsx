import type { Meta, StoryObj } from '@storybook/nextjs';
import SourceMenuTree from '@/app/system-manager/components/application/menu/sourceTree';
import type { SourceMenuNode } from '@/app/system-manager/types/menu';

const sourceMenus: SourceMenuNode[] = [
  {
    name: 'monitor',
    display_name: 'Monitor',
    url: '/monitor',
    icon: 'jiankong',
    type: 'menu',
    children: [
      {
        name: 'dashboard',
        display_name: 'Dashboard',
        url: '/monitor/dashboard',
        icon: 'dashboard',
        type: 'page',
      },
      {
        name: 'alert-policy',
        display_name: 'Alert Policy',
        url: '/monitor/alarm/policy',
        icon: 'gaojing',
        type: 'page',
      },
    ],
  },
  {
    name: 'cmdb-detail',
    display_name: 'Asset Detail',
    url: '/cmdb/asset/detail',
    icon: 'ziyuan',
    type: 'page',
    isDetailMode: true,
  },
];

const meta = {
  title: 'System Manager/Application Menu/SourceMenuTree',
  component: SourceMenuTree,
  decorators: [
    (Story) => (
      <div style={{ width: 340, minHeight: 360, padding: 16, background: 'var(--color-fill-1)' }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof SourceMenuTree>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    sourceMenus,
    selectedKeys: ['dashboard'],
    loading: false,
    onCheck: () => {},
  },
};

export const Loading: Story = {
  args: {
    ...Default.args,
    loading: true,
  },
};

export const Disabled: Story = {
  args: {
    ...Default.args,
    disabled: true,
  },
};
