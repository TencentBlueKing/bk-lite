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
  play: async () => {
    const modal = within(document.body);

    await expect(await modal.findByText('system.permission.app')).toBeInTheDocument();
    await expect(await modal.findByText('system.permission.dataPermission')).toBeInTheDocument();
    await expect(await modal.findByText('Dashboard Admin')).toBeInTheDocument();
    await expect(await modal.findByText('Topology Readonly')).toBeInTheDocument();
  },
};

export const LoadingRules: Story = {
  args: {
    ...baseArgs,
    node: {
      ...permissionNode,
      // Storybook-only sentinel: this key matches the delayed mock below so the loading UI can be asserted.
      key: 'loading-rules',
      title: 'Loading Team',
    },
  },
  play: async () => {
    const modal = within(document.body);

    await expect(modal.getByText('Loading Team')).toBeInTheDocument();
    expect(document.body.querySelector('.ant-spin-spinning')).not.toBeNull();

    await expect(await modal.findByText('system.permission.app')).toBeInTheDocument();
    await expect(await modal.findByText('system.permission.dataPermission')).toBeInTheDocument();
  },
};
