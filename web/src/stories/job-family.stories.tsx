import type { Meta, StoryObj } from '@storybook/nextjs';
import { Button, Segmented } from 'antd';
import CompactEmptyState from '@/components/compact-empty-state';
import JobDangerousRulePage from '@/components/job-dangerous-rule-page';
import JobDriverBadge from '@/components/job-driver-badge';
import JobHostSelectionModal from '@/components/job-host-selection-modal';
import JobFilePreviewModal from '@/app/job/components/file-preview-modal';
import JobListWorkspaceShell from '@/components/job-list-workspace-shell';
import JobPlaybookDetailDrawer from '@/components/job-playbook-detail-drawer';
import JobPlaybookUploadModal from '@/components/job-playbook-upload-modal';
import JobPlaybookUpgradeModal from '@/components/job-playbook-upgrade-modal';
import JobScriptEditor from '@/components/job-script-editor';
import JobScriptTypeBadge from '@/components/job-script-type-badge';
import PageFormHeaderCard from '@/components/page-form-header-card';
import SectionHeader from '@/components/section-header';
import {
  AddTargetHostButton,
  TargetSourceSelector,
} from '@/components/job-target-selection-controls';
import JobTriggerSourceBadge from '@/components/job-trigger-source-badge';
import JobTypeBadge from '@/components/job-type-badge';
import SearchCombinationToolbar from '@/components/search-combination-toolbar';
import WorkspacePanel from '@/components/workspace-panel';
import { Form } from 'antd';
import { jobPlaybookStoryT as t } from './job-playbook-modal.fixtures';

const targetSelectionHosts = [
  {
    key: '101',
    hostName: 'prod-gateway-01',
    ipAddress: '10.0.1.12',
    cloudRegion: 'Shanghai',
    osType: 'Linux',
    currentDriver: 'ansible',
  },
  {
    key: '102',
    hostName: 'prod-worker-08',
    ipAddress: '10.0.2.44',
    cloudRegion: 'Beijing',
    osType: 'Linux',
    currentDriver: 'sidecar',
  },
];

const nodeManagerHosts = targetSelectionHosts.map((host) => ({
  ...host,
  currentDriver: '-',
}));

const dangerousRuleFixtures = [
  {
    id: 1,
    name: 'Block root deletion',
    pattern: 'rm -rf /',
    level: 'forbidden',
    is_enabled: true,
    team: [1],
    description: 'Prevent destructive root cleanup commands.',
    created_at: '2026-06-25T08:00:00Z',
    updated_at: '2026-06-30T08:40:00Z',
  },
  {
    id: 2,
    name: 'Review service restart',
    pattern: 'systemctl restart .*',
    level: 'confirm',
    is_enabled: true,
    team: [1, 2],
    description: 'Require confirmation for production service restarts.',
    created_at: '2026-06-24T05:10:00Z',
    updated_at: '2026-06-29T12:15:00Z',
  },
];

const demoPlaybook = {
  id: 7,
  name: 'System cleanup',
  description: 'Collect logs, clear temp files, and verify disk pressure.',
  version: 'v2.3.1',
  readme:
    '## Runbook\n\n1. Collect diagnostics\n2. Rotate logs\n3. Verify service health',
  file_list: [
    {
      name: 'roles',
      type: 'directory' as const,
      children: [
        {
          name: 'cleanup',
          type: 'directory' as const,
          children: [
            { name: 'tasks.yml', type: 'file' as const },
            { name: 'vars.yml', type: 'file' as const },
          ],
        },
      ],
    },
    { name: 'inventory.ini', type: 'file' as const },
  ],
  params: [
    {
      name: 'target_path',
      default: '/var/log',
      description: 'Directory to clean up before archival.',
    },
    {
      name: 'retain_days',
      default: '7',
      description: 'How many days of files should stay on disk.',
    },
  ],
  file_name: 'system-cleanup.zip',
  file_key: 'playbooks/system-cleanup.zip',
  bucket_name: 'job-artifacts',
  file_size: 2048,
  entry_file: 'roles/cleanup/tasks.yml',
  timeout: 1800,
  team: [1],
  team_name: ['Ops'],
  is_preset: false,
  created_by: 'alice',
  created_at: '2026-06-28T02:14:00Z',
  updated_by: 'alice',
  updated_at: '2026-06-30T08:45:00Z',
};

const demoPreview = {
  file_name: 'cleanup/tasks/main.yml',
  file_path: '/playbooks/cleanup/tasks/main.yml',
  file_type: 'text/yaml',
  file_size: 842,
  content:
    '- name: Restart nginx\n  service:\n    name: nginx\n    state: restarted\n\n- name: Verify port\n  wait_for:\n    host: 127.0.0.1\n    port: 80\n    timeout: 10\n',
};

const FamilyOverview = () => {
  const [uploadForm] = Form.useForm();
  const [upgradeForm] = Form.useForm();

  return (
    <div className="space-y-6">
      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Workspace shell"
          titleClassName="text-sm font-semibold"
          description="Shared job pages reuse the same page header, toolbar, and workspace panel contract across quick execute, scheduled task, target management, and template flows."
        />

        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
          <PageFormHeaderCard
            title="Quick Execute"
            description="Run a one-off command or script on selected targets with the governed job workspace shell."
            spacing="default"
          />

          <WorkspacePanel
            className="flex min-h-[320px] flex-col"
            toolbar={(
              <SearchCombinationToolbar
                fieldConfigs={[]}
                onSearchChange={() => undefined}
                actions={(
                  <>
                    <Segmented
                      options={[
                        { label: 'Today', value: 'today' },
                        { label: '7 Days', value: '7days' },
                      ]}
                      value="today"
                    />
                    <Button type="primary">Create Task</Button>
                  </>
                )}
              />
            )}
          >
            <div className="space-y-3 text-sm text-[var(--color-text-2)]">
              <div className="rounded-md border border-[var(--color-border)] p-3">
                Shared execution form or table content renders here.
              </div>
              <div className="rounded-md border border-[var(--color-border)] p-3">
                The surrounding workspace shell stays stable while individual job flows change.
              </div>
            </div>
          </WorkspacePanel>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="List workspace shell"
          titleClassName="text-sm font-semibold"
          description="Scheduled tasks, target management, job records, and template libraries now share one governed list-shell contract instead of keeping header, search, and table framing split across page-local job code."
        />

        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
          <JobListWorkspaceShell
            title="Job Records"
            description="A governed list workspace for execution history with shared header, search toolbar, and table content framing."
            fieldConfigs={[
              { name: 'name', label: 'Name', lookup_expr: 'icontains' },
              {
                name: 'job_type',
                label: 'Job type',
                lookup_expr: 'in',
                options: [
                  { id: 'script', name: 'Script' },
                  { id: 'playbook', name: 'Playbook' },
                ],
              },
            ]}
            onSearchChange={() => undefined}
            actions={(
              <>
                <Segmented
                  options={[
                    { label: 'Today', value: 'today' },
                    { label: '7 days', value: '7days' },
                    { label: '30 days', value: '30days' },
                  ]}
                  value="today"
                />
                <Button type="primary">Create Task</Button>
              </>
            )}
            tableColumns={[
              { title: 'Name', dataIndex: 'name', key: 'name' },
              { title: 'Version', dataIndex: 'version', key: 'version' },
              { title: 'Updated at', dataIndex: 'updatedAt', key: 'updatedAt' },
            ]}
            tableDataSource={[
              { id: 1, name: 'Linux baseline', version: 'v1.2.0', updatedAt: '2026-07-02 10:15:00' },
              { id: 2, name: 'MySQL backup', version: 'v1.0.4', updatedAt: '2026-07-01 18:20:00' },
            ]}
            tableRowKey="id"
            tableLoading={false}
            tablePagination={{
              current: 1,
              pageSize: 20,
              total: 2,
              onChange: () => undefined,
            }}
          />
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Execution metadata semantics"
          titleClassName="text-sm font-semibold"
          description="Shared badges express job type, execution driver, script type, and trigger source in a consistent business language."
        />

        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
          <div className="flex flex-wrap items-center gap-3">
            <JobTypeBadge type="script" label="Script" />
            <JobTypeBadge type="playbook" label="Playbook" />
            <JobTypeBadge type="file" label="File Distribution" />
            <JobDriverBadge driver="ansible" />
            <JobDriverBadge driver="ssh" />
            <JobDriverBadge driver="sidecar" />
            <JobDriverBadge driver="nats-executor" />
            <JobScriptTypeBadge scriptType="shell" />
            <JobScriptTypeBadge scriptType="python" />
            <JobScriptTypeBadge scriptType="bat" />
            <JobScriptTypeBadge scriptType="powershell" />
            <JobTriggerSourceBadge source="manual" label="Manual" />
            <JobTriggerSourceBadge source="scheduled" label="Scheduled" />
            <JobTriggerSourceBadge source="api" label="API" />
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Playbook file operations"
          titleClassName="text-sm font-semibold"
          description="Shared job template flows now expose governed upload and upgrade business modals through Storybook instead of leaving those flows embedded only in page code."
        />

        <div className="grid gap-4 xl:grid-cols-2">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Upload new playbook" titleClassName="text-sm font-semibold" />
            <JobPlaybookUploadModal
              open
              form={uploadForm}
              uploadFile={null}
              onUploadFileChange={() => undefined}
              onConfirm={() => undefined}
              onCancel={() => undefined}
              onDownloadTemplate={() => undefined}
              t={t}
            />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Upgrade existing version" titleClassName="text-sm font-semibold" />
            <JobPlaybookUpgradeModal
              open
              form={upgradeForm}
              upgradeFile={null}
              currentVersion="v1.2.3"
              nextVersionPlaceholder="e.g. v1.2.4"
              onUpgradeFileChange={() => undefined}
              onConfirm={() => undefined}
              onCancel={() => undefined}
              t={t}
            />
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Playbook detail workflow"
          titleClassName="text-sm font-semibold"
          description="Template library and execution record pages share one tabbed playbook-detail drawer, and file preview remains a subordinate branch of the same workflow instead of a separate Storybook root."
        />

        <div className="grid gap-4 xl:grid-cols-2">
          <div className="overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)]">
            <div style={{ height: 760 }}>
              <JobPlaybookDetailDrawer
                open
                onClose={() => undefined}
                playbook={demoPlaybook}
                formatUpdatedAt={(value: string) => value.replace('T', ' ').replace('Z', '')}
                onPreviewFile={() => undefined}
              />
            </div>
          </div>

          <div className="overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)]">
            <div style={{ height: 760 }}>
              <JobPlaybookDetailDrawer
                open
                onClose={() => undefined}
                playbook={demoPlaybook}
                summaryItems={[
                  { label: 'Execution version', value: 'v2.2.0' },
                  { label: 'Executed by', value: 'job-runner-prod' },
                ]}
                extra={(
                  <div className="flex items-center gap-2">
                    <Button>Download</Button>
                    <Button type="primary">Upgrade version</Button>
                  </div>
                )}
                formatUpdatedAt={(value: string) => value.replace('T', ' ').replace('Z', '')}
                onPreviewFile={() => undefined}
              />
            </div>
          </div>
        </div>

        <div className="grid gap-4 xl:grid-cols-3">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="File preview" titleClassName="text-sm font-semibold" />
            <JobFilePreviewModal
              open
              preview={demoPreview}
              previewLabel="Preview"
              loadingLabel="Loading"
              failedMessage="File preview failed"
              onCancel={() => undefined}
            />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Preview loading" titleClassName="text-sm font-semibold" />
            <JobFilePreviewModal
              open
              loading
              preview={null}
              previewLabel="Preview"
              loadingLabel="Loading"
              failedMessage="File preview failed"
              onCancel={() => undefined}
            />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Preview error" titleClassName="text-sm font-semibold" />
            <JobFilePreviewModal
              open
              preview={null}
              error="The archive entry could not be decoded as UTF-8 text."
              previewLabel="Preview"
              loadingLabel="Loading"
              failedMessage="File preview failed"
              onCancel={() => undefined}
            />
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Playbook detail empty-state contract"
          titleClassName="text-sm font-semibold"
          description="Execution history and playbook library now share one governed detail-empty component for missing parameters, files, and README content inside the same tabbed playbook detail workflow."
        />

        <div className="grid gap-4 xl:grid-cols-3">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Parameters tab" titleClassName="text-sm font-medium" />
            <CompactEmptyState description="No playbook parameters are defined." className="py-8" />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Files tab" titleClassName="text-sm font-medium" />
            <CompactEmptyState description="No bundled files are available in this playbook package." className="py-8" />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="README tab" titleClassName="text-sm font-medium" />
            <CompactEmptyState description="No README content is available for this playbook." className="py-8" />
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Target selection workflow"
          titleClassName="text-sm font-semibold"
          description="Quick execute, file distribution, and scheduled task flows now share one governed target-selection contract instead of keeping host selection behavior hidden inside page-local job components."
        />

        <div className="grid gap-4 xl:grid-cols-[280px_minmax(0,1fr)]">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="regular" title="Source switch and entry action" titleClassName="text-sm font-semibold" />
            <div className="flex flex-col items-start gap-4">
              <TargetSourceSelector
                value="target_manager"
                onChange={() => undefined}
              />
              <AddTargetHostButton count={2} onClick={() => undefined} />
            </div>
          </div>

          <div className="overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)]">
            <div style={{ height: 640 }}>
              <JobHostSelectionModal
                open
                selectedKeys={['101', '102']}
                selectedHosts={targetSelectionHosts}
                source="target_manager"
                onConfirm={() => undefined}
                onCancel={() => undefined}
                fetchHosts={async () => ({
                  items: targetSelectionHosts,
                  total: targetSelectionHosts.length,
                })}
              />
            </div>
          </div>
        </div>

        <div className="grid gap-4 xl:grid-cols-[280px_minmax(0,1fr)]">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader
              spacing="regular"
              title="Node manager source variant"
              titleClassName="text-sm font-semibold"
              description="The same target-selection contract also governs node-manager sourced execution flows."
            />
            <div className="flex flex-col items-start gap-4">
              <TargetSourceSelector
                value="node_manager"
                onChange={() => undefined}
              />
              <AddTargetHostButton count={5} onClick={() => undefined} />
            </div>
          </div>

          <div className="overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)]">
            <div style={{ height: 640 }}>
              <JobHostSelectionModal
                open
                selectedKeys={['101']}
                selectedHosts={nodeManagerHosts.slice(0, 1)}
                source="node_manager"
                onConfirm={() => undefined}
                onCancel={() => undefined}
                fetchHosts={async ({ source }) => ({
                  items: source === 'node_manager' ? nodeManagerHosts : targetSelectionHosts,
                  total:
                    source === 'node_manager'
                      ? nodeManagerHosts.length
                      : targetSelectionHosts.length,
                })}
              />
            </div>
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Safety governance workflow"
          titleClassName="text-sm font-semibold"
          description="Dangerous command and dangerous path settings now share one governed Job safety workbench, with page-level copy and API behavior separated from the reusable rule-management contract."
        />

        <div className="overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)]">
          <div style={{ height: 720 }}>
            <JobDangerousRulePage
              title="Dangerous command rules"
              description="Configure command interception rules and confirmation strategies for high-risk job execution."
              addModalTitle="Add Dangerous Command"
              editModalTitle="Edit Dangerous Command"
              patternLabel="Match pattern"
              patternPlaceholder="Enter a command pattern"
              patternHelp="Use a full command string or a regular expression."
              patternExamples={['rm -rf /', 'shutdown -h now', 'systemctl restart .*']}
              forbiddenLabel="Forbidden"
              confirmLabel="Require Confirmation"
              strategyHelp="Forbidden rules block execution immediately. Confirmation rules require a second approval step."
              ruleNamePlaceholder="Enter a rule name"
              api={{
                getList: async () => ({
                  count: dangerousRuleFixtures.length,
                  items: dangerousRuleFixtures as any,
                }),
                create: async (data) => ({ id: 3, ...data } as any),
                update: async (id, data) => ({ id, ...data } as any),
                patch: async (id, data) => ({ id, ...data } as any),
                remove: async () => undefined,
              }}
            />
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Script authoring workflow"
          titleClassName="text-sm font-semibold"
          description="Quick execute and script library editing now share one governed job script editor contract, including language tabs, copy action, and fullscreen editing behavior."
        />

        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
          <JobScriptEditor
            value={{
              shell: '#!/bin/bash\necho "hello from shell"\n',
              bat: '@echo off\necho hello from bat\r\n',
              python: 'print("hello from python")\n',
              powershell: 'Write-Host "hello from powershell"\n',
            }}
            onChange={() => undefined}
            activeLang="shell"
          />
        </div>
      </section>
    </div>
  );
};

const meta = {
  title: 'Business/Job/FamilyOverview',
  component: FamilyOverview,
  decorators: [
    (Story) => (
      <div style={{ maxWidth: 1120, padding: 24, background: 'var(--color-bg-2)' }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof FamilyOverview>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Overview: Story = {};
