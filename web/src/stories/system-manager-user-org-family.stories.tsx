import type { Meta, StoryObj } from '@storybook/nextjs';
import type { PasswordPolicyConfig } from '@/components/security/password-policy/usePasswordPolicy';
import React, { useRef, type ComponentType, type ReactNode } from 'react';
import { Button } from 'antd';
import { expect, userEvent, within } from 'storybook/test';
import SectionHeader from '@/components/section-header';
import GroupEditModal, { type GroupModalRef } from '@/components/system-manager-group-edit-modal';
import GroupTree from '@/components/system-manager-group-tree';
import PasswordModal, { type PasswordModalRef } from '@/components/system-manager-user-password-modal';
import { ClientProvider } from '@/context/client';
import { groupTreeData, mockT, noop } from './system-manager-user-org.fixtures';
import {
  fetchStoryGroupDetailWithRolesAction,
  fetchStoryRoleListAction,
  fetchStorySystemSettings,
  storybookLoadingClientData,
} from './system-manager-user-org-modal.fixtures';

const StorybookClientProvider = ClientProvider as ComponentType<{
  children: ReactNode;
  clientData?: typeof storybookLoadingClientData;
}>;

const searchTreeData = [
  {
    ...groupTreeData[0],
    children: groupTreeData[0].children?.filter((node) => node.title === 'Frontend Team'),
  },
];

interface GroupEditModalAutoOpenProps {
  groupId: string | number;
  groupName: string;
  fetchRoleListAction?: typeof fetchStoryRoleListAction;
}

const GroupEditModalAutoOpen = ({
  groupId,
  groupName,
  fetchRoleListAction = fetchStoryRoleListAction,
}: GroupEditModalAutoOpenProps) => {
  const ref = useRef<GroupModalRef>(null);

  React.useEffect(() => {
    ref.current?.showModal({
      type: 'edit',
      groupId,
      groupName,
    });
  }, [groupId, groupName]);

  return (
    <StorybookClientProvider clientData={storybookLoadingClientData}>
      <GroupEditModal
        ref={ref}
        onSuccess={() => undefined}
        clientData={storybookLoadingClientData}
        fetchRoleListAction={fetchRoleListAction}
        fetchGroupDetailWithRolesAction={fetchStoryGroupDetailWithRolesAction}
        updateGroupAction={async () => ({ success: true })}
      />
    </StorybookClientProvider>
  );
};

const PasswordModalAutoOpen = () => {
  const ref = useRef<PasswordModalRef>(null);

  React.useEffect(() => {
    ref.current?.showModal({ userId: 'demo-user' });
  }, []);

  return (
    <PasswordModal
      ref={ref}
      onSuccess={() => undefined}
      fetchSystemSettings={fetchStorySystemSettings as unknown as () => Promise<PasswordPolicyConfig>}
      setUserPasswordAction={async () => ({ success: true })}
    />
  );
};

const FamilyOverview = () => {
  const groupModalRef = useRef<GroupModalRef>(null);
  const passwordModalRef = useRef<PasswordModalRef>(null);

  return (
    <StorybookClientProvider clientData={storybookLoadingClientData}>
      <div className="space-y-6">
        <div className="grid gap-6 xl:grid-cols-[320px_minmax(0,1fr)]">
          <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
            <SectionHeader spacing="flush" title="GroupTree entry surface" titleClassName="text-sm font-semibold" />
            <div className="h-[420px]">
              <GroupTree
                treeData={groupTreeData}
                searchValue=""
                onSearchChange={noop}
                onAddRootGroup={noop}
                onTreeSelect={noop}
                onGroupAction={noop}
                t={mockT}
                loading={false}
              />
            </div>
          </section>

          <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
            <SectionHeader
              spacing="flush"
              title="UserOrg action shells"
              titleClassName="text-sm font-semibold"
              description="Open the shared modal contracts used by the user and group management flow."
            />

            <div className="grid gap-4 md:grid-cols-2">
              <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
                <div className="space-y-2">
                  <SectionHeader
                    spacing="flush"
                    title="GroupEditModal"
                    titleClassName="text-sm font-semibold"
                    description="Includes the shared RoleTransfer family for organization-role editing."
                  />
                  <Button
                    type="primary"
                    onClick={() => {
                      groupModalRef.current?.showModal({
                        type: 'edit',
                        groupId: 11,
                        groupName: 'Backend Team',
                      });
                    }}
                  >
                    Open group edit modal
                  </Button>
                </div>
              </div>

              <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
                <div className="space-y-2">
                  <SectionHeader
                    spacing="flush"
                    title="PasswordModal"
                    titleClassName="text-sm font-semibold"
                    description="Reuses the shared security password workflow inside the user-admin surface."
                  />
                  <Button
                    onClick={() => {
                      passwordModalRef.current?.showModal({ userId: 'demo-user' });
                    }}
                  >
                    Open password modal
                  </Button>
                </div>
              </div>
            </div>

            <div className="rounded-lg border border-dashed border-[var(--color-border)] bg-[var(--color-bg-2)] p-4 text-sm text-[var(--color-text-2)]">
              This family keeps group navigation, group editing, role assignment, and credential reset in one governed business flow. Role assignment details continue to live in the dedicated
              {' '}
              <span className="font-medium text-[var(--color-text-1)]">
                Business/SystemManager/RoleTransfer/FamilyOverview
              </span>
              {' '}
              contract.
            </div>
          </section>
        </div>

        <GroupEditModal
          ref={groupModalRef}
          onSuccess={() => undefined}
          clientData={storybookLoadingClientData}
          fetchRoleListAction={fetchStoryRoleListAction}
          fetchGroupDetailWithRolesAction={fetchStoryGroupDetailWithRolesAction}
          updateGroupAction={async () => ({ success: true })}
        />

        <PasswordModal
          ref={passwordModalRef}
          onSuccess={() => undefined}
          fetchSystemSettings={fetchStorySystemSettings as unknown as () => Promise<PasswordPolicyConfig>}
          setUserPasswordAction={async () => ({ success: true })}
        />
      </div>
    </StorybookClientProvider>
  );
};

const meta = {
  title: 'Business/SystemManager/UserOrg/FamilyOverview',
  component: FamilyOverview,
  decorators: [
    (Story) => (
      <div style={{ maxWidth: 1160, padding: 24, background: 'var(--color-bg-2)' }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof FamilyOverview>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Overview: Story = {};

export const GroupTreeStates: Story = {
  render: () => (
    <div className="grid gap-6 xl:grid-cols-3">
      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader spacing="flush" title="Default" titleClassName="text-sm font-semibold" />
        <div className="h-[420px]">
          <GroupTree
            treeData={groupTreeData}
            searchValue=""
            onSearchChange={noop}
            onAddRootGroup={noop}
            onTreeSelect={noop}
            onGroupAction={noop}
            t={mockT}
            loading={false}
          />
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader spacing="flush" title="Loading" titleClassName="text-sm font-semibold" />
        <div className="h-[420px]">
          <GroupTree
            treeData={groupTreeData}
            searchValue=""
            onSearchChange={noop}
            onAddRootGroup={noop}
            onTreeSelect={noop}
            onGroupAction={noop}
            t={mockT}
            loading
          />
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader spacing="flush" title="Search state" titleClassName="text-sm font-semibold" />
        <div className="h-[420px]">
          <GroupTree
            treeData={searchTreeData}
            searchValue="Front"
            onSearchChange={noop}
            onAddRootGroup={noop}
            onTreeSelect={noop}
            onGroupAction={noop}
            t={mockT}
            loading={false}
          />
        </div>
      </section>
    </div>
  ),
};

export const GroupEditModalDefault: Story = {
  render: () => <GroupEditModalAutoOpen groupId={12} groupName="Frontend Team" />,
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

export const GroupEditModalWithInheritedRoles: Story = {
  render: () => <GroupEditModalAutoOpen groupId={11} groupName="Backend Team" />,
  play: async () => {
    const dialog = await within(document.body).findByRole('dialog', {
      name: 'system.group.editGroup',
    });
    const modal = within(dialog);

    await expect(await modal.findByDisplayValue('Backend Team')).toBeInTheDocument();
    await expect(await modal.findByText('system.group.allowInheritRoles')).toBeInTheDocument();
    await expect(await modal.findByRole('switch')).toBeChecked();
    await expect(await modal.findByText('View Topology')).toBeInTheDocument();
    await expect(await modal.findByText('system.role.inheritedRole')).toBeInTheDocument();
  },
};

export const GroupEditModalLoadingRoleTransfer: Story = {
  render: () => (
    <GroupEditModalAutoOpen
      groupId={11}
      groupName="Backend Team"
      fetchRoleListAction={async () => {
        await new Promise((resolve) => {
          setTimeout(resolve, 1200);
        });
        return fetchStoryRoleListAction();
      }}
    />
  ),
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

export const PasswordResetDefault: Story = {
  render: () => <PasswordModalAutoOpen />,
  play: async () => {
    const modal = within(document.body);

    await expect(await modal.findByText('system.user.passwordTitle')).toBeInTheDocument();
    await expect(
      await modal.findByText('system.security.passwordLengthRange: 10-20')
    ).toBeInTheDocument();
    await expect(
      await modal.findByText(
        'system.security.passwordComplexity: system.security.requireUppercase、system.security.requireLowercase、system.security.requireDigit'
      )
    ).toBeInTheDocument();
  },
};

export const PasswordResetValidationHint: Story = {
  render: () => <PasswordModalAutoOpen />,
  play: async () => {
    const modal = within(document.body);
    const dialog = await modal.findByRole('dialog');

    await expect(await modal.findByText('system.user.passwordTitle')).toBeInTheDocument();

    const passwordInput = await within(dialog).findByLabelText('system.user.form.password', {
      selector: 'input',
    });

    await userEvent.type(passwordInput, 'Abc1234567');

    await expect(await modal.findByText('system.user.passwordValidation')).toBeInTheDocument();
    await expect(await modal.findByText('system.security.requireUppercase')).toBeInTheDocument();
  },
};
