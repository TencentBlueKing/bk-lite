import { useEffect, useRef } from 'react';
import type { Meta, StoryObj } from '@storybook/react';
import { Button, Dropdown, Form, Tag, Input, Space } from 'antd';
import { DownOutlined, EllipsisOutlined, PlusOutlined } from '@ant-design/icons';
import CodeSnippet from '@/components/code-snippet';
import CompactEmptyState from '@/components/compact-empty-state';
import CustomTable from '@/components/custom-table';
import HttpEndpointDisplay from '@/components/http-endpoint-display';
import IntegrationAccessComplete from '@/components/integration-access-complete';
import { createMonitorK8sAccessCompletePreset } from '@/components/integration-access-complete/presets';
import IntegrationAutomaticConfigurationShell from '@/components/integration-automatic-configuration-shell';
import IntegrationCatalogCard from '@/components/integration-catalog-card';
import IntegrationCatalogWorkspaceShell from '@/components/integration-catalog-workspace-shell';
import IntegrationDetailLayoutShell from '@/components/integration-detail-layout-shell';
import IntegrationInstanceManagementShell from '@/components/integration-instance-management-shell';
import SectionHeader from '@/components/section-header';
import IntegrationConfigEditModal, {
  type IntegrationConfigEditModalRef,
} from '@/components/integration-config-edit-modal';
import IntegrationInstanceEditModal, {
  type IntegrationInstanceEditModalRef,
} from '@/components/integration-instance-edit-modal';
import IntegrationBatchEditModal, {
  type IntegrationBatchEditModalRef,
} from '@/components/integration-batch-edit-modal';
import IntegrationExcelImportModal, {
  type IntegrationExcelImportModalRef,
} from '@/components/integration-excel-import-modal';
import IntegrationStepCallout from '@/components/integration-step-callout';
import K8sAccessAssetFields from '@/components/k8s-access-asset-fields';
import { createMonitorK8sAccessAssetFieldsCopy } from '@/components/k8s-access-asset-fields/presets';
import K8sCollectorInstallStep from '@/components/k8s-collector-install-step';
import { createMonitorK8sCollectorInstallCopy } from '@/components/k8s-collector-install-step/presets';
import SnmpTrapGuidePanel from '@/components/snmp-trap-guide-panel';
import SearchActionBar from '@/components/search-action-bar';
import SemanticBadge from '@/components/semantic-badge';
import SourceOriginBadge from '@/components/source-origin-badge';
import TimeSelector from '@/components/time-selector';
import {
  integrationBatchEditColumns,
  integrationExcelImportColumns,
  integrationExcelImportColumnsWithInterval,
  integrationSingleCredentialColumn,
  integrationStoryNodeList,
} from './integration-auth.fixtures';
import { createK8sStoryT } from './k8s-story.fixtures';

const detailMenuItems = [
  {
    name: 'integration_configure',
    title: 'Configure',
    url: '/monitor/integration/list/detail/configure',
    icon: 'settings-fill',
    operation: [],
  },
  {
    name: 'integration_metric',
    title: 'Metrics',
    url: '/monitor/integration/list/detail/metric',
    icon: 'guanli',
    operation: [],
  },
];

interface IntegrationCatalogStoryItem {
  id: string;
  title: string;
  description: string;
  category: string;
  custom?: boolean;
}

const integrationCatalogStoryItems: IntegrationCatalogStoryItem[] = [
  {
    id: 'prometheus',
    title: 'Prometheus',
    description: 'Collect metrics, labels, and topology data from Prometheus targets.',
    category: 'Infrastructure',
  },
  {
    id: 'mysql-custom',
    title: 'MySQL Collector',
    description: 'Monitor custom database integrations with governed metadata badges.',
    category: 'Database',
    custom: true,
  },
];

const integrationCatalogTreeData = [
  { key: 'all', title: 'All', children: [] },
  { key: 'infra', title: 'Infrastructure', children: [] },
  { key: 'database', title: 'Database', children: [] },
];

const integrationInstanceTreeData = [
  { key: 'all', title: 'All', children: [] },
  { key: 'mysql', title: 'MySQL', children: [] },
  { key: 'nginx', title: 'Nginx', children: [] },
];

const integrationInstanceColumns = [
  { title: 'Name', dataIndex: 'name', key: 'name' },
  { title: 'Group', dataIndex: 'group', key: 'group' },
  { title: 'Collector', dataIndex: 'collector', key: 'collector' },
];

const integrationInstanceDataSource = [
  { id: '1', name: 'mysql-prod-01', group: 'Core DB', collector: 'Exporter' },
  { id: '2', name: 'nginx-edge-02', group: 'Ingress', collector: 'Agent' },
];

const IntegrationInstanceEditStoryHarness = ({ mode }: { mode: 'edit' | 'batch' }) => {
  const ref = useRef<IntegrationInstanceEditModalRef>(null);

  useEffect(() => {
    ref.current?.showModal({
      title: mode === 'edit' ? 'Edit instance' : 'Batch set group',
      type: mode,
      form:
        mode === 'edit'
          ? {
            instance_name: 'mysql-prod-01',
            organization: [1, 3],
            instance_id: 'instance-01',
          }
          : {
            keys: ['instance-01', 'instance-02', 'instance-03'],
            organization: [2],
          },
    });
  }, [mode]);

  return (
    <IntegrationInstanceEditModal
      ref={ref}
      onSuccess={() => undefined}
      nameLabel="Instance name"
      groupLabel="Group"
      getInstanceName={(form) =>
        String(form.instance_name || form.name || '')
      }
      submitEdit={async () => undefined}
      submitBatch={async () => undefined}
    />
  );
};

const presetT = createK8sStoryT({
  'monitor.integrations.k8s.accessCompleteSubDesc':
    'Review discovered assets now or continue with another onboarding flow from the catalog.',
  'monitor.integrations.k8s.viewClusterList': 'View assets',
  'monitor.integrations.k8s.addAnotherCluster': 'Add another source',
});

const FamilyOverview = () => {
  const [automaticForm] = Form.useForm();
  const configModalRef = useRef<IntegrationConfigEditModalRef>(null);
  const emptyConfigModalRef = useRef<IntegrationConfigEditModalRef>(null);
  const instanceModalRef = useRef<IntegrationInstanceEditModalRef>(null);
  const batchModalRef = useRef<IntegrationBatchEditModalRef>(null);
  const excelModalRef = useRef<IntegrationExcelImportModalRef>(null);

  return (
    <div className="space-y-6">
      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Catalog and detail shell"
          titleClassName="text-sm font-semibold"
          description="Shared entry surfaces for integration discovery and per-plugin detail navigation."
        />

        <div className="grid gap-6 xl:grid-cols-[360px_minmax(0,1fr)]">
          <div className="space-y-4">
            <IntegrationCatalogCard
              media={(
                <div className="flex h-14 w-14 min-w-[56px] items-center justify-center rounded-lg bg-[var(--color-fill-1)] text-lg font-semibold text-[var(--color-primary)]">
                  K8s
                </div>
              )}
              title="Kubernetes"
              details={(
                <>
                  <Tag>Containers</Tag>
                  <Tag>Managed</Tag>
                </>
              )}
              description="Discover cluster assets, install collectors, and connect metrics or logs through one governed integration surface."
              menu={(
                <Dropdown
                  menu={{
                    items: [
                      { key: 'edit', label: 'Edit' },
                      { key: 'delete', label: 'Delete', danger: true },
                    ],
                  }}
                  placement="bottomRight"
                  trigger={['click']}
                >
                  <Button type="text" icon={<EllipsisOutlined />} />
                </Dropdown>
              )}
              action={(
                <Button className="w-full rounded-md" icon={<PlusOutlined />} type="primary">
                  Connect
                </Button>
              )}
            />

            <IntegrationCatalogCard
              media={(
                <div className="flex h-14 w-14 min-w-[56px] items-center justify-center rounded-lg bg-[var(--color-fill-1)] text-lg font-semibold text-[var(--color-primary)]">
                  M
                </div>
              )}
              title="MySQL Collector"
              details={(
                <>
                  <Tag>Database</Tag>
                  <Tag>Self-built</Tag>
                </>
              )}
              description="Monitor custom database integrations with the same governed catalog card contract."
              action={(
                <Button className="w-full rounded-md" icon={<PlusOutlined />} type="primary">
                  Connect
                </Button>
              )}
            />
          </div>

          <div className="space-y-4">
            <IntegrationDetailLayoutShell
              summary={{
                title: 'Kubernetes',
                description:
                  'Configure onboarding, review collector state, and inspect the integration details for this plugin.',
                icon: 'kubernetes',
              }}
              menuItems={detailMenuItems}
              topSectionClassName="bg-[var(--color-bg-2)]"
              onBackButtonClick={() => undefined}
            >
              <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-6 text-sm text-[var(--color-text-2)]">
                Monitor integration detail content area
              </div>
            </IntegrationDetailLayoutShell>

            <IntegrationDetailLayoutShell
              summary={{
                title: 'Kubernetes',
                description:
                  'Review the log collection configuration and continue into the plugin-specific setup workflow.',
                icon: 'kubernetes',
              }}
              menuItems={[detailMenuItems[0]]}
              onBackButtonClick={() => undefined}
            >
              <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-6 text-sm text-[var(--color-text-2)]">
                Log integration detail content area
              </div>
            </IntegrationDetailLayoutShell>
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Catalog workspace workflows"
          titleClassName="text-sm font-semibold"
          description="Monitor and log integration list pages share the same catalog workspace shell; the stable differences live in sidebar mode, search width, and whether template actions are exposed."
        />

        <div className="space-y-4">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Log catalog workflow" titleClassName="text-sm font-semibold" />
            <IntegrationCatalogWorkspaceShell<IntegrationCatalogStoryItem>
              items={integrationCatalogStoryItems}
              getItemKey={(item) => item.id}
              treePanelProps={{
                showAllMenu: true,
                data: integrationCatalogTreeData,
                defaultSelectedKey: 'all',
                surface: 'panel',
                style: { width: 220, height: 'calc(100vh - 146px)' },
                onNodeSelect: () => undefined,
              }}
              search={(
                <SearchActionBar
                  spacing="flush"
                  searchProps={{
                    className: 'w-60',
                    allowClear: true,
                    enterButton: true,
                    placeholder: 'Search integrations...',
                  }}
                />
              )}
              emptyState={<CompactEmptyState description="No integrations found." className="py-6" />}
              renderItem={(item) => (
                <IntegrationCatalogCard
                  media={(
                    <div className="flex h-14 w-14 min-w-[56px] items-center justify-center rounded-lg bg-[var(--color-fill-1)] text-lg font-semibold text-[var(--color-primary)]">
                      {item.title.charAt(0)}
                    </div>
                  )}
                  title={item.title}
                  details={(
                    <>
                      <SemanticBadge
                        label={item.category}
                        textColor="var(--color-text-2)"
                        backgroundColor="color-mix(in srgb, var(--color-fill-5) 32%, transparent)"
                      />
                      {item.custom ? <SourceOriginBadge kind="custom" label="Custom" /> : null}
                    </>
                  )}
                  description={item.description}
                  action={(
                    <Button className="w-full rounded-md" icon={<PlusOutlined />} type="primary">
                      Connect
                    </Button>
                  )}
                />
              )}
            />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Monitor catalog workflow" titleClassName="text-sm font-semibold" />
            <IntegrationCatalogWorkspaceShell<IntegrationCatalogStoryItem>
              items={integrationCatalogStoryItems}
              getItemKey={(item) => item.id}
              sidebarMode="resizable"
              sidebarCollapseStorageKey="storybook.integration.catalog.workspace"
              sidebarContentClassName="h-[calc(100vh-146px)] overflow-y-auto bg-[var(--color-bg-1)] px-2.5 pb-2.5 pt-5"
              treePanelProps={{
                showAllMenu: true,
                data: integrationCatalogTreeData,
                defaultSelectedKey: 'all',
                draggable: true,
                onNodeSelect: () => undefined,
                onNodeDrag: () => undefined,
              }}
              search={(
                <SearchActionBar
                  spacing="flush"
                  searchProps={{
                    className: 'w-[400px]',
                    allowClear: true,
                    placeholder: 'Search integrations',
                    enterButton: false,
                  }}
                />
              )}
              actions={(
                <Button type="primary">
                  Create template
                </Button>
              )}
              emptyState={<CompactEmptyState description="No integrations found." className="py-6" />}
              renderItem={(item) => (
                <IntegrationCatalogCard
                  className="cursor-pointer"
                  media={(
                    <div className="flex h-14 w-14 min-w-[56px] items-center justify-center rounded-lg bg-[var(--color-fill-1)] text-lg font-semibold text-[var(--color-primary)]">
                      {item.title.charAt(0)}
                    </div>
                  )}
                  title={item.title}
                  details={(
                    <>
                      <SemanticBadge
                        label={item.category}
                        textColor="var(--color-text-2)"
                        backgroundColor="color-mix(in srgb, var(--color-fill-5) 32%, transparent)"
                      />
                      {item.custom ? <SourceOriginBadge kind="custom" label="Self-built" /> : null}
                    </>
                  )}
                  description={item.description}
                  menu={(
                    <Dropdown
                      menu={{
                        items: [
                          { key: 'edit', label: 'Edit' },
                          { key: 'delete', label: 'Delete', danger: true },
                        ],
                      }}
                      placement="bottomRight"
                      trigger={['click']}
                    >
                      <Button type="text" icon={<EllipsisOutlined />} />
                    </Dropdown>
                  )}
                  action={(
                    <Button className="w-full rounded-md" icon={<PlusOutlined />} type="primary">
                      Access
                    </Button>
                  )}
                />
              )}
            />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Catalog empty state" titleClassName="text-sm font-semibold" />
            <IntegrationCatalogWorkspaceShell<IntegrationCatalogStoryItem>
              items={[]}
              getItemKey={(item) => item.id}
              treePanelProps={{
                showAllMenu: true,
                data: integrationCatalogTreeData,
                defaultSelectedKey: 'all',
                surface: 'panel',
                style: { width: 220, height: 'calc(100vh - 146px)' },
                onNodeSelect: () => undefined,
              }}
              search={(
                <SearchActionBar
                  spacing="flush"
                  searchProps={{
                    className: 'w-60',
                    allowClear: true,
                    enterButton: true,
                    placeholder: 'Search integrations...',
                  }}
                />
              )}
              emptyState={<CompactEmptyState description="No integrations found." className="py-6" />}
              renderItem={() => null}
            />
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Editing workflows and supporting shells"
          titleClassName="text-sm font-semibold"
          description="Business integration workflows paired with their shared support surfaces. Instance editing, config editing, and batch updates all stay inside the integration governance lane."
        />

        <div className="flex flex-wrap gap-3">
          <Button
            type="primary"
            onClick={() => {
              instanceModalRef.current?.showModal({
                title: 'Edit instance',
                type: 'edit',
                form: {
                  name: 'mysql-prod-01',
                  organization: [1, 3],
                  id: 'instance-01',
                },
              });
            }}
          >
            Open instance modal
          </Button>
          <Button
            onClick={() => {
              configModalRef.current?.showModal({
                title: 'Update configuration',
                form: {
                  id: 'instance-01',
                  config_id: 'cfg-01',
                },
              });
            }}
          >
            Open config modal
          </Button>
          <Button
            onClick={() => {
              emptyConfigModalRef.current?.showModal({
                title: 'No editable config',
                form: {
                  id: 'instance-02',
                  config_id: 'cfg-empty',
                },
              });
            }}
          >
            Open empty config modal
          </Button>
          <Button
            onClick={() => {
              batchModalRef.current?.showModal({
                selectedRows: [],
                nodeList: integrationStoryNodeList,
                columns: integrationBatchEditColumns,
              });
            }}
          >
            Open batch edit
          </Button>
          <Button
            onClick={() => {
              batchModalRef.current?.showModal({
                title: 'Bulk edit',
                selectedRows: [
                  { id: 'node-a', auth_type: 'private_key' },
                  { id: 'node-b', auth_type: 'private_key' },
                ],
                hideFieldToggles: true,
                preEnabledFields: ['password'],
                initialAuthType: 'private_key',
                columns: integrationSingleCredentialColumn,
              });
            }}
          >
            Open single-field batch edit
          </Button>
          <Button
            onClick={() => {
              excelModalRef.current?.showModal({
                title: 'Import data',
                pluginName: 'mysql',
                nodeList: integrationStoryNodeList,
                columns: integrationExcelImportColumns,
              });
            }}
          >
            Open Excel import
          </Button>
          <Button
            onClick={() => {
              excelModalRef.current?.showModal({
                title: 'Import data',
                pluginName: 'mysql',
                nodeList: integrationStoryNodeList,
                columns: integrationExcelImportColumnsWithInterval,
              });
            }}
          >
            Open interval Excel import
          </Button>
        </div>

        <IntegrationInstanceEditModal
          ref={instanceModalRef}
          onSuccess={() => undefined}
          nameLabel="Instance name"
          groupLabel="Group"
          getInstanceName={(form) => String(form.name || '')}
          submitEdit={async () => undefined}
          submitBatch={async () => undefined}
        />

        <IntegrationConfigEditModal
          ref={configModalRef}
          onSuccess={() => undefined}
          loadConfig={async () => ({
            env_config: { endpoint: '10.0.0.10:9200', protocol: 'https' },
          })}
          getFormItems={() => (
            <>
              <Form.Item label="Endpoint" name="endpoint" rules={[{ required: true }]}>
                <Input />
              </Form.Item>
              <Form.Item label="Protocol" name="protocol" rules={[{ required: true }]}>
                <Input />
              </Form.Item>
            </>
          )}
          getDefaultValues={({ loadedConfig }) => {
            const config = loadedConfig as { env_config?: Record<string, unknown> };
            return config.env_config || {};
          }}
          submitConfig={async () => undefined}
        />

        <IntegrationConfigEditModal
          ref={emptyConfigModalRef}
          onSuccess={() => undefined}
          emptyDescription="No configuration schema is available for this collector."
          loadConfig={async () => null}
          getFormItems={() => null}
          getDefaultValues={() => ({})}
          submitConfig={async () => undefined}
        />

        <IntegrationBatchEditModal
          ref={batchModalRef}
          onSuccess={() => undefined}
        />

        <IntegrationExcelImportModal
          ref={excelModalRef}
          onSuccess={() => undefined}
        />

        <div className="grid gap-4 xl:grid-cols-2">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Edit single instance" titleClassName="text-sm font-semibold" />
            <IntegrationInstanceEditStoryHarness mode="edit" />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Batch assign group" titleClassName="text-sm font-semibold" />
            <IntegrationInstanceEditStoryHarness mode="batch" />
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Instance management workflows"
          titleClassName="text-sm font-semibold"
          description="Log receive and monitor asset pages share the same instance-management shell; the stable differences live in sidebar mode, primary actions, row-selection policy, and which page-local modals mount beside the table."
        />

        <div className="space-y-4">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Log receive workflow" titleClassName="text-sm font-semibold" />
            <IntegrationInstanceManagementShell
              treePanelProps={{
                data: integrationInstanceTreeData,
                showAllMenu: true,
                defaultSelectedKey: 'all',
                surface: 'panel',
                style: { width: 236, height: 'calc(100vh - 146px)' },
                onNodeSelect: () => undefined,
              }}
              contentClassName="w-[calc(100vw-236px)] min-w-[1040px] bg-[var(--color-bg-1)] p-5"
              searchProps={{
                allowClear: true,
                className: 'w-[320px]',
                placeholder: 'Search instances',
                enterButton: false,
              }}
              actions={(
                <div className="flex items-center gap-2">
                  <Dropdown
                    menu={{ items: [{ key: 'edit', label: 'Batch edit' }] }}
                  >
                    <Button>
                      <Space>
                        Action
                        <DownOutlined />
                      </Space>
                    </Button>
                  </Dropdown>
                  <TimeSelector
                    onlyRefresh
                    onFrequenceChange={() => undefined}
                    onRefresh={() => undefined}
                  />
                </div>
              )}
              columns={integrationInstanceColumns}
              dataSource={integrationInstanceDataSource}
              rowKey="id"
              rowSelection={{
                selectedRowKeys: ['1'],
                onChange: () => undefined,
              }}
              scroll={{ y: 420, x: 960 }}
              modal={(
                <>
                  <div className="rounded border border-dashed border-[var(--color-border-2)] p-3 text-sm text-[var(--color-text-2)]">
                    Edit config modal mount
                  </div>
                  <div className="rounded border border-dashed border-[var(--color-border-2)] p-3 text-sm text-[var(--color-text-2)]">
                    Edit instance modal mount
                  </div>
                </>
              )}
            />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Monitor asset workflow" titleClassName="text-sm font-semibold" />
            <IntegrationInstanceManagementShell
              sidebarMode="resizable"
              sidebarCollapseStorageKey="storybook.integration.instance.workspace"
              sidebarContentClassName="h-[calc(100vh-146px)] overflow-y-auto bg-[var(--color-bg-1)] px-2.5 pb-2.5 pt-5"
              treePanelProps={{
                data: integrationInstanceTreeData,
                defaultSelectedKey: 'mysql',
                onNodeSelect: () => undefined,
              }}
              searchProps={{
                allowClear: true,
                className: 'w-[320px]',
                placeholder: 'Search integrations',
                enterButton: false,
              }}
              actions={(
                <div className="flex items-center gap-2">
                  <Button
                    type="primary"
                    icon={<PlusOutlined />}
                  >
                    Access
                  </Button>
                  <Dropdown
                    menu={{ items: [{ key: 'delete', label: 'Delete' }] }}
                  >
                    <Button>
                      <Space>
                        Action
                        <DownOutlined />
                      </Space>
                    </Button>
                  </Dropdown>
                  <TimeSelector
                    onlyRefresh
                    onFrequenceChange={() => undefined}
                    onRefresh={() => undefined}
                  />
                </div>
              )}
              columns={integrationInstanceColumns}
              dataSource={integrationInstanceDataSource}
              rowKey="id"
              rowSelection={{
                selectedRowKeys: ['1'],
                onChange: () => undefined,
              }}
              scroll={{ y: 420, x: 'max-content' }}
              modal={(
                <>
                  <div className="rounded border border-dashed border-[var(--color-border-2)] p-3 text-sm text-[var(--color-text-2)]">
                    Edit config modal mount
                  </div>
                  <div className="rounded border border-dashed border-[var(--color-border-2)] p-3 text-sm text-[var(--color-text-2)]">
                    Edit instance modal mount
                  </div>
                  <div className="rounded border border-dashed border-[var(--color-border-2)] p-3 text-sm text-[var(--color-text-2)]">
                    Template config drawer mount
                  </div>
                </>
              )}
            />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Instance empty state" titleClassName="text-sm font-semibold" />
            <IntegrationInstanceManagementShell
              treePanelProps={{
                data: integrationInstanceTreeData,
                showAllMenu: true,
                defaultSelectedKey: 'all',
                surface: 'panel',
                style: { width: 236, height: 'calc(100vh - 146px)' },
                onNodeSelect: () => undefined,
              }}
              contentClassName="w-[calc(100vw-236px)] min-w-[1040px] bg-[var(--color-bg-1)] p-5"
              searchProps={{
                allowClear: true,
                className: 'w-[320px]',
                placeholder: 'Search instances',
                enterButton: false,
              }}
              actions={(
                <div className="flex items-center gap-2">
                  <Dropdown
                    menu={{ items: [{ key: 'edit', label: 'Batch edit' }] }}
                  >
                    <Button>
                      <Space>
                        Action
                        <DownOutlined />
                      </Space>
                    </Button>
                  </Dropdown>
                </div>
              )}
              columns={integrationInstanceColumns}
              dataSource={[]}
              rowKey="id"
              scroll={{ y: 420, x: 960 }}
              emptyText={<CompactEmptyState description="No instances found." className="py-8" />}
            />
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Onboarding flow contracts"
          titleClassName="text-sm font-semibold"
          description="Shared onboarding and completion surfaces that carry integration-specific semantics across automatic configuration and guided access flows."
        />

        <div className="grid gap-6 xl:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
          <div className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <IntegrationStepCallout
              title="Prerequisites"
              description="Confirm the environment baseline before generating commands or importing monitored objects."
              items={[
                'Required node or cluster permissions are available',
                'The selected runtime or protocol matches the target source',
                'The owning organization is known before saving the flow',
              ]}
            />

            <IntegrationAutomaticConfigurationShell
              form={automaticForm}
              configurationTitle="Configuration"
              basicInformationTitle="Basic information"
              formItems={(
                <div className="rounded-lg bg-[var(--color-fill-1)] p-4 text-sm text-[var(--color-text-2)]">
                  Shared integration-specific form content renders here.
                </div>
              )}
              formItemsWrapperClassName="w-full"
              tableSectionClassName="w-full"
              monitoredObjectTitle="Monitored objects"
              importButtonLabel="Import"
              onImport={() => undefined}
              batchOperationLabel="Batch operation"
              batchMenuItems={[
                { key: 'edit', label: 'Batch edit' },
                { key: 'delete', label: 'Batch delete' },
              ]}
              onBatchMenuClick={() => undefined}
              batchDisabled={false}
              tableFieldName="nodes"
              tableFieldRules={[{ required: true, message: 'Required' }]}
              tableNode={(
                <CustomTable
                  dataSource={[
                    { key: '1', node: 'node-a', instance: 'primary' },
                    { key: '2', node: 'node-b', instance: 'secondary' },
                  ]}
                  columns={[
                    { title: 'Node', dataIndex: 'node', key: 'node' },
                    { title: 'Instance', dataIndex: 'instance', key: 'instance' },
                  ]}
                  rowKey="key"
                  pagination={false}
                />
              )}
              confirmButtonLabel="Confirm"
              onConfirm={() => undefined}
            />

            <IntegrationAutomaticConfigurationShell
              form={automaticForm}
              emptyState={{
                description: 'No configuration data',
              }}
              configurationTitle="Install configuration"
              monitoredObjectTitle="Installation information"
              importButtonLabel="Import"
              onImport={() => undefined}
              batchOperationLabel="Batch operation"
              batchMenuItems={[{ key: 'edit', label: 'Batch edit' }]}
              onBatchMenuClick={() => undefined}
              batchDisabled={true}
              tableFieldName="nodes"
              confirmButtonLabel="Install (2)"
              onConfirm={() => undefined}
              secondaryActions={<Button>Cancel</Button>}
              actionsWrapperClassName="mt-[10px]"
            >
              <div className="mt-4 rounded-[12px] border border-dashed border-[var(--color-border-2)] p-4 text-sm text-[var(--color-text-2)]">
                Product-specific modal refs and follow-up actions still mount outside the shell while the shared onboarding contract stays stable.
              </div>
            </IntegrationAutomaticConfigurationShell>
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <IntegrationAccessComplete
              {...createMonitorK8sAccessCompletePreset(presetT, {
                onPrimaryAction: () => undefined,
                onSecondaryAction: () => undefined,
              })}
            />
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Shared protocol-specific guidance"
          titleClassName="text-sm font-semibold"
          description="Business guidance panels that carry protocol semantics but are reused across integration domains instead of living as one-app implementations."
        />

        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
          <SnmpTrapGuidePanel
            nodeLabel="Node"
            nodeHint="Select the node that hosts snmptrapd so the same guidance contract can serve both alarm and log integration flows."
            nodePlaceholder="Please select"
            selectedNodeId={1}
            nodeOptions={[
              { label: 'collector-a (172.24.0.5)', value: 1 },
              { label: 'collector-b (172.24.0.6)', value: 2 },
            ]}
            onNodeChange={() => undefined}
            emptyDescription="No data"
            guideTitle="Access Guide"
            steps={[
              {
                key: 'trap-target',
                title: 'Configure Trap Target Address',
                description: 'Configure the following target address on the device to send Trap messages.',
                details: [
                  { label: 'Target IP', value: '172.24.0.5' },
                  { label: 'Target Port', value: '162', bordered: false },
                ],
              },
              {
                key: 'mib',
                title: 'Configure MIB Files',
                description: 'Obtain the MIB files from the device vendor and place them in the following directory on the node.',
                details: [
                  { label: 'MIB File Path', value: '/usr/share/mibs', bordered: false },
                ],
              },
            ]}
            maxHeightClassName="max-h-none"
          />
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Kubernetes onboarding"
          titleClassName="text-sm font-semibold"
          description="K8s-specific setup steps layer on top of the generic integration family without creating a second disconnected contract center."
        />

        <div className="grid gap-6 xl:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
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

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <K8sCollectorInstallStep
              installCommand="kubectl apply -f collector.yaml"
              copy={createMonitorK8sCollectorInstallCopy(presetT)}
              onVerifyStatus={async () => false}
              onPrev={() => undefined}
              onNext={() => undefined}
              onOpenCommonIssues={() => undefined}
            />
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Access guide documentation surfaces"
          titleClassName="text-sm font-semibold"
          description="Integration access guides now converge on the same endpoint and read-only code-example surfaces. Alarm and monitor can keep different business copy while reusing the governed display contracts."
        />

        <div className="grid gap-6 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
          <div className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="flush" title="Shared endpoint surface" titleClassName="text-sm font-medium" />
            <HttpEndpointDisplay
              method="POST"
              endpoint="https://bk-lite.example.com/api/integration/custom/collect"
              copySuccessMessage="Endpoint copied"
              endpointClassName="whitespace-normal break-all"
            />
          </div>

          <div className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="flush" title="Shared code-example surface" titleClassName="text-sm font-medium" />
            <CodeSnippet
              value={`curl -X POST 'https://bk-lite.example.com/api/integration/custom/collect' \\
  -H 'Content-Type: text/plain' \\
  --data-binary 'cpu_usage,organization_id=2001,instance_id=host-01 value=0.87 1719811200000'`}
              copyable
              tone="inverse"
              maxHeight={220}
            />
          </div>
        </div>
      </section>
    </div>
  );
};

const meta = {
  title: 'Business/Integrations/FamilyOverview',
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
