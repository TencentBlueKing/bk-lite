import type { Meta, StoryObj } from '@storybook/react';
import {
  SkillImportModal,
  ToolConnectionStatusTag,
  ToolEditorField,
  ToolEditorEmptyState,
  ToolEditorShell,
  ToolInstanceSidebar,
} from '@/components/opspilot-tool-editor';
import React from 'react';
import SectionHeader from '@/components/section-header';
import type { UploadFile } from 'antd/es/upload/interface';

const sidebarItems = [
  { id: 'mysql-1', title: 'Primary cluster', description: '10.0.0.8:3306' },
  { id: 'mysql-2', title: 'Reporting replica', description: '10.0.0.9:3306' },
  { id: 'mysql-3', title: 'Batch replica', description: '10.0.0.10:3306' },
];

const FamilyOverview = () => {
  const [importFileList, setImportFileList] = React.useState<UploadFile[]>([
    {
      uid: 'skill-package.zip',
      name: 'skill-package.zip',
      status: 'done',
    },
  ]);

  return (
    <div className="space-y-6">
      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader title="ToolInstanceSidebar shell" />
        <div className="grid gap-4 lg:grid-cols-[260px_260px]">
          <ToolInstanceSidebar
            title="MySQL instances"
            addLabel="+ Add"
            emptyDescription="No tool instances added yet."
            items={sidebarItems}
            selectedId="mysql-2"
            onAdd={() => undefined}
            onSelect={() => undefined}
            onDelete={() => undefined}
          />
          <div className="space-y-4">
            <ToolInstanceSidebar
              title="Kubernetes instances"
              addLabel="+ Add"
              emptyDescription="No tool instances added yet."
              items={[
                { id: 'k8s-1', title: 'Production cluster', description: 'apiVersion: v1' },
                { id: 'k8s-2', title: 'Staging cluster', description: 'apiVersion: v1' },
              ]}
              selectedId="k8s-1"
              selectedVariant="strong"
              onAdd={() => undefined}
              onSelect={() => undefined}
              onDelete={() => undefined}
            />
            <ToolInstanceSidebar
              title="Redis instances"
              addLabel="+ Add"
              emptyDescription="No tool instances added yet."
              items={[]}
              selectedId={null}
              onAdd={() => undefined}
              onSelect={() => undefined}
              onDelete={() => undefined}
            />
          </div>
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader title="ToolConnectionStatusTag states" />
        <div className="flex flex-wrap items-center gap-3">
          <ToolConnectionStatusTag scope="tool.mysql" status="untested" />
          <ToolConnectionStatusTag scope="tool.redis" status="success" />
          <ToolConnectionStatusTag scope="tool.kubernetes" status="failed" />
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          title="Labeled field contract"
          description="Tool editors now share one labeled-control primitive for instance metadata, credentials, and runtime values while keeping the underlying control type flexible."
        />
        <div className="grid gap-4 md:grid-cols-2">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <ToolEditorField label="Instance Name">
              <div className="rounded border border-[var(--color-border)] bg-[var(--color-bg-1)] px-3 py-2 text-sm">
                Orders primary
              </div>
            </ToolEditorField>
          </div>
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <ToolEditorField label="SSL">
              <div className="flex items-center gap-2 text-sm text-[var(--color-text-1)]">
                <span className="inline-block h-2.5 w-2.5 rounded-full bg-[var(--color-success)]" />
                Enabled
              </div>
            </ToolEditorField>
          </div>
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader title="Combined family contract" />
        <ToolEditorShell
          sidebarProps={{
            title: 'Postgres instances',
            addLabel: '+ Add',
            emptyDescription: 'No tool instances added yet.',
            items: [
              {
                id: 'pg-1',
                title: 'Orders primary',
                description: 'prod-orders.internal:5432',
              },
              {
                id: 'pg-2',
                title: 'Analytics replica',
                description: 'analytics.internal:5432',
              },
            ],
            selectedId: 'pg-1',
            selectedVariant: 'strong',
            onAdd: () => undefined,
            onSelect: () => undefined,
            onDelete: () => undefined,
          }}
          detailTitle="Orders primary"
          detailStatusScope="tool.postgres"
          detailStatus="success"
          emptyDescription="Select a connection field set to configure this instance."
          panelClassName="border-dashed bg-[var(--color-bg-2)]"
          detailFooter={
            <button className="rounded border border-[var(--color-border)] bg-[var(--color-bg-1)] px-3 py-1.5 text-sm text-[var(--color-text-1)]">
              Test connection
            </button>
          }
        >
          <p className="text-sm text-[var(--color-text-2)]">
            Shared tool editors reuse the same instance navigator, connection status contract,
            empty-state surface, and footer action row while each editor keeps its own form body.
          </p>
          <div className="rounded border border-[var(--color-border)] bg-[var(--color-bg-1)]">
            <div className="flex min-h-[120px] items-center justify-center text-sm text-[var(--color-text-3)]">
              Form body slot
            </div>
          </div>
        </ToolEditorShell>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader title="Empty and custom-footer states" />
        <div className="grid gap-4 xl:grid-cols-2">
          <ToolEditorShell
            sidebarProps={{
              title: 'Redis instances',
              addLabel: '+ Add',
              emptyDescription: 'No tool instances added yet.',
              items: [],
              selectedId: null,
              onAdd: () => undefined,
              onSelect: () => undefined,
              onDelete: () => undefined,
            }}
            emptyDescription="Select a connection field set to configure this instance."
          />
          <ToolEditorShell
            sidebarProps={{
              title: 'Postgres instances',
              addLabel: '+ Add',
              emptyDescription: 'No tool instances added yet.',
              items: [
                {
                  id: 'pg-1',
                  title: 'Orders primary',
                  description: 'prod-orders.internal:5432',
                },
              ],
              selectedId: 'pg-1',
              selectedVariant: 'strong',
              onAdd: () => undefined,
              onSelect: () => undefined,
              onDelete: () => undefined,
            }}
            detailTitle="Orders primary"
            detailStatusScope="tool.postgres"
            detailStatus="success"
            emptyDescription="Select a connection field set to configure this instance."
            detailFooterClassName="justify-between"
            detailFooter={
              <>
                <span className="text-sm text-[var(--color-text-2)]">Last checked 2 minutes ago</span>
                <button className="rounded border border-[var(--color-border)] bg-[var(--color-bg-1)] px-3 py-1.5 text-sm text-[var(--color-text-1)]">
                  Re-test
                </button>
              </>
            }
          >
            <div className="rounded border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4 text-sm text-[var(--color-text-2)]">
              Custom footer alignment remains part of the governed shell contract.
            </div>
          </ToolEditorShell>
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          title="Skill import workflow"
          description="ToolEditor now governs its own skill-package import flow alongside the navigator, status, and empty-state primitives."
        />
        <div className="grid gap-4 xl:grid-cols-2">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Import empty state" titleClassName="text-sm font-medium" />
            <SkillImportModal
              open
              fileList={[]}
              onFileListChange={() => undefined}
              onConfirm={() => undefined}
              onCancel={() => undefined}
            />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Ready to import" titleClassName="text-sm font-medium" />
            <SkillImportModal
              open
              fileList={importFileList}
              onFileListChange={setImportFileList}
              onConfirm={() => undefined}
              onCancel={() => undefined}
            />
          </div>
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          title="Editor empty states"
          description="The same empty-state primitive covers both unselected-instance guidance and no-match search feedback."
        />
        <div className="grid gap-4 md:grid-cols-2">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <ToolEditorEmptyState
              description="Please select an instance"
              fullHeight
            />
          </div>
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <ToolEditorEmptyState
              description="No matching skills"
            />
          </div>
        </div>
      </section>
    </div>
  );
};

const meta = {
  title: 'Business/OpsPilot/ToolEditor/FamilyOverview',
  component: FamilyOverview,
  decorators: [
    (Story) => (
      <div style={{ maxWidth: 980, padding: 24, background: 'var(--color-bg-2)' }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof FamilyOverview>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Overview: Story = {};
