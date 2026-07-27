import type { Meta, StoryObj } from '@storybook/react';
import React from 'react';
import { Button, Input } from 'antd';
import { ClearOutlined, EditOutlined } from '@ant-design/icons';
import Collapse from '@/components/collapse';
import CodeSnippet from '@/components/code-snippet';
import DetailListDrawerShell from '@/components/detail-list-drawer-shell';
import DetailIntro from '@/components/detail-intro';
import GuideStepPanel from '@/components/guide-step-panel';
import Introduction from '@/components/introduction';
import NoteListPanel from '@/components/note-list-panel';
import TroubleshootingCard from '@/components/troubleshooting-card';

const FamilyOverview = () => {
  return (
    <div className="space-y-6">
      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <div className="text-sm font-semibold text-[var(--color-text-1)]">
          Intro content shells
        </div>
        <div className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <Introduction
              title="Alert Enrichment"
              message="Configure reusable enrichment actions to annotate alarms with context before they fan out to operators."
            />
            <Introduction
              title="Operation Log"
              minWidth={420}
              spacing="flush"
              message="Keep the introduction shell readable and visually aligned even when the page layout narrows the working area."
            />
          </div>

          <div className="grid gap-4">
            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
              <DetailIntro
                title="Knowledge Base Alpha"
                description="Internal documentation and FAQ management."
              />
            </div>
            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
              <DetailIntro
                title="Kubernetes Collector"
                description="Cluster-level event ingestion and metric collection with a reusable visual shell."
                titleTruncate={false}
                descriptionTruncate={false}
                titleClassName="text-[21px] font-semibold leading-[28px] text-[var(--color-text-1)]"
                descriptionClassName="mt-0.5 break-words text-[13px] leading-5 text-[var(--color-text-2)] sm:text-sm"
                visual={(
                  <div className="flex h-[82px] w-[82px] shrink-0 items-center justify-center rounded-[20px] border border-[var(--color-border-1)] bg-[var(--color-fill-1)] p-2.5">
                    <div className="flex h-full w-full items-center justify-center rounded-lg bg-[var(--color-primary-bg-active)]">
                      <span className="text-base font-semibold text-[var(--color-primary)]">K8s</span>
                    </div>
                  </div>
                )}
              />
            </div>
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <div className="text-sm font-semibold text-[var(--color-text-1)]">
          Guided steps and notes
        </div>
        <div className="grid gap-4 xl:grid-cols-2">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <GuideStepPanel
              step={1}
              title="Download installation package"
              description="Fetch the installer artifact before moving to the target host."
            >
              <CodeSnippet
                value={'curl -O https://bk-lite.example.com/controller-installer.exe'}
                copyable
                tone="inverse"
              />
            </GuideStepPanel>
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <GuideStepPanel
              step={2}
              variant="timeline"
              showConnector
              eyebrow="STEP 02"
              title="Apply to cluster"
              description="Run the rendered manifest after confirming the organization secret."
            >
              <CodeSnippet
                value={'kubectl apply -f bk-lite-k8s-event-exporter.deploy.yaml'}
                copyable
              />
            </GuideStepPanel>
          </div>
        </div>

        <div className="grid gap-4 xl:grid-cols-[1fr_0.9fr]">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <NoteListPanel
              items={[
                'Confirm the selected organization secret before downloading deployment materials.',
                'Return to the event list after rollout to verify ingestion.',
              ]}
            />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <NoteListPanel
              items={[
                'Replace the legacy secret with the selected team secret before saving the media type.',
                'Verify the webhook from the same network segment as the Zabbix server.',
              ]}
              itemClassName="rounded-[14px] bg-[var(--color-fill-1)] px-3.5 py-3 text-[12px] leading-5"
              bulletClassName="mt-[2px] h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-primary)]"
            />
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <div className="text-sm font-semibold text-[var(--color-text-1)]">
          Troubleshooting patterns
        </div>
        <div className="grid gap-4 xl:grid-cols-2">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <TroubleshootingCard
              title="Events do not appear in BK-Lite"
              causeLabel="Possible causes"
              causes={[
                'Webhook URL is incorrect',
                'Team secret does not match the selected organization',
              ]}
              solutionLabel="Resolutions"
              solutions={[
                'Regenerate the current team secret',
                'Run a dry-run request from the Zabbix host',
              ]}
              solutionTone="accent"
              cardClassName="border border-[var(--color-border-1)] bg-[var(--color-fill-1)] px-4 py-3.5"
            />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <TroubleshootingCard
              badge={2}
              title="Collector cannot connect to NATS"
              titleClassName="mb-2 text-base font-semibold"
              causeLabel="Reason"
              cause="Network connectivity or certificate settings are blocking the collector handshake."
              causeLayout="inline"
              solutionLabel="Solutions"
              solutions={[
                'Inspect collector pod logs for TLS errors',
                'Verify the configured NATS endpoint and CA bundle',
              ]}
              cardClassName="rounded-lg"
            />
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <div className="text-sm font-semibold text-[var(--color-text-1)]">
          Disclosure panels
        </div>
        <div className="grid gap-4 xl:grid-cols-2">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <div className="space-y-3">
              <Collapse title="Default Accordion">
                <p className="text-sm text-[var(--color-text-2)]">
                  Use the shared disclosure shell to reveal additional chart, filter, or grouped metric content without forking layout behavior.
                </p>
              </Collapse>
              <Collapse
                title={(
                  <div className="flex items-center justify-between gap-3">
                    <span>Alarm Source Filter</span>
                    <ClearOutlined className="text-[var(--color-text-3)]" />
                  </div>
                )}
              >
                <Input className="w-[250px]" placeholder="Type to filter" />
              </Collapse>
            </div>
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <Collapse
              title="Sortable Metric Group"
              sortable
              dragHandleOnly
              onDragStart={() => undefined}
              onDragEnd={() => undefined}
              onDragOver={(event) => event.preventDefault()}
              onDrop={() => undefined}
              icon={(
                <div className="flex items-center gap-1">
                  <Button type="link" size="small" icon={<EditOutlined />} />
                  <Button type="link" size="small">
                    More
                  </Button>
                </div>
              )}
            >
              <div className="flex flex-wrap gap-3">
                <div className="min-w-[180px] rounded-lg border border-[var(--color-border)] bg-[var(--color-fill-1)] p-3 text-sm">
                  CPU usage
                </div>
                <div className="min-w-[180px] rounded-lg border border-[var(--color-border)] bg-[var(--color-fill-1)] p-3 text-sm">
                  Memory usage
                </div>
                <div className="min-w-[180px] rounded-lg border border-[var(--color-border)] bg-[var(--color-fill-1)] p-3 text-sm">
                  Disk latency
                </div>
              </div>
            </Collapse>
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <div className="text-sm font-semibold text-[var(--color-text-1)]">
          Detail drawer shells
        </div>
        <div className="grid gap-4 xl:grid-cols-2">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <div className="h-[620px] overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)]">
              <DetailListDrawerShell
                open={true}
                onClose={() => undefined}
                title="Operation Detail"
                items={[
                  { label: 'Target Type', value: 'License' },
                  { label: 'Target ID', value: 'license-01' },
                  { label: 'Scenario', value: 'Manual update' },
                ]}
                labelWidthClassName="w-32"
              />
            </div>
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <div className="h-[620px] overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)]">
              <DetailListDrawerShell
                open={true}
                onClose={() => undefined}
                title="Knowledge Relation Detail"
                items={[
                  { label: 'Source Node', value: 'Service Alpha' },
                  { label: 'Target Node', value: 'Database Cluster' },
                ]}
                labelWidthClassName="w-32"
              >
                <div>
                  <div className="mb-2 font-medium">Before / After</div>
                  <div className="rounded-[12px] border border-[var(--color-border-1)] bg-[var(--color-fill-1)] p-3 text-xs text-[var(--color-text-2)]">
                    Structured diff content stays outside the base detail list but inside the same governed drawer shell.
                  </div>
                </div>
              </DetailListDrawerShell>
            </div>
          </div>
        </div>
      </section>

      <section className="space-y-2 rounded-lg border border-dashed border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <div className="text-sm font-semibold text-[var(--color-text-1)]">
          Storybook structure
        </div>
        <div className="text-sm text-[var(--color-text-2)]">
          The Content family is currently governed through intro, guided-step, note-list, troubleshooting, disclosure-panel, and detail-drawer-shell sub-contracts, while lower-level content primitives stay standalone.
        </div>
      </section>
    </div>
  );
};

const meta = {
  title: 'Framework/Content/FamilyOverview',
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
