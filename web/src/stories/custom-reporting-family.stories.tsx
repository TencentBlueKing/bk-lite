import type { Meta, StoryObj } from '@storybook/react';
import CustomReportingCleanupStrategyValue from '@/components/custom-reporting-cleanup-strategy-value';
import CustomReportingIdentityKeyGroup from '@/components/custom-reporting-identity-key-group';
import CustomReportingModeBadge from '@/components/custom-reporting-mode-badge';
import CustomReportingReviewStatusBadge from '@/components/custom-reporting-review-status-badge';
import CustomReportingReviewStatusSummary from '@/components/custom-reporting-review-status-summary';
import CustomReportingRuntimeStatusBadge from '@/components/custom-reporting-runtime-status-badge';
import CustomReportingTaskSummaryPanel from '@/components/custom-reporting-task-summary-panel';
import CustomReportingTargetModelValue from '@/components/custom-reporting-target-model-value';
import CustomReportingTokenDisplay from '@/components/custom-reporting-token-display';
import DetailListPanel from '@/components/detail-list-panel';
import PanelShell from '@/components/panel-shell';
import SectionHeader from '@/components/section-header';

const FamilyOverview = () => {
  const summaryTask = {
    id: 9,
    name: 'Host inventory sync',
    team: [1, 2],
    config: {
      mode: 'quick' as const,
      cleanup_strategy: 'snapshot' as const,
      quick_model: {
        model_id: 'bk_host',
        model_name: 'Host',
        identity_keys: ['bk_inst_name', 'cloud_id'],
      },
    },
    is_enabled: true,
    created_by: 'alice',
    created_at: '2026-06-25T02:15:00Z',
    updated_by: 'alice',
    updated_at: '2026-06-30T08:45:00Z',
    last_reported_at: '2026-07-01T01:20:00Z',
  };

  return (
    <div className="space-y-6">
      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Task identity semantics"
          titleClassName="text-sm font-semibold"
          description="Shared task metadata components keep mode, target model, identity keys, and cleanup strategy consistent across task lists, task details, and onboarding guidance."
        />

        <div className="grid gap-4 lg:grid-cols-2">
          <div className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <div className="flex flex-wrap items-center gap-3">
              <CustomReportingModeBadge mode="quick" />
              <CustomReportingModeBadge mode="standard" />
              <CustomReportingModeBadge mode="quick" label="Quick Import Model" />
            </div>
            <div className="text-sm text-[var(--color-text-2)]">
              <span className="font-medium text-[var(--color-text-1)]">Target model:</span>{' '}
              <CustomReportingTargetModelValue
                config={{
                  mode: 'quick',
                  quick_model: {
                    model_id: 'bk_host',
                    model_name: 'Host',
                    identity_keys: ['bk_inst_name'],
                  },
                }}
              />
            </div>
            <div className="text-sm text-[var(--color-text-2)]">
              <span className="font-medium text-[var(--color-text-1)]">Target model fallback:</span>{' '}
              <CustomReportingTargetModelValue
                config={{
                  mode: 'quick',
                  quick_model: {
                    model_id: 'bk_switch',
                    model_name: '',
                    identity_keys: ['bk_inst_name'],
                  },
                }}
              />
            </div>
            <div className="text-sm text-[var(--color-text-2)]">
              <span className="font-medium text-[var(--color-text-1)]">Standard model:</span>{' '}
              <CustomReportingTargetModelValue
                config={{
                  mode: 'standard',
                  model_id: 'bk_database',
                }}
              />
            </div>
            <div className="text-sm text-[var(--color-text-2)]">
              <span className="font-medium text-[var(--color-text-1)]">Empty target:</span>{' '}
              <CustomReportingTargetModelValue
                config={{
                  mode: 'standard',
                }}
                fallback="Not configured"
              />
            </div>
            <div className="text-sm text-[var(--color-text-2)]">
              <span className="font-medium text-[var(--color-text-1)]">Identity keys:</span>{' '}
              <CustomReportingIdentityKeyGroup
                keys={['bk_inst_name', 'ip', 'cloud_area_id']}
              />
            </div>
            <div className="text-sm text-[var(--color-text-2)]">
              <span className="font-medium text-[var(--color-text-1)]">Overflow identity keys:</span>{' '}
              <CustomReportingIdentityKeyGroup
                keys={['bk_inst_name', 'ip', 'cloud_area_id', 'host_id', 'biz_id']}
              />
            </div>
            <div className="text-sm text-[var(--color-text-2)]">
              <span className="font-medium text-[var(--color-text-1)]">Empty identity keys:</span>{' '}
              <CustomReportingIdentityKeyGroup keys={[]} />
            </div>
            <div className="text-sm text-[var(--color-text-2)]">
              <span className="font-medium text-[var(--color-text-1)]">Cleanup:</span>{' '}
              <CustomReportingCleanupStrategyValue strategy="snapshot" />
            </div>
            <div className="text-sm text-[var(--color-text-2)]">
              <span className="font-medium text-[var(--color-text-1)]">Cleanup variants:</span>{' '}
              <span className="inline-flex flex-wrap items-center gap-3">
                <CustomReportingCleanupStrategyValue strategy="none" />
                <CustomReportingCleanupStrategyValue strategy="expire" />
                <CustomReportingCleanupStrategyValue strategy="unexpected" />
              </span>
            </div>
          </div>

          <div className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader
              spacing="flush"
              title="Credential and onboarding contract"
              titleClassName="text-sm font-medium"
            />
            <CustomReportingTokenDisplay
              token="bkcr_xxx_live_token_1234567890"
              variant="panel"
              showCopyButton
            />
            <div className="space-y-2">
              <div className="text-xs text-[var(--color-text-3)]">Inline token surface</div>
              <CustomReportingTokenDisplay token="bkcr_xxx_live_token_1234567890" />
            </div>
            <div className="space-y-2">
              <div className="text-xs text-[var(--color-text-3)]">Empty token surface</div>
              <div className="rounded border border-dashed border-[var(--color-border)] px-3 py-2 text-xs text-[var(--color-text-3)]">
                <CustomReportingTokenDisplay token="" />
                No token available.
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Runtime and review semantics"
          titleClassName="text-sm font-semibold"
          description="Shared status surfaces align task health, batch progress, and reviewer outcomes across the task table, detail drawer, and batch review workflow."
        />

        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
          <div className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <div className="flex flex-wrap items-center gap-3">
              <CustomReportingRuntimeStatusBadge
                kind="task"
                status="receiving"
                label="Receiving"
              />
              <CustomReportingRuntimeStatusBadge
                kind="task"
                status="pending_review"
                label="Pending Review"
              />
              <CustomReportingRuntimeStatusBadge
                kind="batch"
                status="success"
                label="Success"
              />
              <CustomReportingRuntimeStatusBadge
                kind="task"
                status="no_report"
                label="No Report"
              />
              <CustomReportingRuntimeStatusBadge
                kind="batch"
                status="running"
                label="Running"
              />
              <CustomReportingRuntimeStatusBadge
                kind="batch"
                status="failed"
                label="Failed"
              />
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <CustomReportingReviewStatusBadge status="pending" label="Pending" />
              <CustomReportingReviewStatusBadge status="approved" label="Approved" />
              <CustomReportingReviewStatusBadge status="rejected" label="Rejected" />
              <CustomReportingReviewStatusBadge status="pending" label="Pending: 12" />
              <CustomReportingReviewStatusBadge status="approved" label="Approved · alice" />
            </div>
          </div>

          <div className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <CustomReportingReviewStatusSummary
              summary={{
                pending: 4,
                approved: 11,
                rejected: 2,
                total: 17,
              }}
            />
            <CustomReportingReviewStatusSummary
              summary={{
                pending: 0,
                approved: 0,
                rejected: 0,
                total: 0,
              }}
            />
            <CustomReportingReviewStatusSummary
              summary={{
                pending: 28,
                approved: 156,
                rejected: 13,
                total: 197,
              }}
            />
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Governed detail-card contract"
          titleClassName="text-sm font-semibold"
          description="Batch review drawers and onboarding detail surfaces now reuse the same framework `PanelShell`, with read-only metadata rendered through the governed detail-list panel."
        />

        <PanelShell
          className="rounded border border-[var(--color-border)] bg-[var(--color-bg)]"
          bodyClassName="space-y-3 p-[12px]"
        >
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-3">
              <CustomReportingReviewStatusBadge status="approved" label="Approved" />
              <CustomReportingRuntimeStatusBadge
                kind="batch"
                status="success"
                label="Success"
              />
            </div>

            <DetailListPanel
              className="border-0 bg-transparent"
              labelWidthClassName="w-40"
              items={[
                { label: 'Batch ID', value: '#2048' },
                { label: 'Reviewer', value: 'platform-admin' },
                { label: 'Reviewed At', value: '2026-07-01 14:22:08' },
              ]}
            />
          </div>
        </PanelShell>

        <div className="grid gap-4 xl:grid-cols-2">
          <CustomReportingTaskSummaryPanel
            task={summaryTask}
            teamLabels={['Platform', 'Ops']}
          />
          <CustomReportingTaskSummaryPanel
            task={summaryTask}
            teamLabels={['Platform', 'Ops']}
            variant="compact"
          />
        </div>
      </section>
    </div>
  );
};

const meta = {
  title: 'Business/CMDB/CustomReporting/FamilyOverview',
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
