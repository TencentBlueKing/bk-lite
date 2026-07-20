import type { Meta, StoryObj } from '@storybook/nextjs';
import { Button, Space } from 'antd';
import OpsAnalysisImportModal from '@/app/ops-analysis/components/ops-analysis-import-modal';
import OpsAnalysisSettingsListShell from '@/app/ops-analysis/components/ops-analysis-settings-list-shell';
import type {
  ImportSubmitResponse,
  PrecheckResponse,
} from '@/app/ops-analysis/components/ops-analysis-import-modal/contracts';

const precheckResponse: PrecheckResponse = {
  valid: true,
  counts: {
    total: 3,
    by_type: {
      dashboard: 1,
      topology: 1,
      architecture: 1,
      screen: 0,
      report: 0,
      networkTopology: 0,
      datasource: 0,
      namespace: 0,
    },
  },
  conflicts: [
    {
      object_key: 'orders-prod',
      object_type: 'dashboard',
      reason: 'name_conflict',
      suggested_actions: ['skip', 'overwrite', 'rename'],
    },
  ],
  warnings: [
    {
      code: 'secret_missing',
      message: 'Datasource token will need to be re-entered after import.',
    },
  ],
  errors: [],
};

const submitResponse: ImportSubmitResponse = {
  success: true,
  summary: {
    total: 3,
    success: 2,
    overwritten: 1,
    skipped: 0,
    failed: 0,
  },
  results: [
    {
      object_key: 'orders-prod',
      object_type: 'dashboard',
      status: 'overwritten',
      message: 'Existing dashboard replaced with imported version.',
      new_id: 501,
    },
    {
      object_key: 'service-map',
      object_type: 'topology',
      status: 'success',
      message: 'Imported successfully.',
      new_id: 502,
    },
  ],
};

const meta = {
  title: 'Business/OpsAnalysis/Settings/FamilyOverview',
  component: OpsAnalysisSettingsListShell,
  args: {
    introTitle: 'Namespace management',
    introDescription: 'Configure namespaces that can be queried and imported into Ops Analysis through the shared top section and search-action scaffold.',
    searchValue: 'production',
    searchPlaceholder: 'Search',
    onSearchValueChange: () => undefined,
    onSearch: () => undefined,
    onSearchClear: () => undefined,
    actions: (
      <Space>
        <Button>Import</Button>
        <Button type="primary">Add new</Button>
      </Space>
    ),
    columns: [
      { title: 'Name', dataIndex: 'name', key: 'name', width: 180 },
      { title: 'Type', dataIndex: 'type', key: 'type', width: 140 },
      { title: 'Created at', dataIndex: 'createdAt', key: 'createdAt', width: 220 },
    ],
    dataSource: [
      { id: 1, name: 'Production', type: 'Namespace', createdAt: '2026-07-03 10:00:00' },
      { id: 2, name: 'Analytics API', type: 'Datasource', createdAt: '2026-07-03 10:30:00' },
    ],
    rowKey: 'id',
    pagination: {
      current: 1,
      total: 2,
      pageSize: 20,
      onChange: () => undefined,
    },
    scroll: { y: 320, x: 'max-content' },
  },
} satisfies Meta<typeof OpsAnalysisSettingsListShell>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Overview: Story = {};

export const EmptyState: Story = {
  args: {
    searchValue: '',
    dataSource: [],
  },
};

export const WithSharedImportWorkflow: Story = {
  args: {
    modal: (
      <OpsAnalysisImportModal
        visible
        onCancel={() => undefined}
        targetDirectoryId={null}
        onSuccess={() => undefined}
        importPrecheck={async () => precheckResponse}
        importSubmit={async () => submitResponse}
      />
    ),
  },
};

export const WithDirectoryTargetImport: Story = {
  args: {
    modal: (
      <OpsAnalysisImportModal
        visible
        onCancel={() => undefined}
        targetDirectoryId={101}
        onSuccess={() => undefined}
        importPrecheck={async () => precheckResponse}
        importSubmit={async () => submitResponse}
      />
    ),
  },
};
