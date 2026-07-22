import type { Meta, StoryObj } from '@storybook/react';
import React from 'react';
import { Button, Input, Tag } from 'antd';
import CustomTable from '@/components/custom-table';
import SelectableCardGrid from '@/components/selectable-card-grid';
import SelectionPreviewLayout from '@/components/selection-preview-layout';

const notificationCards = [
  {
    icon: 'youjian',
    title: 'Email',
    tag: 'Email',
    description: 'Send notifications to selected recipients.',
    value: 'email',
  },
  {
    icon: 'qiwei2',
    title: 'Enterprise WeChat',
    tag: 'WeChat',
    description: 'Post alert notifications to configured bots.',
    value: 'enterprise_wechat_bot',
  },
  {
    icon: 'dongzuo1',
    title: 'NATS',
    tag: 'NATS',
    description: 'Push event messages to the internal message bus.',
    value: 'nats',
  },
];

const SelectionFamilyOverview = () => {
  return (
    <div className="space-y-6">
      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <div className="text-sm font-semibold text-[var(--color-text-1)]">
          Selectable card patterns
        </div>
        <div className="grid gap-4 xl:grid-cols-2">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SelectableCardGrid
              data={notificationCards}
              value={['email', 'nats']}
              selectionMode="multiple"
            />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SelectableCardGrid
              data={[
                {
                  title: 'Keyword Alert',
                  description: 'Create a policy based on direct keyword matching.',
                  value: 'keyword',
                },
                {
                  title: 'Aggregation Alert',
                  description: 'Create a policy based on grouped counts and thresholds.',
                  value: 'aggregate',
                },
              ]}
              value="keyword"
              selectionMode="single"
              cardWidth={248}
              style={{ justifyContent: 'center' }}
            />
          </div>
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <div className="text-sm font-semibold text-[var(--color-text-1)]">
          Selection preview layouts
        </div>
        <div className="grid gap-4">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SelectionPreviewLayout
              primaryWidth={560}
              items={[
                { key: '1', label: 'web-prod-01' },
                { key: '2', label: 'web-prod-02' },
                { key: '3', label: 'db-stage-01' },
              ]}
              onClear={() => undefined}
              onRemove={() => undefined}
              primary={(
                <div className="flex flex-col gap-3">
                  <Input placeholder="Search instances" />
                  <CustomTable
                    size="small"
                    pagination={false}
                    rowKey="key"
                    dataSource={[
                      { key: '1', name: 'web-prod-01', region: 'ap-shanghai', status: 'Running' },
                      { key: '2', name: 'web-prod-02', region: 'ap-shanghai', status: 'Running' },
                      { key: '3', name: 'db-stage-01', region: 'ap-beijing', status: 'Stopped' },
                    ]}
                    columns={[
                      { title: 'Instance', dataIndex: 'name', key: 'name' },
                      { title: 'Region', dataIndex: 'region', key: 'region' },
                      {
                        title: 'Status',
                        dataIndex: 'status',
                        key: 'status',
                        render: (value: string) => (
                          <Tag color={value === 'Running' ? 'green' : 'default'}>
                            {value}
                          </Tag>
                        ),
                      },
                    ]}
                  />
                </div>
              )}
            />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SelectionPreviewLayout
              primaryWidth={520}
              showClearWhenEmpty={false}
              previewTitle="Pending Documents (2)"
              footer={(
                <div className="border-t border-[var(--color-border)] pt-3 text-center text-xs text-[var(--color-primary)]">
                  Click confirm to apply the selected documents.
                </div>
              )}
              primaryClassName="rounded-lg border border-[var(--color-border)] p-4"
              previewClassName="rounded-lg border border-[var(--color-border)] p-4 h-full flex flex-col border-l-0"
              previewHeaderClassName="mb-2"
              listClassName="flex-1 space-y-2 overflow-auto"
              items={[
                {
                  key: '1',
                  label: (
                    <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-fill-1)] p-3">
                      Incident-handbook.md
                    </div>
                  ),
                },
                {
                  key: '2',
                  label: (
                    <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-fill-1)] p-3">
                      Service-map.pdf
                    </div>
                  ),
                },
              ]}
              onClear={() => undefined}
              onRemove={() => undefined}
              primary={(
                <div className="flex flex-col gap-3">
                  <Input placeholder="Search groups" />
                  <div className="rounded-md border border-[var(--color-border)] p-3">
                    <div className="mb-2 font-medium">Team Tree</div>
                    <div className="space-y-2 text-sm text-[var(--color-text-2)]">
                      <div>Business</div>
                      <div className="pl-4">Payment Team</div>
                      <div>Infrastructure</div>
                      <div className="pl-4">Observability</div>
                    </div>
                  </div>
                  <Button type="dashed">Expand all</Button>
                </div>
              )}
            />
          </div>
        </div>
      </section>

      <section className="space-y-2 rounded-lg border border-dashed border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <div className="text-sm font-semibold text-[var(--color-text-1)]">
          Storybook structure
        </div>
        <div className="text-sm text-[var(--color-text-2)]">
          The Selection family is governed through choice-card and preview-layout branches instead of separate leaf stories.
        </div>
      </section>
    </div>
  );
};

const meta = {
  title: 'Framework/Selection/FamilyOverview',
  component: SelectionFamilyOverview,
  decorators: [
    (Story) => (
      <div style={{ maxWidth: 1100, padding: 24, background: 'var(--color-bg-2)' }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof SelectionFamilyOverview>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Overview: Story = {};
