import type { Meta, StoryObj } from '@storybook/nextjs';
import { expect, within } from 'storybook/test';
import PermissionModal from '@/app/system-manager/components/user/permissionModal';
import {
  permissionNode,
  permissionRules,
} from './system-manager-user-org-modal.fixtures';

const meta = {
  title: 'System Manager/User Org/PermissionModal',
  component: PermissionModal,
  parameters: { layout: 'centered' },
} satisfies Meta<typeof PermissionModal>;

export default meta;
type Story = StoryObj<typeof meta>;

const baseArgs = {
  visible: true,
  node: permissionNode,
  rules: {},
  onOk: async () => {},
  onCancel: () => {},
};

export const Default: Story = {
  args: baseArgs,
};

export const PrefilledRules: Story = {
  args: {
    ...baseArgs,
    rules: permissionRules,
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);

    await expect(canvas.getByText('system.permission.app')).toBeInTheDocument();
    await expect(canvas.getByText('system.permission.dataPermission')).toBeInTheDocument();
    await expect(canvas.getByText('Dashboard Admin')).toBeInTheDocument();
    await expect(canvas.getByText('Topology Readonly')).toBeInTheDocument();
  },
};

export const LoadingRules: Story = {
  args: {
    ...baseArgs,
    node: {
      ...permissionNode,
      key: 99,
      title: 'Loading Team',
    },
  },
};
