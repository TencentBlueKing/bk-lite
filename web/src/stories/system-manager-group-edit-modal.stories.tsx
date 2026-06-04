import type { Meta, StoryObj } from '@storybook/nextjs';
import { useEffect, useRef, type ComponentType, type ReactNode } from 'react';
import { expect, within } from 'storybook/test';
import GroupEditModal, { GroupModalRef } from '@/app/system-manager/components/group/GroupEditModal';
import { ClientProvider } from '@/context/client';
import {
  groupDetailWithRoles,
  roleTreeResponse,
  storybookLoadingClientData,
} from './system-manager-user-org-modal.fixtures';

interface GroupEditModalStoryProps {
  groupId: string | number;
  groupName: string;
  fetchRoleListAction?: () => Promise<typeof roleTreeResponse>;
}

const GroupEditModalStory = ({
  groupId,
  groupName,
  fetchRoleListAction,
}: GroupEditModalStoryProps) => {
  const ref = useRef<GroupModalRef>(null);

  useEffect(() => {
    ref.current?.showModal({
      type: 'edit',
      groupId,
      groupName,
    });
  }, [groupId, groupName]);

  return (
    <GroupEditModal
      ref={ref}
      onSuccess={() => {}}
      clientDataOverride={storybookLoadingClientData}
      fetchRoleListAction={fetchRoleListAction ?? (async () => roleTreeResponse)}
      fetchGroupDetailWithRolesAction={async ({ group_id }) => {
        if (String(group_id) === '12') {
          return {
            allow_inherit_roles: false,
            own_role_ids: [2001],
            inherited_role_ids: [],
            inherited_role_source_map: {},
          };
        }

        return groupDetailWithRoles;
      }}
      updateGroupAction={async () => ({ success: true })}
    />
  );
};

const StorybookClientProvider = ClientProvider as ComponentType<{
  children: ReactNode;
  clientData?: typeof storybookLoadingClientData;
}>;

const LoadingRoleTransferStory = (args: GroupEditModalStoryProps) => (
  <StorybookClientProvider clientData={storybookLoadingClientData}>
    <GroupEditModalStory
      {...args}
      fetchRoleListAction={async () => {
        await new Promise((resolve) => {
          setTimeout(resolve, 1200);
        });
        return roleTreeResponse;
      }}
    />
  </StorybookClientProvider>
);

const meta = {
  title: 'System Manager/User Org/GroupEditModal',
  component: GroupEditModalStory,
  parameters: { layout: 'centered' },
} satisfies Meta<typeof GroupEditModalStory>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    groupId: 12,
    groupName: 'Frontend Team',
  },
  play: async () => {
    const dialog = await within(document.body).findByRole('dialog', {
      name: 'system.group.editGroup',
    });
    const modal = within(dialog);

    await expect(await modal.findByText('system.group.form.name')).toBeInTheDocument();
    await expect(await modal.findByDisplayValue('Frontend Team')).toBeInTheDocument();
    await expect(await modal.findByText('system.group.allowInheritRoles')).toBeInTheDocument();
    await expect(await modal.findByText('View Topology')).toBeInTheDocument();
    expect(modal.queryByText('system.role.inheritedRole')).toBeNull();
  },
};

export const WithInheritedRoles: Story = {
  args: {
    groupId: 11,
    groupName: 'Backend Team',
  },
  play: async () => {
    const dialog = await within(document.body).findByRole('dialog', {
      name: 'system.group.editGroup',
    });
    const modal = within(dialog);

    await expect(await modal.findByDisplayValue('Backend Team')).toBeInTheDocument();
    await expect(await modal.findByText('system.group.allowInheritRoles')).toBeInTheDocument();
    await expect(await modal.findByText('View Topology')).toBeInTheDocument();
    await expect(await modal.findByText('system.role.inheritedRole')).toBeInTheDocument();
  },
};

export const LoadingRoleTransfer: Story = {
  args: {
    groupId: 11,
    groupName: 'Backend Team',
  },
  render: (args) => <LoadingRoleTransferStory {...args} />,
  play: async () => {
    const dialog = await within(document.body).findByRole('dialog', {
      name: 'system.group.editGroup',
    });
    const modal = within(dialog);

    await expect(await modal.findByText('system.group.form.name')).toBeInTheDocument();
    await expect(await modal.findByDisplayValue('Backend Team')).toBeInTheDocument();
    await expect(await modal.findByText('system.group.allowInheritRoles')).toBeInTheDocument();
    await expect(await modal.findByRole('switch')).toBeChecked();
    expect(dialog.querySelector('.ant-spin-spinning')).not.toBeNull();

    await expect(await modal.findByText('View Topology')).toBeInTheDocument();
    await expect(await modal.findByText('system.role.inheritedRole')).toBeInTheDocument();
  },
};
