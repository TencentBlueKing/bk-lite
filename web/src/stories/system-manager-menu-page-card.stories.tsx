import type { Meta, StoryObj } from '@storybook/nextjs';
import MenuPageCard from '@/app/system-manager/components/application/menu/pageCard';
import type { FunctionMenuItem } from '@/app/system-manager/types/menu';

const page: FunctionMenuItem = {
  name: 'dashboard-overview',
  display_name: 'Dashboard Overview',
  originName: 'Overview',
  url: '/monitor/dashboard/overview',
  icon: 'dashboard',
  type: 'page',
};

const meta = {
  title: 'System Manager/Application Menu/MenuPageCard',
  component: MenuPageCard,
  decorators: [
    (Story) => (
      <div style={{ width: 420, padding: 16, background: 'var(--color-bg)' }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof MenuPageCard>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    page,
    onDragStart: () => {},
    onDragEnd: () => {},
    onRemove: () => {},
    onRename: () => {},
  },
};

export const WithoutIcon: Story = {
  args: {
    ...Default.args,
    page: {
      ...page,
      icon: undefined,
      display_name: 'Alert Policy',
      originName: undefined,
      url: '/monitor/alarm/policy',
    },
  },
};
