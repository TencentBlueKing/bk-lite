import type { Meta, StoryObj } from '@storybook/nextjs';
import { Button, Form, Input, InputNumber, Radio, Select } from 'antd';
import IntegrationAccessComplete from '@/components/integration-access-complete';
import {
  createCmdbK8sAccessCompletePreset,
  createLogK8sAccessCompletePreset,
  createMonitorK8sAccessCompletePreset,
} from '@/components/integration-access-complete/presets';
import IntegrationK8sAccessConfigShell from '@/app/monitor/components/integration-contract/integration-k8s-access-config-shell';
import IntegrationK8sConfigurationShell from '@/components/integration-k8s-configuration-shell';
import K8sAccessAssetFields from '@/app/monitor/components/k8s-access-asset-fields';
import {
  createLogK8sAccessAssetFieldsCopy,
  createMonitorK8sAccessAssetFieldsCopy,
} from '@/app/monitor/components/k8s-access-asset-fields/presets';
import K8sCollectorInstallStep from '@/app/monitor/components/k8s-collector-install-step';
import {
  createCmdbK8sCollectorInstallCopy,
  createLogK8sCollectorInstallCopy,
  createMonitorK8sCollectorInstallCopy,
} from '@/app/monitor/components/k8s-collector-install-step/presets';
import K8sCommonIssuesDrawer from '@/app/monitor/components/k8s-common-issues-drawer';
import SectionHeader from '@/components/section-header';
import {
  createLogK8sStepCalloutPreset,
  createMonitorK8sStepCalloutPreset,
} from '@/components/integration-step-callout/presets';
import { createK8sStoryT } from './k8s-story.fixtures';

const issues = [
  {
    id: 1,
    title: 'Pod pending for a long time',
    reason:
      'The cluster has no schedulable resources for the requested limits.',
    solutions: [
      'Check node usage with kubectl top nodes.',
      'Reduce requests or add worker nodes.',
    ],
  },
  {
    id: 2,
    title: 'Collector cannot reach NATS',
    reason:
      'Egress or certificate configuration is blocking the connection.',
    solutions: [
      'Inspect pod logs for TLS errors.',
      'Verify the cluster can reach the configured NATS endpoint.',
    ],
  },
];

const presetT = createK8sStoryT({
  'monitor.integrations.k8s.accessCompleteSubDesc':
    'Open the discovered assets now or start another onboarding flow.',
  'monitor.integrations.k8s.viewClusterList': 'View assets',
});

const cloudRegionOptions = [
  { value: '1', label: 'ap-southeast-1' },
  { value: '2', label: 'eu-west-1' },
];

const existingClusterOptions = [
  { value: 'cluster-a', label: 'payments-cluster-a' },
  { value: 'cluster-b', label: 'analytics-cluster-b' },
];

const FamilyOverview = () => {
  const [monitorAccessForm] = Form.useForm();
  const [logAccessForm] = Form.useForm();

  return (
    <div className="space-y-6">
      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Shared K8s flow shells"
          titleClassName="text-sm font-semibold"
          description={(
            <>
              <p>
                Monitor and log do not just share field fragments. They also share the K8s access step shell and the
                multi-step configuration flow skeleton that wraps access, install, and completion states.
              </p>
              <p className="mt-2">
                This family stays business-scoped because it documents one K8s onboarding journey, while the focused
                completion-result and install/verify shell contracts remain governed in shared framework families.
              </p>
            </>
          )}
        />

        <div className="space-y-6">
          <div className="space-y-3">
            <SectionHeader spacing="compact" title="Access step shell variants" titleClassName="text-sm font-medium" />
            <div className="grid gap-6 xl:grid-cols-2">
              <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
                <div className="rounded-lg bg-[var(--color-bg-1)] p-4">
                  <IntegrationK8sAccessConfigShell
                    form={monitorAccessForm}
                    sectionTitle="Monitor K8s Access"
                    initialValues={{ accessType: 'new' }}
                    stepCallout={createMonitorK8sStepCalloutPreset(presetT)}
                    assetFieldsProps={{
                      controlWidth: 260,
                      cloudRegionOptions,
                      existingClusterOptions,
                      copy: createMonitorK8sAccessAssetFieldsCopy(presetT),
                    }}
                    actions={<Button type="primary">Next</Button>}
                  >
                    <div className="rounded-lg bg-[var(--color-fill-1)] p-4 text-sm text-[var(--color-text-2)]">
                      Monitor flow keeps the shared shell and injects module-specific access fields underneath.
                    </div>
                  </IntegrationK8sAccessConfigShell>
                </div>
              </div>

              <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
                <div className="rounded-lg bg-[var(--color-bg-1)] p-4">
                  <IntegrationK8sAccessConfigShell
                    form={logAccessForm}
                    sectionTitle="Log K8s Access"
                    initialValues={{
                      accessType: 'existing',
                      k8sCluster: 'cluster-a',
                      cloud_region_id: '1',
                      runtime_profile: 'custom',
                      host_log_path: '/var/log/containers',
                    }}
                    stepCallout={createLogK8sStepCalloutPreset(presetT)}
                    assetFieldsProps={{
                      controlWidth: 260,
                      cloudRegionOptions,
                      existingClusterOptions,
                      existingClusterShowSearch: true,
                      copy: createLogK8sAccessAssetFieldsCopy(presetT),
                    }}
                    actions={<Button type="primary">Next</Button>}
                  >
                    <Form.Item label="Runtime Profile" required>
                      <Form.Item name="runtime_profile" noStyle>
                        <Radio.Group style={{ width: 260 }}>
                          <Radio value="standard">Standard</Radio>
                          <Radio value="docker">Docker</Radio>
                          <Radio value="custom">Custom</Radio>
                        </Radio.Group>
                      </Form.Item>
                    </Form.Item>

                    <Form.Item label="Host Log Path" required>
                      <Form.Item name="host_log_path" noStyle>
                        <Input style={{ width: 260 }} placeholder="/var/log/containers" />
                      </Form.Item>
                    </Form.Item>
                  </IntegrationK8sAccessConfigShell>
                </div>
              </div>
            </div>
          </div>

          <div className="space-y-3">
            <SectionHeader
              spacing="compact"
              title="Configuration flow variants"
              titleClassName="text-sm font-medium"
            />
            <div className="grid gap-6 xl:grid-cols-3">
              <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
                <div className="rounded-lg bg-[var(--color-bg-1)] p-4">
                  <IntegrationK8sConfigurationShell<{ command?: string; instance_id?: string }>
                    accessConfigTitle="Access Config"
                    collectorInstallTitle="Collector Install"
                    accessCompleteTitle="Access Complete"
                    accessCompletePreset={createMonitorK8sAccessCompletePreset(
                      presetT,
                      {
                        onPrimaryAction: () => undefined,
                        onSecondaryAction: () => undefined,
                      },
                    )}
                    renderAccessConfig={({ next }) => (
                      <div className="rounded border p-4">
                        <p className="mb-4 text-sm text-[var(--color-text-2)]">
                          Monitor variant can inject its own access form and cadence settings.
                        </p>
                        <InputNumber
                          style={{ width: '100%' }}
                          min={1}
                          max={3600}
                          defaultValue={60}
                          addonAfter={(
                            <Select
                              defaultValue="seconds"
                              style={{ width: 100 }}
                              options={[
                                { value: 'seconds', label: 'Seconds' },
                                { value: 'minutes', label: 'Minutes' },
                                { value: 'hours', label: 'Hours' },
                              ]}
                            />
                          )}
                        />
                        <div className="mt-4">
                          <Button
                            type="primary"
                            onClick={() =>
                              next({
                                command: 'kubectl apply -f metrics-collector.yaml',
                                instance_id: 'host-01',
                              })
                            }
                          >
                            Continue
                          </Button>
                        </div>
                      </div>
                    )}
                    renderCollectorInstall={({ commandData, prev, next }) => (
                      <div className="rounded border p-4">
                        <p className="mb-3 text-sm text-[var(--color-text-2)]">
                          Target instance: {commandData?.instance_id || '--'}
                        </p>
                        <div className="flex gap-2">
                          <Button onClick={prev}>Back</Button>
                          <Button type="primary" onClick={() => next()}>
                            Continue
                          </Button>
                        </div>
                      </div>
                    )}
                  />
                </div>
              </div>

              <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
                <div className="rounded-lg bg-[var(--color-bg-1)] p-4">
                  <IntegrationK8sConfigurationShell<{ command?: string }>
                    accessConfigTitle="Access Config"
                    collectorInstallTitle="Collector Install"
                    accessCompleteTitle="Access Complete"
                    accessCompletePreset={createLogK8sAccessCompletePreset(
                      presetT,
                      {
                        onPrimaryAction: () => undefined,
                        onSecondaryAction: () => undefined,
                      },
                    )}
                    renderAccessConfig={({ commandData, next }) => (
                      <div className="rounded border p-4">
                        <p className="mb-4 text-sm text-[var(--color-text-2)]">
                          Shared first step shell with log-specific runtime profile fields.
                        </p>
                        <Button
                          type="primary"
                          onClick={() => next({ ...commandData, command: 'kubectl apply -f collector.yaml' })}
                        >
                          Save and continue
                        </Button>
                      </div>
                    )}
                    renderCollectorInstall={({ commandData, prev, next }) => (
                      <div className="rounded border p-4">
                        <p className="mb-3 text-sm text-[var(--color-text-2)]">
                          Install command: {commandData?.command || '--'}
                        </p>
                        <div className="flex gap-2">
                          <Button onClick={prev}>Back</Button>
                          <Button type="primary" onClick={() => next()}>
                            Verify and continue
                          </Button>
                        </div>
                      </div>
                    )}
                  />
                </div>
              </div>

              <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
                <div className="rounded-lg bg-[var(--color-bg-1)] p-4">
                  <IntegrationK8sConfigurationShell<{
                    collectorClusterId: string;
                    cloudRegionId: string;
                  }>
                    initialCommandData={{
                      collectorClusterId: '',
                      cloudRegionId: '',
                    }}
                    accessConfigTitle="Access Config"
                    collectorInstallTitle="Collector Install"
                    accessCompleteTitle="Access Complete"
                    resetActionKey="another"
                    accessCompletePreset={createCmdbK8sAccessCompletePreset(
                      presetT,
                      {
                        onPrimaryAction: () => undefined,
                        onSecondaryAction: () => undefined,
                      },
                    )}
                    renderAccessConfig={({ next }) => (
                      <div className="rounded border p-4">
                        <p className="mb-4 text-sm text-[var(--color-text-2)]">
                          CMDB guided onboarding keeps its own save form while reusing the same wizard shell.
                        </p>
                        <Button
                          type="primary"
                          onClick={() =>
                            next({
                              collectorClusterId: 'prod-cluster-1',
                              cloudRegionId: 'cn-hangzhou',
                            })
                          }
                        >
                          Save and continue
                        </Button>
                      </div>
                    )}
                    renderCollectorInstall={({ commandData, prev, next }) => (
                      <div className="rounded border p-4">
                        <p className="mb-2 text-sm text-[var(--color-text-2)]">
                          Collector ID: {commandData?.collectorClusterId || '--'}
                        </p>
                        <p className="mb-4 text-sm text-[var(--color-text-2)]">
                          Cloud region: {commandData?.cloudRegionId || '--'}
                        </p>
                        <div className="flex gap-2">
                          <Button onClick={prev}>Back</Button>
                          <Button type="primary" onClick={() => next()}>
                            Verify and continue
                          </Button>
                        </div>
                      </div>
                    )}
                  />
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Access configuration"
          titleClassName="text-sm font-semibold"
          description="The K8s family starts with one governed asset-binding contract shared by monitor, log, and CMDB onboarding flows."
        />

        <Form
          layout="vertical"
          initialValues={{ accessType: 'new' }}
          className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4"
        >
          <K8sAccessAssetFields
            copy={createMonitorK8sAccessAssetFieldsCopy(presetT)}
            controlWidth={300}
            cloudRegionOptions={[
              { value: 1, label: 'ap-southeast-1' },
              { value: 2, label: 'eu-west-1' },
            ]}
            existingClusterOptions={[
              { value: 'cluster-a', label: 'payments-cluster-a' },
              { value: 'cluster-b', label: 'analytics-cluster-b' },
            ]}
          />
        </Form>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Install and troubleshoot"
          titleClassName="text-sm font-semibold"
          description={(
            <>
              <p>
                Monitor and log use the same direct-command verify flow, while CMDB
                adds a pre-generation idle state without forking the shared contract.
              </p>
              <p className="mt-2">
                The K8s business layer owns install-specific semantics here, while the terminal success surface composes the
                shared framework completion-result contract instead of reintroducing a separate K8s-only result component.
              </p>
            </>
          )}
        />

        <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <div className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="flush" title="Ready command flow" titleClassName="text-sm font-medium" />
            <K8sCollectorInstallStep
              installCommand="kubectl apply -f collector.yaml"
              copy={createMonitorK8sCollectorInstallCopy(presetT)}
              onVerifyStatus={async () => false}
              onPrev={() => undefined}
              onNext={() => undefined}
              onOpenCommonIssues={() => undefined}
            />
          </div>

          <div className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="flush" title="Generate-then-install flow" titleClassName="text-sm font-medium" />
            <K8sCollectorInstallStep
              installCommand=""
              copy={{
                ...createCmdbK8sCollectorInstallCopy(presetT),
                title: 'Generate and install collector',
                installDescription:
                  'CMDB keeps the same install shell but starts in an idle state until a command is generated.',
                commonIssuesText: undefined,
                troubleshootText: undefined,
              }}
              installActions={(
                <div className="mb-2 flex items-center gap-2">
                  <Button type="primary">Generate command</Button>
                </div>
              )}
              verifyDisabled
              initialVerificationStatus="idle"
              onVerifyStatus={async () => false}
              onPrev={() => undefined}
              onNext={() => undefined}
            />
          </div>
        </div>

        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
          <SectionHeader spacing="regular" title="Common issues" titleClassName="text-sm font-medium" />
          <K8sCommonIssuesDrawer
            title="Common issues"
            issues={issues}
            reasonLabel="Reason: "
            solutionLabel="Solutions"
            defaultOpen
          />
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Install-step presets across apps"
          titleClassName="text-sm font-semibold"
          description="Monitor, log, and CMDB now reuse the same install-step component through governed copy presets, so the middle phase of K8s onboarding stays aligned without flattening app-specific language."
        />

        <div className="grid gap-4 xl:grid-cols-3">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <K8sCollectorInstallStep
              installCommand="kubectl apply -f collector.yaml"
              copy={createMonitorK8sCollectorInstallCopy(presetT)}
              onVerifyStatus={async () => false}
              onPrev={() => undefined}
              onNext={() => undefined}
            />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <K8sCollectorInstallStep
              installCommand="kubectl apply -f collector.yaml"
              copy={createLogK8sCollectorInstallCopy(presetT)}
              onVerifyStatus={async () => false}
              onPrev={() => undefined}
              onNext={() => undefined}
            />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <K8sCollectorInstallStep
              installCommand="kubectl apply -f generated-collector.yaml"
              copy={createCmdbK8sCollectorInstallCopy(presetT)}
              installActions={(
                <div className="mb-2 flex items-center gap-2">
                  <Button type="primary">Generate command</Button>
                </div>
              )}
              initialVerificationStatus="idle"
              onVerifyStatus={async () => false}
              onPrev={() => undefined}
              onNext={() => undefined}
            />
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Completion states"
          titleClassName="text-sm font-semibold"
          description="Completion stays on the shared integration result shell while allowing K8s flows to vary action sets by domain."
        />

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
          <IntegrationAccessComplete
            {...createMonitorK8sAccessCompletePreset(presetT, {
              onPrimaryAction: () => undefined,
              onSecondaryAction: () => undefined,
            })}
          />
        </div>

        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
          <IntegrationAccessComplete
            {...createCmdbK8sAccessCompletePreset(presetT, {
              onPrimaryAction: () => undefined,
              onSecondaryAction: () => undefined,
            })}
          />
        </div>
      </div>
      </section>
    </div>
  );
};

const meta = {
  title: 'Business/Integrations/K8s/FamilyOverview',
  component: FamilyOverview,
  decorators: [
    (Story) => (
      <div style={{ maxWidth: 1180, padding: 24, background: 'var(--color-bg-2)' }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof FamilyOverview>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Overview: Story = {};
