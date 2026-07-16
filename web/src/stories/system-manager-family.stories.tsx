import { useState } from 'react';
import type { Meta, StoryObj } from '@storybook/nextjs';
import { Button, Input, Select } from 'antd';
import FilterToolbar from '@/components/filter-toolbar';
import DetailListDrawerShell from '@/components/detail-list-drawer-shell';
import SectionHeader from '@/components/section-header';
import MenuGroupCard from '@/app/system-manager/components/system-manager-application-menu/group-card';
import SourceMenuTree from '@/app/system-manager/components/system-manager-application-menu/source-menu-tree';
import GroupTree from '@/app/system-manager/components/system-manager-group-tree';
import SystemManagerRoleAssignmentTabShell from '@/app/system-manager/components/system-manager-role-assignment-tab-shell';
import RoleTransfer from '@/app/system-manager/components/system-manager-role-transfer';
import UserProfilePasswordModal from '@/app/(core)/components/top-menu/user-info/passwordModal';
import UserInformation from '@/app/(core)/components/top-menu/user-info/userInformation';
import VersionModal from '@/app/(core)/components/top-menu/user-info/versionModal';
import TimeSelector from '@/components/time-selector';
import ReactDiffViewer from 'react-diff-viewer-continued';
import {
  systemManagerGroupPages,
  systemManagerSourceMenus,
} from './system-manager-application-menu.fixtures';
import {
  groupTreeData,
  mockT,
  noop,
  organizationRoleIds,
  organizationRoleSourceMap,
  personalRoleIds,
  roleTransferSelectedKeys,
  roleTreeData,
} from './system-manager-user-org.fixtures';
import {
  renderSystemManagerVersionContent,
  systemManagerStorybookPasswordPolicy,
  systemManagerStorybookUserInfo,
  systemManagerVersionContentMap,
} from './system-manager-user-profile.fixtures';

const FamilyOverview = () => {
  const [userInformationOpen, setUserInformationOpen] = useState(false);
  const [passwordModalOpen, setPasswordModalOpen] = useState(false);
  const [versionModalOpen, setVersionModalOpen] = useState(false);

  return (
    <div className="space-y-6">
      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Security and audit workspace"
          titleClassName="text-sm font-semibold"
          description="Shared audit filtering keeps operation logs, login logs, and error logs aligned around one stable control surface."
        />

        <FilterToolbar>
          <Input.Search allowClear className="w-48" placeholder="Operator" />
          <Select
            allowClear
            className="w-48"
            options={[
              { label: 'System Manager', value: 'system-manager' },
              { label: 'OpsPilot', value: 'opspilot' },
            ]}
            placeholder="Operation module"
          />
          <TimeSelector
            clearable
            defaultValue={{
              selectValue: 7 * 24 * 60,
              rangePickerVaule: null,
            }}
            onlyTimeSelect
            showTime
          />
          <Button type="primary">Search</Button>
          <Button>Reset</Button>
        </FilterToolbar>

        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
          <SectionHeader
            className="mb-3"
            title="Operation log detail drawer"
            titleClassName="text-sm font-semibold"
            description="Audit detail uses one governed drawer shell for metadata and optional before/after diffs."
          />

          <div className="space-y-4">
            <div style={{ height: 620 }}>
              <DetailListDrawerShell
                title="Operation Detail"
                width={720}
                open
                onClose={() => undefined}
                destroyOnClose
                labelWidthClassName="w-32"
                items={[
                  {
                    key: 'target_type',
                    label: 'Target Type',
                    value: 'Policy',
                    copyable: false,
                  },
                  {
                    key: 'target_id',
                    label: 'Target ID',
                    value: 'policy-42',
                    copyable: false,
                  },
                  {
                    key: 'scenario',
                    label: 'Scenario',
                    value: 'Manual update',
                    copyable: false,
                  },
                  {
                    key: 'operator_object',
                    label: 'Operator Object',
                    value: 'Security policy',
                    copyable: false,
                  },
                ]}
              >
                <div>
                  <div className="mb-2 font-medium">Before / After</div>
                  <ReactDiffViewer
                    oldValue={JSON.stringify(
                      {
                        retention_days: 30,
                        notify_on_delete: false,
                      },
                      null,
                      2,
                    )}
                    newValue={JSON.stringify(
                      {
                        retention_days: 90,
                        notify_on_delete: true,
                      },
                      null,
                      2,
                    )}
                    splitView
                  />
                </div>
              </DetailListDrawerShell>
            </div>

            <div style={{ height: 420 }}>
              <DetailListDrawerShell
                title="Operation Detail"
                width={720}
                open
                onClose={() => undefined}
                destroyOnClose
                labelWidthClassName="w-32"
                items={[
                  {
                    key: 'target_type',
                    label: 'Target Type',
                    value: 'User',
                    copyable: false,
                  },
                  {
                    key: 'target_id',
                    label: 'Target ID',
                    value: 'user-17',
                    copyable: false,
                  },
                  {
                    key: 'scenario',
                    label: 'Scenario',
                    value: 'Password reset',
                    copyable: false,
                  },
                ]}
              />
            </div>
          </div>
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-2">
        <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
          <SectionHeader
            spacing="flush"
            title="Application menu governance"
            titleClassName="text-sm font-semibold"
            description="Shared menu-management surfaces define source selection and destination grouping for application navigation setup."
          />

          <div className="grid gap-4 lg:grid-cols-[220px_minmax(0,1fr)]">
            <SourceMenuTree
              sourceMenus={[systemManagerSourceMenus[0]]}
              selectedKeys={['dashboard']}
              loading={false}
              onCheck={noop}
            />

            <MenuGroupCard
              group={{
                id: 'monitoring',
                name: 'Monitoring',
                children: systemManagerGroupPages,
              }}
              isEditing={false}
              onDragStart={noop}
              onDragEnd={noop}
              onRename={noop}
              onEdit={noop}
              onDelete={noop}
              onCancelEdit={noop}
              onDropToGroup={noop}
              onRemovePage={noop}
              onRenamePage={noop}
              onPageDragStart={noop}
              onPageDragOver={noop}
              onPageDrop={noop}
            />
          </div>
        </section>

        <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
          <SectionHeader
            spacing="flush"
            title="User organization and role assignment"
            titleClassName="text-sm font-semibold"
            description="Shared tree navigation and role-transfer surfaces power organization editing, user structure, and permission assignment flows."
          />

          <div className="grid gap-4">
            <div className="h-[320px] rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
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

            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
              <RoleTransfer
                treeData={roleTreeData}
                personalRoleIds={personalRoleIds}
                organizationRoleIds={organizationRoleIds}
                selectedKeys={roleTransferSelectedKeys}
                organizationRoleSourceMap={organizationRoleSourceMap}
                inheritedRoleIds={[]}
                inheritedRoleSourceMap={{}}
                onChange={noop}
              />
            </div>
          </div>
        </section>
      </div>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="User profile self-service"
          titleClassName="text-sm font-semibold"
          description="Shared account-management surfaces now form a governed `UserProfile` subtree for profile editing, password reset, and version-history browsing."
        />

        <div className="grid gap-4 md:grid-cols-3">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <div className="space-y-2">
              <SectionHeader
                spacing="flush"
                title="InformationDrawer"
                titleClassName="text-sm font-semibold"
                description="Editable account profile fields with locale and timezone preferences."
              />
              <Button type="primary" onClick={() => setUserInformationOpen(true)}>
                Open information drawer
              </Button>
            </div>
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <div className="space-y-2">
              <SectionHeader
                spacing="flush"
                title="PasswordModal"
                titleClassName="text-sm font-semibold"
                description="Self-service password reset built on the shared security password contract."
              />
              <Button onClick={() => setPasswordModalOpen(true)}>
                Open password modal
              </Button>
            </div>
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <div className="space-y-2">
              <SectionHeader
                spacing="flush"
                title="VersionModal"
                titleClassName="text-sm font-semibold"
                description="Product release notes rendered as a tabbed markdown browser."
              />
              <Button onClick={() => setVersionModalOpen(true)}>
                Open version modal
              </Button>
            </div>
          </div>
        </div>

        <UserInformation
          visible={userInformationOpen}
          onClose={() => setUserInformationOpen(false)}
          fetchUserInfoAction={async () => systemManagerStorybookUserInfo}
          updateUserBaseInfoAction={async () => undefined}
        />

        <UserProfilePasswordModal
          visible={passwordModalOpen}
          onCancel={() => setPasswordModalOpen(false)}
          onSuccess={() => setPasswordModalOpen(false)}
          fetchPolicyAction={async () => systemManagerStorybookPasswordPolicy}
          resetPasswordAction={async () => undefined}
        />

        <VersionModal
          visible={versionModalOpen}
          onClose={() => setVersionModalOpen(false)}
          fetchVersionFilesAction={async () => Object.keys(systemManagerVersionContentMap)}
          renderVersionContent={renderSystemManagerVersionContent}
        />
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Role assignment tab shell"
          titleClassName="text-sm font-semibold"
          description="Shared assignment tabs cover user and organization selection with the same table, selection, and add-modal shell."
        />

        <div className="grid gap-4 xl:grid-cols-2">
          <SystemManagerRoleAssignmentTabShell
            loading={false}
            selectedKeys={['1', '2']}
            addPermission="Add user"
            removePermission="Remove user"
            searchPlaceholder="Search"
            addLabel="+Add"
            batchDeleteLabel="Batch delete"
            modalTitle="Add user"
            confirmText="Confirm"
            cancelText="Cancel"
            modalOpen={true}
            modalLoading={false}
            columns={[
              { title: 'Username', dataIndex: 'username', key: 'username' },
              { title: 'Display name', dataIndex: 'display_name', key: 'display_name' },
            ]}
            dataSource={[
              { id: 1, username: 'alice', display_name: 'Alice' },
              { id: 2, username: 'bob', display_name: 'Bob' },
            ]}
            rowKey={(record: { id: number }) => record.id}
            pagination={{
              current: 1,
              pageSize: 10,
              total: 2,
              onChange: () => undefined,
            }}
            onSearch={() => undefined}
            onOpenAddModal={() => undefined}
            onBatchDelete={() => undefined}
            onSelectionChange={() => undefined}
            onConfirmModal={() => undefined}
            onCancelModal={() => undefined}
            modalContent={(
              <Select
                mode="multiple"
                options={[
                  { label: 'Alice (alice)', value: 1 },
                  { label: 'Bob (bob)', value: 2 },
                ]}
              />
            )}
          />

          <SystemManagerRoleAssignmentTabShell
            loading={false}
            selectedKeys={['1', '2']}
            addPermission="Add group"
            removePermission="Remove group"
            searchPlaceholder="Search"
            addLabel="+Add"
            batchDeleteLabel="Batch delete"
            modalTitle="Add organization"
            confirmText="Confirm"
            cancelText="Cancel"
            modalOpen={true}
            modalLoading={false}
            columns={[
              { title: 'Organization', dataIndex: 'name', key: 'name' },
            ]}
            dataSource={[
              { id: 1, name: 'Ops Team' },
              { id: 2, name: 'Platform Team' },
            ]}
            rowKey={(record: { id: number }) => record.id}
            pagination={{
              current: 1,
              pageSize: 10,
              total: 2,
              onChange: () => undefined,
            }}
            onSearch={() => undefined}
            onOpenAddModal={() => undefined}
            onBatchDelete={() => undefined}
            onSelectionChange={() => undefined}
            onConfirmModal={() => undefined}
            onCancelModal={() => undefined}
            modalContent={(
              <div className="space-y-4">
                <div className="rounded-md border border-blue-200 bg-blue-50 p-3 text-sm text-blue-800">
                  Add one or more organizations to the current role.
                </div>
                <Select
                  mode="multiple"
                  options={[
                    { label: 'Ops Team', value: 1 },
                    { label: 'Platform Team', value: 2 },
                  ]}
                />
              </div>
            )}
          />
        </div>
      </section>
    </div>
  );
};

const meta = {
  title: 'Business/SystemManager/FamilyOverview',
  component: FamilyOverview,
  decorators: [
    (Story) => (
      <div style={{ maxWidth: 1200, padding: 24, background: 'var(--color-bg-2)' }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof FamilyOverview>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Overview: Story = {};
