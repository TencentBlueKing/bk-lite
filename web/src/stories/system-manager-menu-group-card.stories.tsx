import type { Meta, StoryObj } from '@storybook/nextjs';
import MenuGroupCard from '@/app/system-manager/components/application/menu/groupCard';
import type { FunctionMenuItem } from '@/app/system-manager/types/menu';

const pages: FunctionMenuItem[] = [
  {
    name: 'dashboard-overview',
    display_name: 'Dashboard Overview',
    originName: 'Overview',
    url: '/monitor/dashboard/overview',
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
];

const baseArgs = {
  group: {
    id: 'monitoring',
    name: 'Monitoring',
    children: pages,
  },
  isEditing: false,
  onDragStart: () => {},
  onDragEnd: () => {},
  onRename: () => {},
  onEdit: () => {},
  onDelete: () => {},
  onCancelEdit: () => {},
  onDropToGroup: () => {},
  onRemovePage: () => {},
  onRenamePage: () => {},
  onPageDragStart: () => {},
  onPageDragOver: () => {},
  onPageDrop: () => {},
};

const meta = {
  title: 'System Manager/Application Menu/MenuGroupCard',
  component: MenuGroupCard,
  decorators: [
    (Story) => (
      <div style={{ width: 520, padding: 16, background: 'var(--color-bg)' }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof MenuGroupCard>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: baseArgs,
};

export const EditingGroup: Story = {
  args: {
    ...baseArgs,
    isEditing: true,
  },
};

export const EmptyGroup: Story = {
  args: {
    ...baseArgs,
    group: {
      id: 'empty',
      name: 'Empty Group',
      children: [],
    },
  },
};

export const DragTarget: Story = {
  args: {
    ...baseArgs,
    isDragging: true,
    dragOverPageIndex: 1,
  },
};
