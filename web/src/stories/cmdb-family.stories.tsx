import type { Meta, StoryObj } from '@storybook/react';
import AutoAssociationMatchPairGroup from '@/components/auto-association-match-pair-group';
import ChartEmptyState from '@/components/chart-empty-state';
import CmdbConfigFileCompareDrawer from '@/components/cmdb-config-file-compare-drawer';
import CmdbCredentialPoolEditor from '@/components/cmdb-credential-pool-editor';
import CompactEmptyState from '@/components/compact-empty-state';
import DetailListPanel from '@/components/detail-list-panel';
import SectionHeader from '@/components/section-header';
import StructuredDataPreview from '@/components/structured-data-preview';
import SubscriptionDrawer from '@/components/cmdb-subscription-drawer';
import { UserInfoContext } from '@/context/userInfo';

const subscriptionRules = [
  {
    id: 101,
    name: 'Host change notifications',
    organization: 1,
    model_id: 'bk_host',
    filter_type: 'instances',
    instance_filter: { instance_ids: [12, 29, 41] },
    trigger_types: ['attribute_change'],
    trigger_config: { attribute_change: { fields: ['bk_inst_name', 'bk_cloud_id'] } },
    recipients: { users: [1001, 1002] },
    channel_ids: [11],
    is_enabled: true,
    last_triggered_at: '2026-06-29T18:20:00Z',
    last_check_time: '2026-06-29T18:10:00Z',
    created_by: 'ops-admin',
    created_at: '2026-06-15T08:00:00Z',
    updated_by: 'ops-admin',
    updated_at: '2026-06-29T18:20:00Z',
    can_manage: true,
  },
];

const configFileVersions = [
  {
    id: 101,
    collect_task_id: 8,
    instance_id: 'host-001',
    model_id: 'bk_host',
    version: 'v3',
    file_path: '/etc/nginx/nginx.conf',
    file_name: 'nginx.conf',
    content_hash: 'hash-3',
    content_key: 'content-3',
    file_size: 2048,
    status: 'success',
    error_message: '',
    created_at: '2026-06-30T08:40:00Z',
  },
  {
    id: 102,
    collect_task_id: 8,
    instance_id: 'host-001',
    model_id: 'bk_host',
    version: 'v2',
    file_path: '/etc/nginx/nginx.conf',
    file_name: 'nginx.conf',
    content_hash: 'hash-2',
    content_key: 'content-2',
    file_size: 1880,
    status: 'success',
    error_message: '',
    created_at: '2026-06-28T07:10:00Z',
  },
];

const FamilyOverview = () => {
  return (
    <div className="space-y-6">

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Auto-association rule semantics"
          titleClassName="text-sm font-semibold"
          description="AutoAssociationMatchPairGroup provides the shared compact display for CMDB field-match pairs across rule detail and rule editing surfaces."
        />

        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
          <AutoAssociationMatchPairGroup
            items={[
              { key: 'hostname-ip', label: 'hostname = ip' },
              { key: 'name-instance_id', label: 'name = instance_id' },
            ]}
          />
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Discovery credential workflow"
          titleClassName="text-sm font-semibold"
          description="CMDB auto-discovery tasks now share one governed credential-pool editor across SSH, SQL, SNMP, cloud, VM, config-file, and IPMI collection flows instead of carrying page-local card layouts."
        />

        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
          <div className="space-y-4">
            <div className="space-y-2">
              <div className="text-sm font-medium text-[var(--color-text-1)]">SSH fallback order</div>
              <CmdbCredentialPoolEditor
                credentialShape="ssh"
                editMode
                value={[
                  { username: 'root', password: '******', port: '22' },
                  { username: 'ops-runner', password: '******', port: '2222' },
                ]}
                onChange={() => undefined}
              />
            </div>

            <div className="space-y-2">
              <div className="text-sm font-medium text-[var(--color-text-1)]">SNMP v3 secure credentials</div>
              <CmdbCredentialPoolEditor
                credentialShape="snmp"
                editMode
                value={[
                  {
                    version: 'v3',
                    snmp_port: '161',
                    level: 'authPriv',
                    username: 'snmp-admin',
                    authkey: '******',
                    integrity: 'sha',
                    privacy: 'aes',
                    privkey: '******',
                  },
                ]}
                onChange={() => undefined}
              />
            </div>

            <div className="space-y-2">
              <div className="text-sm font-medium text-[var(--color-text-1)]">Cloud credential single entry</div>
              <CmdbCredentialPoolEditor
                credentialShape="cloud"
                editMode
                showCount={false}
                value={[
                  {
                    accessKey: 'AKIDEXAMPLE001',
                    accessSecret: '******',
                    regionId: 'cn-shanghai',
                    regionName: 'cn-shanghai',
                  },
                ]}
                onChange={() => undefined}
                cloudRegionOptions={[
                  { label: 'cn-shanghai', value: 'cn-shanghai' },
                  { label: 'cn-beijing', value: 'cn-beijing' },
                ]}
              />
            </div>
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Discovery detail empty-state contract"
          titleClassName="text-sm font-semibold"
          description="CMDB collection detail and visualization views now expose governed business empties for no raw data, no topology facts, and missing topology canvases instead of carrying page-local fallback markup."
        />

        <div className="grid gap-4 xl:grid-cols-3">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Collection raw data" titleClassName="text-sm font-medium" />
            <div className="space-y-3">
              <DetailListPanel
                labelWidthClassName="w-32"
                items={[
                  { label: 'instance_id', value: 'host-01', copyable: false },
                  { label: 'source_protocol', value: 'snmp', copyable: false },
                  {
                    label: 'payload',
                    copyable: false,
                    displayValue: (
                      <StructuredDataPreview
                        value={{
                          sysName: 'prod-host-01',
                          sysLocation: 'hangzhou-a',
                          cpu: 92.4,
                        }}
                        maxHeight="10rem"
                        className="rounded-md"
                      />
                    ),
                  },
                ]}
              />
              <CompactEmptyState description="No raw collection data is available for this task yet." className="py-6" />
            </div>
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Topology facts" titleClassName="text-sm font-medium" />
            <CompactEmptyState description="No topology facts were generated for the selected collection task." className="py-8" />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Visualization canvas" titleClassName="text-sm font-medium" />
            <ChartEmptyState description="No topology links are available for this asset." compact style={{ height: '100%' }} />
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Subscription workflow"
          titleClassName="text-sm font-semibold"
          description="Asset list and asset detail pages already share one subscription-management drawer. Storybook now exposes that rule-management contract directly instead of leaving it implicit behind page actions."
        />

        <UserInfoContext.Provider
          value={{
            loading: false,
            roles: [],
            groups: [],
            groupTree: [],
            selectedGroup: { id: 1, name: 'Frontend Ops' } as any,
            flatGroups: [
              { id: 1, name: 'Frontend Ops' },
              { id: 2, name: 'Cloud Platform' },
            ] as any,
            isSuperUser: true,
            isFirstLogin: false,
            userId: '1001',
            username: 'ops-admin',
            displayName: 'Ops Admin',
            setSelectedGroup: () => undefined,
            refreshUserInfo: async () => undefined,
          }}
        >
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SubscriptionDrawer
              open
              onClose={() => undefined}
              modelId="bk_host"
              modelName="Host"
              subscriptionListController={{
                rules: subscriptionRules as any,
                loading: false,
                pagination: {
                  current: 1,
                  pageSize: 10,
                  total: subscriptionRules.length,
                },
                fetchRules: async () => undefined,
                refresh: async () => undefined,
              }}
              subscriptionMutationController={{
                submitting: false,
                createRule: async () => undefined,
                updateRule: async () => undefined,
                deleteRule: async () => undefined,
                toggleRule: async () => undefined,
              }}
              formRuntime={{
                userList: [
                  { id: '1001', username: 'ops-admin', display_name: 'Ops Admin' },
                  { id: '1002', username: 'oncall-a', display_name: 'Oncall A' },
                ],
                modelList: [
                  { model_id: 'bk_host', model_name: 'Host' },
                  { model_id: 'bk_process', model_name: 'Process' },
                ],
                cloudOptions: [
                  { proxy_id: '1', proxy_name: 'Shanghai' },
                ],
                searchInstances: async () => ({
                  insts: [
                    { _id: 12, inst_name: 'gateway-01' },
                    { _id: 29, inst_name: 'worker-29' },
                  ],
                }),
                getModelAttrGroupsFullInfo: async () => ({
                  groups: [
                    {
                      attrs: [
                        { attr_id: 'bk_inst_name', attr_name: 'Instance Name', attr_type: 'str' },
                        { attr_id: 'bk_cloud_id', attr_name: 'Cloud Region', attr_type: 'cloud' },
                      ],
                    },
                  ],
                }),
                getModelAssociations: async () => [
                  { src_model_id: 'bk_host', dst_model_id: 'bk_process' },
                ],
                loadChannelOptions: async () => [{ label: 'Email', value: 11 }],
              }}
            />
          </div>
        </UserInfoContext.Provider>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Config-file compare workflow"
          titleClassName="text-sm font-semibold"
          description="The config-file version compare drawer is now treated as a governed CMDB business workbench. Thin view wrappers stay page-local, while the synchronized diff contract is centralized in Storybook."
        />

        <div className="overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)]">
          <div className="space-y-4 p-4">
            <div style={{ height: 700 }}>
              <CmdbConfigFileCompareDrawer
                open
                loading={false}
                compareTarget={{
                  latest_version_id: 101,
                  file_path: '/etc/nginx/nginx.conf',
                  file_name: 'nginx.conf',
                  collect_task_id: 8,
                  latest_version: 'v3',
                  latest_status: 'success',
                  latest_created_at: '2026-06-30T08:40:00Z',
                }}
                versionList={configFileVersions}
                leftVersionId={101}
                rightVersionId={102}
                leftContent={[
                  'http {',
                  '  include       mime.types;',
                  '  default_type  application/octet-stream;',
                  '  sendfile      on;',
                  '  keepalive_timeout  75;',
                  '}',
                ].join('\n')}
                rightContent={[
                  'http {',
                  '  include       mime.types;',
                  '  default_type  text/plain;',
                  '  sendfile      on;',
                  '  client_max_body_size 20m;',
                  '}',
                ].join('\n')}
                onClose={() => undefined}
                onLeftVersionChange={() => undefined}
                onRightVersionChange={() => undefined}
              />
            </div>

            <div style={{ height: 700 }}>
              <CmdbConfigFileCompareDrawer
                open
                loading={false}
                compareTarget={{
                  latest_version_id: 101,
                  file_path: '/etc/nginx/nginx.conf',
                  file_name: 'nginx.conf',
                  collect_task_id: 8,
                  latest_version: 'v3',
                  latest_status: 'success',
                  latest_created_at: '2026-06-30T08:40:00Z',
                }}
                versionList={configFileVersions}
                leftVersionId={101}
                rightVersionId={undefined}
                leftContent={[
                  'http {',
                  '  include       mime.types;',
                  '  default_type  application/octet-stream;',
                  '  sendfile      on;',
                  '  keepalive_timeout  75;',
                  '}',
                ].join('\n')}
                rightContent=""
                onClose={() => undefined}
                onLeftVersionChange={() => undefined}
                onRightVersionChange={() => undefined}
              />
            </div>
          </div>
        </div>
      </section>
    </div>
  );
};

const meta = {
  title: 'Business/CMDB/FamilyOverview',
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
