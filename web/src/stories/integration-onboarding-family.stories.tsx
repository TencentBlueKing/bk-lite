import type { Meta, StoryObj } from '@storybook/nextjs';
import { Button, Input, Select } from 'antd';
import IntegrationAccessComplete from '@/components/integration-access-complete';
import {
  createCmdbK8sAccessCompletePreset,
  createLogK8sAccessCompletePreset,
  createMonitorK8sAccessCompletePreset,
} from '@/components/integration-access-complete/presets';
import {
  createLogK8sAccessAssetFieldsCopy,
  createMonitorK8sAccessAssetFieldsCopy,
} from '@/app/monitor/components/k8s-access-asset-fields/presets';
import {
  createLogK8sStepCalloutPreset,
  createMonitorK8sStepCalloutPreset,
} from '@/components/integration-step-callout/presets';
import K8sAccessAssetFields from '@/app/monitor/components/k8s-access-asset-fields';
import SectionHeader from '@/components/section-header';
import FormSettingRow from '@/components/form-setting-row';
import IntegrationStepCallout from '@/components/integration-step-callout';
import { createK8sStoryT } from './k8s-story.fixtures';

const t = createK8sStoryT();

const FamilyOverview = () => {
  return (
    <div className="space-y-6">
      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          title="Step guidance contract"
          description="This business family composes framework-governed onboarding primitives so teams can review the full flow contract without duplicating leaf stories under business taxonomy."
        />
        <IntegrationStepCallout
          title="Prerequisites"
          description="Shared onboarding guidance stays consistent before monitor, log, or CMDB-specific form content appears."
          items={[
            'Confirm the target cluster or node permissions are available.',
            'Choose the correct organization before generating commands or saving the flow.',
            'Validate the runtime preset so downstream onboarding steps stay coherent.',
          ]}
        />
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader title="Setting rows" />
        <div className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
        <FormSettingRow
            control={<Input placeholder="Cluster name" style={{ width: 280 }} />}
            description="The asset name used in the integration list and downstream views."
          />
          <FormSettingRow
            control={(
              <Select
                style={{ width: 280 }}
                placeholder="Select cloud region"
                options={[
                  { value: 'cn-hz', label: 'cn-hangzhou' },
                  { value: 'sg', label: 'ap-southeast-1' },
                ]}
              />
            )}
            description="Commands and automatic discovery bind to the selected cloud region."
          />
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          title="Combined onboarding contract"
          description="The family overview stays business-scoped because it shows how framework content, layout, and feedback primitives travel together through one governed onboarding journey."
        />
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <IntegrationStepCallout
              title="Before connecting"
              description="The onboarding family carries shared guidance and field row layout before the flow hands off to an app-specific shell."
              items={[
                'Review prerequisites first.',
                'Collect the minimum identity fields next.',
                'Continue into the module-specific install or automatic configuration flow.',
              ]}
            />
            <div className="space-y-4 rounded-lg bg-[var(--color-bg-1)] p-4">
              <FormSettingRow
                control={<Input placeholder="Cluster name" style={{ width: 260 }} />}
                description="Used when the flow creates a new managed asset."
              />
              <FormSettingRow
                control={(
                  <Select
                    style={{ width: 260 }}
                    placeholder="Select organization"
                    options={[
                      { value: 'platform', label: 'Platform Team' },
                      { value: 'payments', label: 'Payments Team' },
                    ]}
                  />
                )}
                description="Sets the ownership boundary for the new asset."
              />
              <div className="flex justify-end">
                <Button type="primary">Next</Button>
              </div>
            </div>
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <IntegrationAccessComplete
              title="Collector setup completed"
              description="The shared completion surface closes monitor, log, and CMDB onboarding flows with a consistent success contract."
              subDescription="Teams can continue into the next business workflow without redesigning the final state per app."
              actions={[
                {
                  key: 'primary',
                  label: 'View assets',
                  type: 'primary',
                  onClick: () => undefined,
                },
                {
                  key: 'secondary',
                  label: 'Add another cluster',
                  onClick: () => undefined,
                },
              ]}
            />
          </div>
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          title="Completion presets across apps"
          description="The final success surface is shared, but monitor, log, and CMDB now converge through governed preset helpers instead of hand-rolled action sets per app."
        />
        <div className="grid gap-4 xl:grid-cols-3">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <IntegrationAccessComplete
              {...createMonitorK8sAccessCompletePreset(t, {
                onPrimaryAction: () => undefined,
                onSecondaryAction: () => undefined,
              })}
            />
          </div>
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <IntegrationAccessComplete
              {...createLogK8sAccessCompletePreset(t, {
                onPrimaryAction: () => undefined,
                onSecondaryAction: () => undefined,
              })}
            />
          </div>
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <IntegrationAccessComplete
              {...createCmdbK8sAccessCompletePreset(t, {
                onPrimaryAction: () => undefined,
                onSecondaryAction: () => undefined,
              })}
            />
          </div>
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          title="K8s onboarding entry presets"
          description="Monitor and log now converge on governed preset helpers for both the prerequisite callout and the access-asset field copy, instead of keeping those first-step differences scattered across page code."
        />
        <div className="grid gap-6 xl:grid-cols-2">
          <div className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <IntegrationStepCallout {...createMonitorK8sStepCalloutPreset(t)} />
            <div className="rounded-lg bg-[var(--color-bg-1)] p-4">
              <K8sAccessAssetFields
                copy={createMonitorK8sAccessAssetFieldsCopy(t)}
                controlWidth={260}
                cloudRegionOptions={[
                  { value: 'cn-hz', label: 'cn-hangzhou' },
                  { value: 'sg', label: 'ap-southeast-1' },
                ]}
                existingClusterOptions={[
                  { value: 'cluster-a', label: 'payments-cluster-a' },
                  { value: 'cluster-b', label: 'analytics-cluster-b' },
                ]}
              />
            </div>
          </div>

          <div className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <IntegrationStepCallout {...createLogK8sStepCalloutPreset(t)} />
            <div className="rounded-lg bg-[var(--color-bg-1)] p-4">
              <K8sAccessAssetFields
                copy={createLogK8sAccessAssetFieldsCopy(t)}
                controlWidth={260}
                cloudRegionOptions={[
                  { value: 'cn-hz', label: 'cn-hangzhou' },
                  { value: 'sg', label: 'ap-southeast-1' },
                ]}
                existingClusterOptions={[
                  { value: 'cluster-a', label: 'payments-cluster-a' },
                  { value: 'cluster-b', label: 'analytics-cluster-b' },
                ]}
                existingClusterShowSearch
              />
            </div>
          </div>
        </div>
      </section>
    </div>
  );
};

const meta = {
  title: 'Business/Integrations/Onboarding/FamilyOverview',
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
