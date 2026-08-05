import type { Meta, StoryObj } from '@storybook/nextjs';
import PermissionWrapper from '@/components/permission';

const meta: Meta<typeof PermissionWrapper> = {
  component: PermissionWrapper,
};

export default meta;

type Story = StoryObj<typeof PermissionWrapper>;


export const WithoutPermission: Story = {
  args: {
    requiredPermissions: ['view'],
    children: <div>Content without permission</div>,
  },
};