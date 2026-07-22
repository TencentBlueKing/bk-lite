import type { Meta, StoryObj } from '@storybook/nextjs';
import React from 'react';
import { expect, fn, userEvent, within } from 'storybook/test';
import SectionHeader from '@/components/section-header';
import RoleTransfer from '@/app/system-manager/components/system-manager-role-transfer';
import PermissionModal from '@/app/system-manager/components/system-manager-role-transfer/permissionModal';
import TransferLeftTree from '@/app/system-manager/components/system-manager-role-transfer/transferLeftTree';
import TransferRightTree from '@/app/system-manager/components/system-manager-role-transfer/transferRightTree';
import TransferTreePanel from '@/app/system-manager/components/system-manager-transfer-tree-panel';
import { groupTreeData } from './system-manager-user-org.fixtures';
import {
  groupRuleResponse,
  permissionNode,
  permissionRules,
} from './system-manager-user-org-modal.fixtures';
import {
  inheritedRoleIds,
  inheritedRoleSourceMap,
  mockT,
  noop,
  organizationRoleIds,
  organizationRoleSourceMap,
  personalRoleIds,
  roleTransferFilteredRightData,
  roleTransferSelectedKeys,
  roleTreeData,
} from './system-manager-user-org.fixtures';

const FamilyOverview = () => {
  return (
    <div className="space-y-6">
      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader spacing="flush" title="RoleTransfer composed shell" titleClassName="text-sm font-semibold" />
        <div style={{ width: 960 }}>
          <RoleTransfer
            treeData={roleTreeData}
            personalRoleIds={personalRoleIds}
            organizationRoleIds={organizationRoleIds}
            selectedKeys={roleTransferSelectedKeys}
            organizationRoleSourceMap={organizationRoleSourceMap}
            inheritedRoleIds={inheritedRoleIds}
            inheritedRoleSourceMap={inheritedRoleSourceMap}
            onChange={noop}
          />
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-2">
        <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
          <SectionHeader spacing="flush" title="TransferLeftTree selection surface" titleClassName="text-sm font-semibold" />
          <TransferLeftTree
            treeData={roleTreeData}
            selectedKeys={roleTransferSelectedKeys}
            personalRoleIds={personalRoleIds}
            organizationRoleIds={organizationRoleIds}
            leftSearchValue=""
            leftExpandedKeys={['app-monitor', 'app-cmdb']}
            disabled={false}
            loading={false}
            mode="role"
            enableSubGroupSelect={false}
            t={mockT}
            onSearchChange={noop}
            onExpandedKeysChange={noop}
            onChange={noop}
            onSubGroupToggle={noop}
          />
        </section>

        <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
          <SectionHeader spacing="flush" title="TransferRightTree assigned-role surface" titleClassName="text-sm font-semibold" />
          <TransferRightTree
            treeData={roleTreeData}
            filteredRightData={roleTransferFilteredRightData}
            selectedKeys={roleTransferSelectedKeys}
            personalRoleIds={personalRoleIds}
            organizationRoleIds={organizationRoleIds}
            organizationRoleSourceMap={organizationRoleSourceMap}
            inheritedRoleIds={inheritedRoleIds}
            inheritedRoleSourceMap={inheritedRoleSourceMap}
            rightSearchValue=""
            rightExpandedKeys={['app-monitor', 'app-cmdb']}
            disabled={false}
            loading={false}
            mode="role"
            forceOrganizationRole={false}
            t={mockT}
            onSearchChange={noop}
            onExpandedKeysChange={noop}
            onChange={noop}
            onPermissionSetting={noop}
          />
        </section>
      </div>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="TransferTreePanel search scaffold"
          titleClassName="text-sm font-semibold"
        />
        <div className="grid gap-4 xl:grid-cols-2">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <TransferTreePanel
              searchPlaceholder="Search assignable roles"
              searchValue=""
              onSearchChange={noop}
            >
              <div className="space-y-2 text-sm text-[var(--color-text-2)]">
                <div className="rounded-md bg-[var(--color-bg-1)] px-3 py-2">Monitor Viewer</div>
                <div className="rounded-md bg-[var(--color-bg-1)] px-3 py-2">CMDB Editor</div>
                <div className="rounded-md bg-[var(--color-bg-1)] px-3 py-2">Job Operator</div>
              </div>
            </TransferTreePanel>
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <TransferTreePanel
              searchPlaceholder="Search assigned roles"
              searchValue="monitor"
              onSearchChange={noop}
              maxHeight={180}
            >
              <div className="space-y-2 text-sm text-[var(--color-text-2)]">
                <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg-1)] px-3 py-2">
                  Monitor Admin
                </div>
                <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg-1)] px-3 py-2">
                  Monitor Viewer
                </div>
              </div>
            </TransferTreePanel>
          </div>
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader spacing="flush" title="PermissionModal rule-editing contract" titleClassName="text-sm font-semibold" />
        <PermissionModal
          visible={true}
          node={permissionNode}
          rules={permissionRules}
          onOk={async () => undefined}
          onCancel={() => undefined}
          clientModules={['monitor', 'cmdb']}
          fetchGroupDataRule={async () => groupRuleResponse}
        />
      </section>
    </div>
  );
};

const meta = {
  title: 'Business/SystemManager/RoleTransfer/FamilyOverview',
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

// RightTreeRoleSemantics 通过 args + play 校验 TransferRightTree 的 onChange 触发路径,
// 需要在 args 上携带 onChange; FamilyOverview 自身不接收任何 props, 所以单独声明交互式 Story 类型.
type InteractiveStory = StoryObj<{ onChange?: (keys: React.Key[]) => void }>;

export const Overview: Story = {};

export const RoleTransferInteractive: Story = {
  render: () => {
    const [personalSelectedRoleIds, setPersonalSelectedRoleIds] = React.useState<React.Key[]>(
      roleTransferSelectedKeys.filter((key) => !organizationRoleIds.includes(String(key))),
    );
    const selectedKeys = [...personalSelectedRoleIds, ...organizationRoleIds];

    return (
      <div style={{ width: 960 }}>
        <RoleTransfer
          treeData={roleTreeData}
          personalRoleIds={personalSelectedRoleIds}
          organizationRoleIds={organizationRoleIds}
          selectedKeys={selectedKeys}
          organizationRoleSourceMap={organizationRoleSourceMap}
          inheritedRoleIds={inheritedRoleIds}
          inheritedRoleSourceMap={inheritedRoleSourceMap}
          onChange={setPersonalSelectedRoleIds}
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

export const GroupTransferMode: Story = {
  render: () => {
    const [selectedKeys, setSelectedKeys] = React.useState<React.Key[]>([11]);

    return (
      <div style={{ width: 960 }}>
        <RoleTransfer
          treeData={groupTreeData}
          selectedKeys={selectedKeys}
          mode="group"
          enableSubGroupSelect
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

    const rightRow = within(rightList).getByText('Backend Team').closest('.ant-tree-treenode') as HTMLElement;
    const rightDelete = rightRow.querySelector('.anticon-delete') as HTMLElement;
    await userEvent.click(rightDelete);
    await expect(within(rightList).queryByText('Backend Team')).toBeNull();
  },
};

export const LoadingState: Story = {
  render: () => {
    const [personalSelectedRoleIds, setPersonalSelectedRoleIds] = React.useState<React.Key[]>(
      roleTransferSelectedKeys.filter((key) => !organizationRoleIds.includes(String(key))),
    );
    const selectedKeys = [...personalSelectedRoleIds, ...organizationRoleIds];

    return (
      <div style={{ width: 960 }}>
        <RoleTransfer
          treeData={roleTreeData}
          personalRoleIds={personalSelectedRoleIds}
          organizationRoleIds={organizationRoleIds}
          selectedKeys={selectedKeys}
          organizationRoleSourceMap={organizationRoleSourceMap}
          inheritedRoleIds={inheritedRoleIds}
          inheritedRoleSourceMap={inheritedRoleSourceMap}
          loading
          onChange={setPersonalSelectedRoleIds}
        />
      </div>
    );
  },
};

export const LeftTreeModes: Story = {
  render: () => (
    <div className="grid gap-6 xl:grid-cols-2">
      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader spacing="flush" title="Group mode" titleClassName="text-sm font-semibold" />
        <TransferLeftTree
          treeData={groupTreeData}
          selectedKeys={[11]}
          personalRoleIds={[]}
          organizationRoleIds={[]}
          leftSearchValue=""
          leftExpandedKeys={[1, 2]}
          disabled={false}
          loading={false}
          mode="group"
          enableSubGroupSelect
          t={mockT}
          onSearchChange={noop}
          onExpandedKeysChange={noop}
          onChange={noop}
          onSubGroupToggle={noop}
        />
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader spacing="flush" title="Role mode" titleClassName="text-sm font-semibold" />
        <TransferLeftTree
          treeData={roleTreeData}
          selectedKeys={[]}
          personalRoleIds={personalRoleIds}
          organizationRoleIds={organizationRoleIds}
          leftSearchValue=""
          leftExpandedKeys={['app-monitor', 'app-cmdb']}
          disabled={false}
          loading={false}
          mode="role"
          enableSubGroupSelect={false}
          t={mockT}
          onSearchChange={noop}
          onExpandedKeysChange={noop}
          onChange={noop}
          onSubGroupToggle={noop}
        />
      </section>
    </div>
  ),
};

export const RightTreeRoleSemantics: InteractiveStory = {
  args: {
    onChange: fn(),
  },
  render: ({ onChange }) => (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
      <TransferRightTree
        treeData={roleTreeData}
        filteredRightData={roleTransferFilteredRightData}
        selectedKeys={roleTransferSelectedKeys}
        personalRoleIds={personalRoleIds}
        organizationRoleIds={organizationRoleIds}
        organizationRoleSourceMap={organizationRoleSourceMap}
        inheritedRoleIds={inheritedRoleIds}
        inheritedRoleSourceMap={inheritedRoleSourceMap}
        rightSearchValue=""
        rightExpandedKeys={['app-monitor', 'app-cmdb']}
        disabled={false}
        loading={false}
        mode="role"
        forceOrganizationRole={false}
        t={mockT}
        onSearchChange={noop}
        onExpandedKeysChange={noop}
        onChange={onChange}
        onPermissionSetting={noop}
      />
    </div>
  ),
  play: async ({ canvasElement, args }) => {
    const canvas = within(canvasElement);
    const getTreeNode = (label: string) => canvas.getByText(label).closest('.ant-tree-treenode');

    const inheritedRow = getTreeNode('View Dashboard');
    const organizationRow = getTreeNode('View Topology');
    const personalRow = getTreeNode('Edit Dashboard');

    await expect(inheritedRow).toBeTruthy();
    await expect(within(inheritedRow as HTMLElement).getByText('system.role.inheritedRole')).toBeInTheDocument();
    await expect(within(inheritedRow as HTMLElement).queryByText('system.role.organizationRole')).toBeNull();
    await expect(within(inheritedRow as HTMLElement).queryByText('system.role.personalRole')).toBeNull();
    await expect(inheritedRow?.querySelector('.anticon-delete')).toBeNull();

    await expect(organizationRow).toBeTruthy();
    await expect(within(organizationRow as HTMLElement).getByText('system.role.organizationRole')).toBeInTheDocument();
    await expect(within(organizationRow as HTMLElement).queryByText('system.role.inheritedRole')).toBeNull();
    await expect(within(organizationRow as HTMLElement).queryByText('system.role.personalRole')).toBeNull();
    await expect(organizationRow?.querySelector('.anticon-delete')).toBeNull();

    await expect(personalRow).toBeTruthy();
    await expect(within(personalRow as HTMLElement).getByText('system.role.personalRole')).toBeInTheDocument();
    await expect(within(personalRow as HTMLElement).queryByText('system.role.inheritedRole')).toBeNull();
    await expect(within(personalRow as HTMLElement).queryByText('system.role.organizationRole')).toBeNull();

    const deleteButton = personalRow?.querySelector('.anticon-delete');
    await expect(deleteButton).not.toBeNull();

    await userEvent.click(deleteButton as HTMLElement);
    await expect(args.onChange).toHaveBeenCalledWith([]);
  },
};

export const PermissionModalPrefilledRules: Story = {
  render: () => (
    <PermissionModal
      visible={true}
      node={permissionNode}
      rules={permissionRules}
      onOk={async () => undefined}
      onCancel={() => undefined}
      clientModules={['monitor', 'cmdb']}
      fetchGroupDataRule={async () => groupRuleResponse}
    />
  ),
  play: async () => {
    const modal = within(document.body);

    await expect(await modal.findByText('system.permission.app')).toBeInTheDocument();
    await expect(await modal.findByText('system.permission.dataPermission')).toBeInTheDocument();
    await expect(await modal.findByText('Dashboard Admin')).toBeInTheDocument();
    await expect(await modal.findByText('Topology Readonly')).toBeInTheDocument();
  },
};

export const PermissionModalLoadingRules: Story = {
  render: () => (
    <PermissionModal
      visible={true}
      node={{
        ...permissionNode,
        key: 'loading-rules',
        title: 'Loading Team',
      }}
      rules={{}}
      onOk={async () => undefined}
      onCancel={() => undefined}
      clientModules={['monitor', 'cmdb']}
      fetchGroupDataRule={async () => {
        await new Promise((resolve) => {
          setTimeout(resolve, 1200);
        });
        return groupRuleResponse;
      }}
    />
  ),
  play: async () => {
    const modal = within(document.body);

    await expect(modal.getByText('Loading Team')).toBeInTheDocument();
    expect(document.body.querySelector('.ant-spin-spinning')).not.toBeNull();

    await expect(await modal.findByText('system.permission.app')).toBeInTheDocument();
    await expect(await modal.findByText('system.permission.dataPermission')).toBeInTheDocument();
  },
};
