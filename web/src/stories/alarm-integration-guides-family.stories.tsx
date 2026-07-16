import type { Meta, StoryObj } from '@storybook/nextjs';
import { Alert } from 'antd';
import AlarmIntegrationGuideCredentialsPanel from '@/app/alarm/components/integration-guide/CredentialsPanel';
import AlarmIntegrationGuideSectionPanel from '@/app/alarm/components/integration-guide/SectionPanel';
import DetailListPanel from '@/components/detail-list-panel';
import K8sGuide from '@/app/alarm/components/alarm-k8s-guide';
import SectionHeader from '@/components/section-header';
import ZabbixGuide from '@/app/alarm/components/alarm-zabbix-guide';
import type {
  AlertSourceIntegrationGuide,
  K8sMeta,
  SourceItem,
} from '@/app/alarm/types/integration-guide';
import SnmpTrapGuidePanel from '@/app/alarm/components/integration-guide/SnmpTrapGuidePanel';

const k8sSource: SourceItem = {
  id: 1,
  event_count: 42,
  last_event_time: '2026-06-30T10:00:00Z',
  created_at: '2026-06-29T10:00:00Z',
  updated_at: '2026-06-30T10:00:00Z',
  created_by: 'alice',
  updated_by: 'alice',
  name: 'Kubernetes Events',
  source_id: 'k8s',
  source_type: 'kubernetes',
  config: {
    url: '',
    params: {},
    auth: {
      type: '',
      token: '',
      password: '',
      username: '',
      secret_key: '',
    },
    method: 'POST',
    headers: {},
    timeout: 30,
    content_type: 'application/json',
    examples: {},
    event_fields_mapping: {},
    event_fields_desc_mapping: {},
  },
  secret: 'alarm-secret',
  logo: null,
  access_type: 'push',
  is_active: true,
  is_effective: true,
  description: 'Kubernetes event source',
};

const k8sMeta: K8sMeta = {
  source_id: 'k8s',
  name: 'Kubernetes',
  description: 'Deploy the exporter to collect events from the target cluster.',
  receiver_url: 'https://bk-lite.example.com/api/alarm/k8s/receive',
  method: 'POST',
  headers: {
    SECRET: 'alarm-secret',
  },
  push_source_id_default: 'k8s',
  push_source_id_configurable: true,
  image_reference: 'docker.io/bk-lite/kubernetes-event-exporter:latest',
  download_files: [
    {
      key: 'deploy_yaml',
      file_name: 'bk-lite-k8s-event-exporter.deploy.yaml',
      display_name: 'Download deployment YAML',
    },
  ],
  notes: [
    'Confirm the selected organization secret before downloading deployment materials.',
    'Return to the event list after rollout to verify ingestion.',
  ],
};

const zabbixGuide: AlertSourceIntegrationGuide = {
  source_type: 'zabbix',
  source_id: 'zabbix',
  webhook_url: 'https://legacy.example.com/api/alarm/zabbix/webhook',
  headers: {
    SECRET: 'legacy-zabbix-secret',
    'Content-Type': 'application/json',
  },
  description:
    'This guide keeps the webhook, parameter mapping, and verification steps aligned for Zabbix integrations.',
  parameter_guidance: [
    { name: 'URL', value: 'https://legacy.example.com/api/alarm/zabbix/webhook', required: true },
    { name: 'SECRET', value: 'legacy-zabbix-secret', required: true },
    { name: 'SOURCE_ID', value: 'zabbix', required: true },
  ],
  field_mappings: [
    { bk_lite_field: 'title', upstream_source: '{ALERT.SUBJECT}' },
    { bk_lite_field: 'description', upstream_source: '{ALERT.MESSAGE}' },
  ],
  script_template: `curl -X POST "https://legacy.example.com/api/alarm/zabbix/webhook" \\
  -H "SECRET: legacy-zabbix-secret"`,
  setup_steps: [
    {
      title: 'Create a media type',
      items: ['Create the webhook entry in Zabbix.', 'Paste the governed script template.'],
    },
  ],
  verification: {
    curl_check: {
      title: 'Webhook reachability',
      summary: 'Confirm BK-Lite can receive a test event.',
      expected_results: ['HTTP response is 2xx'],
      steps: ['Run the generated curl command'],
    },
  },
  troubleshooting: [
    {
      symptom: 'No events arrive',
      possible_causes: ['Secret mismatch'],
      resolutions: ['Regenerate the selected team secret'],
    },
  ],
};

const FamilyOverview = () => {
  return (
    <div className="space-y-6">
      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          title="Guide family boundary"
          description="Alarm integration detail uses three distinct guide surfaces: cluster deployment guidance for Kubernetes, device routing guidance for SNMP Trap, and webhook mapping guidance for Zabbix. They share alarm-domain onboarding semantics, but each keeps a source-specific interaction model."
        />
      </section>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="space-y-4">
          <AlarmIntegrationGuideSectionPanel
            title="Governed connection-values shell"
            description="The guide family now shares one business section contract for endpoint values, mapping snippets, and notes."
            className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)]"
          >
            <DetailListPanel
              className="overflow-hidden rounded-[16px] border border-[var(--color-border-1)] bg-[var(--color-fill-1)]"
              labelWidthClassName="w-40"
              items={[
                { label: 'URL', value: 'https://bk-lite.example.com/api/alarm/zabbix/webhook' },
                { label: 'SECRET', value: 'team-secret-value' },
                { label: 'SOURCE_ID', value: 'zabbix' },
              ]}
            />
          </AlarmIntegrationGuideSectionPanel>

          <AlarmIntegrationGuideSectionPanel
            title="Guide Notes"
            description="Notes"
            headerClassName="px-5 pt-5"
            bodyClassName="px-5 pb-5"
            className="rounded-[18px] border border-[var(--color-border-1)] bg-[var(--color-fill-1)]"
            descriptionClassName="text-[11px] font-medium uppercase tracking-[0.08em] text-[var(--color-primary)]"
          >
            <div className="mt-3 space-y-2">
              <div className="flex items-start gap-2 text-[13px] leading-6 text-[var(--color-text-2)]">
                <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-primary)]" />
                <span>Confirm the selected organization secret before rollout.</span>
              </div>
              <div className="flex items-start gap-2 text-[13px] leading-6 text-[var(--color-text-2)]">
                <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-primary)]" />
                <span>Return to the event list after rollout to verify ingestion.</span>
              </div>
            </div>
          </AlarmIntegrationGuideSectionPanel>
        </div>

        <AlarmIntegrationGuideCredentialsPanel title="Governed credentials surface">
          <div className="space-y-3">
            <Alert
              type="info"
              showIcon
              message="Selected team secret"
              description="Kubernetes, Zabbix, and the alarm integration detail page now place operator guidance inside the same credentials panel contract."
            />
            <div className="rounded-[8px] border border-[var(--color-border-1)] bg-[var(--color-bg-1)] p-3 text-[13px] text-[var(--color-text-2)]">
              Example payloads and secret previews can be composed inside the same governed credentials surface.
            </div>
          </div>
        </AlarmIntegrationGuideCredentialsPanel>
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
          <SectionHeader title="Kubernetes deployment guide" />
          <div className="space-y-4">
            <div style={{ height: 720 }}>
              <K8sGuide
                source={k8sSource}
                meta={k8sMeta}
                selectedTeamSecret="team-secret-value"
                credentialsSlot={(
                  <Alert
                    type="info"
                    showIcon
                    message="Selected organization"
                    description="Platform Team uses a dedicated guide secret before downloading deployment YAML."
                  />
                )}
                onDownload={async () => undefined}
              />
            </div>

            <div style={{ height: 720 }}>
              <K8sGuide
                source={k8sSource}
                meta={k8sMeta}
                selectedTeamSecret={undefined}
                credentialsSlot={(
                  <Alert
                    type="warning"
                    showIcon
                    message="No team secret selected"
                    description="Operators must choose a secret before exporting deployment materials."
                  />
                )}
                onDownload={async () => undefined}
              />
            </div>

            <div style={{ height: 360 }}>
              <K8sGuide
                source={undefined}
                meta={undefined}
                selectedTeamSecret={undefined}
                credentialsSlot={undefined}
                onDownload={async () => undefined}
              />
            </div>
          </div>
        </section>

        <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
          <SectionHeader title="SNMP and Zabbix guides" />
          <div className="space-y-4">
            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
              <SnmpTrapGuidePanel
                nodeLabel="Node"
                nodeHint="Select the node hosting snmptrapd."
                nodePlaceholder="Please select"
                nodeOptions={[
                  { label: 'collector-a (172.24.0.5)', value: 1 },
                  { label: 'collector-b (172.24.0.6)', value: 2 },
                ]}
                selectedNodeId={1}
                onNodeChange={() => undefined}
                emptyDescription="No data"
                guideTitle="Access Guide"
                steps={[
                  {
                    key: 'trap-target',
                    title: 'Configure Trap Target Address',
                    description: 'Send Trap messages to the selected node.',
                    details: [
                      { label: 'Target IP', value: '172.24.0.5' },
                      { label: 'Target Port', value: '162', bordered: false },
                    ],
                  },
                ]}
                maxHeightClassName="max-h-none"
              />
            </div>

            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-3">
              <div className="space-y-4">
                <div style={{ height: 720 }}>
                  <ZabbixGuide
                    guide={zabbixGuide}
                    selectedTeamSecret="team-secret-value"
                    credentialsSlot={(
                      <Alert
                        type="info"
                        showIcon
                        message="Selected team secret"
                        description="The selected secret replaces the legacy webhook header before operators save the media type."
                      />
                    )}
                  />
                </div>

                <div style={{ height: 720 }}>
                  <ZabbixGuide
                    guide={zabbixGuide}
                    selectedTeamSecret={undefined}
                    credentialsSlot={(
                      <Alert
                        type="warning"
                        showIcon
                        message="Missing team secret"
                        description="The guide falls back to legacy placeholders until an operator selects a secret."
                      />
                    )}
                  />
                </div>

                <div style={{ height: 320 }}>
                  <ZabbixGuide
                    guide={undefined}
                    selectedTeamSecret={undefined}
                    credentialsSlot={undefined}
                  />
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
};

const meta = {
  title: 'Business/Alarm/Integrations/Guides/FamilyOverview',
  component: FamilyOverview,
  decorators: [
    (Story) => (
      <div style={{ maxWidth: 1280, padding: 24, background: 'var(--color-bg-2)' }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof FamilyOverview>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Overview: Story = {};
