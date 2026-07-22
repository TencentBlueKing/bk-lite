import type { Meta, StoryObj } from '@storybook/nextjs';
import ServingGuideDrawer from '@/app/mlops/components/ServingGuideDrawer';
import MlopsAlgorithmTypeBadge from '@/app/mlops/components/mlops-algorithm-type-badge';
import MlopsAlgorithmWorkspaceShell from '@/app/mlops/components/mlops-algorithm-workspace-shell';
import MlopsDatasetReleaseModal from '@/app/mlops/components/mlops-dataset-release-modal';
import MlopsDatasetUploadModal from '@/app/mlops/components/mlops-dataset-upload-modal';
import type { MlopsDatasetModalRef } from '@/app/mlops/components/mlops-dataset-shared/contracts';
import { DatasetType } from '@/app/mlops/components/mlops-shared';
import SectionHeader from '@/components/section-header';
import React, { useEffect, useRef } from 'react';
import { Button } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';

const badgeRows = [
  {
    title: 'Structured data workflows',
    description:
      'Tabular and sequence-oriented training flows share the same MLOps algorithm taxonomy and header semantics.',
    items: ['anomaly_detection', 'timeseries_predict', 'classification'] as const,
  },
  {
    title: 'Vision workflows',
    description:
      'Image-based training flows keep a separate business taxonomy but still use the same governed badge contract.',
    items: ['image_classification', 'object_detection'] as const,
  },
  {
    title: 'Log intelligence workflows',
    description:
      'Log-oriented training and analysis surfaces rely on the same business badge grammar rather than app-local header pills.',
    items: ['log_clustering'] as const,
  },
];

const algorithmColumns = [
  { title: 'Name', dataIndex: 'name', key: 'name', width: 180 },
  { title: 'Owner', dataIndex: 'owner', key: 'owner', width: 160 },
  { title: 'Status', dataIndex: 'status', key: 'status', width: 140 },
  { title: 'Updated At', dataIndex: 'updatedAt', key: 'updatedAt', width: 200 },
];

const algorithmDataSource = [
  {
    id: '1',
    name: 'Fraud Detection Baseline',
    owner: 'alice',
    status: 'Running',
    updatedAt: '2026-07-03 10:00:00',
  },
  {
    id: '2',
    name: 'Time Series Forecast v2',
    owner: 'bob',
    status: 'Stopped',
    updatedAt: '2026-07-03 14:25:00',
  },
];

const FamilyOverview = () => {
  const imageUploadRef = useRef<MlopsDatasetModalRef>(null);
  const releaseRef = useRef<MlopsDatasetModalRef>(null);

  useEffect(() => {
    imageUploadRef.current?.showModal({
      type: 'upload',
      form: {
        dataset_id: 1,
        name: 'Vision Dataset',
      },
    });
    releaseRef.current?.showModal({
      type: 'publish',
    });
  }, []);

  return (
    <div className="space-y-6">
      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Algorithm taxonomy"
          titleClassName="text-sm font-semibold"
          description="MLOps surfaces share one business-owned algorithm taxonomy. Storybook governs the visible badge contract under `Business/MLOps/Algorithm/*` while the underlying workflow logic stays specific to each training domain."
        />

        <div className="space-y-4">
          {badgeRows.map((row) => (
            <div
              key={row.title}
              className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4"
            >
              <SectionHeader
                className="mb-3"
                title={row.title}
                titleClassName="text-sm font-semibold"
                description={row.description}
              />
              <div className="flex flex-wrap gap-3">
                {row.items.map((algorithmType) => (
                  <MlopsAlgorithmTypeBadge
                    key={algorithmType}
                    algorithmType={algorithmType}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Algorithm workspace shell"
          titleClassName="text-sm font-semibold"
          description="Algorithm list pages share one governed workspace contract while keeping page-local columns, actions, and drawer/modal attachments specific to each MLOps domain."
        />

        <div className="grid gap-4 xl:grid-cols-2">
          <MlopsAlgorithmWorkspaceShell
            algorithmType="classification"
            description="MLOps algorithm list pages share one governed workspace contract while keeping page-level columns, actions, and modal flows local."
            searchProps={{
              placeholder: 'Search algorithm assets',
            }}
            actions={<Button type="primary">Add item</Button>}
            refreshAction={<ReloadOutlined />}
            columns={algorithmColumns}
            dataSource={algorithmDataSource}
            rowKey="id"
            pagination={{ current: 1, total: 2, pageSize: 10 }}
            scroll={{ x: 'max-content', y: 360 }}
          />

          <MlopsAlgorithmWorkspaceShell
            algorithmType="timeseries_predict"
            description="The workspace shell governs the shared scaffold while dialogs and drawers remain page-local business attachments."
            searchProps={{
              placeholder: 'Search training jobs',
            }}
            actions={<Button type="primary">Create task</Button>}
            refreshAction={<ReloadOutlined />}
            columns={algorithmColumns}
            dataSource={algorithmDataSource}
            rowKey="id"
            pagination={{ current: 1, total: 2, pageSize: 10 }}
            scroll={{ x: 'max-content', y: 360 }}
            modal={(
              <div className="mb-4 rounded-md border border-dashed border-[var(--color-border-1)] bg-[var(--color-fill-quaternary)] p-3 text-sm text-[var(--color-text-2)]">
                Page-local modal mount
              </div>
            )}
          >
            <div className="mt-4 rounded-md border border-dashed border-[var(--color-border-1)] bg-[var(--color-fill-quaternary)] p-3 text-sm text-[var(--color-text-2)]">
              Page-local drawer mount
            </div>
          </MlopsAlgorithmWorkspaceShell>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Upload workflow boundary"
          titleClassName="text-sm font-semibold"
          description="Dataset upload remains business-scoped for now because image bundling, validation modes, and algorithm-specific submission semantics diverge more than the current shared import shell can reasonably express."
        />

        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
          <div className="grid gap-3 md:grid-cols-3">
            <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg-1)] p-3">
              <SectionHeader spacing="flush" title="Tabular upload" titleClassName="text-sm font-semibold" />
              <div className="mt-1 text-sm text-[var(--color-text-2)]">
                CSV and TXT flows keep algorithm-specific validation and train/val/test labeling.
              </div>
            </div>
            <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg-1)] p-3">
              <SectionHeader spacing="flush" title="Image upload" titleClassName="text-sm font-semibold" />
              <div className="mt-1 text-sm text-[var(--color-text-2)]">
                Image workflows zip multiple files and enforce naming constraints before submission.
              </div>
            </div>
            <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg-1)] p-3">
              <SectionHeader spacing="flush" title="Shared direction" titleClassName="text-sm font-semibold" />
              <div className="mt-1 text-sm text-[var(--color-text-2)]">
                The next extraction boundary should be a true MLOps business upload component, not a forced reuse of the generic import shell.
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Dataset upload contract"
          titleClassName="text-sm font-semibold"
          description="The upload modal remains MLOps-specific, but it is now a governed business component rather than an app-local-only implementation. Dataset upload and release now also live under a dedicated `Business/MLOps/Dataset/*` subtree."
        />

        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
          <MlopsDatasetUploadModal
            ref={imageUploadRef}
            datasetType={DatasetType.IMAGE_CLASSIFICATION}
            onSuccess={() => undefined}
            uploadDataset={async () => undefined}
          />
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Dataset release contract"
          titleClassName="text-sm font-semibold"
          description="Release publishing is now governed as an MLOps business component too. It shares the family’s modal grammar, but keeps dataset-specific split selection and version validation instead of pretending to be a cross-domain publish primitive."
        />

        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
          <MlopsDatasetReleaseModal
            ref={releaseRef}
            datasetId="1"
            datasetType={DatasetType.CLASSIFICATION}
            onSuccess={() => undefined}
            fetchDatasetFiles={async () => [
              {
                id: 101,
                name: 'train-split.csv',
                is_train_data: true,
                is_val_data: false,
                is_test_data: false,
              },
              {
                id: 102,
                name: 'validation-split.csv',
                is_train_data: false,
                is_val_data: true,
                is_test_data: false,
              },
              {
                id: 103,
                name: 'test-split.csv',
                is_train_data: false,
                is_val_data: false,
                is_test_data: true,
              },
            ]}
            createDatasetRelease={async () => undefined}
          />
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          className="mb-0"
          title="Serving guide drawer contract"
          titleClassName="text-sm font-semibold"
          description="Model-serving usage guidance now has an explicit Storybook contract as an MLOps business drawer. It composes the governed `ContentDrawer`, `HttpEndpointDisplay`, and `CodeSnippet` surfaces without hiding that composition inside one page route."
        />

        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
          <div className="space-y-4">
            <ServingGuideDrawer
              open
              onClose={() => undefined}
              algorithmType={DatasetType.CLASSIFICATION}
              serving={{
                id: 101,
                name: 'fraud-detection-serving',
                container_info: {
                  port: 8080,
                  state: 'running',
                  host: '10.0.0.21',
                },
              }}
            />
            <ServingGuideDrawer
              open
              onClose={() => undefined}
              algorithmType={DatasetType.OBJECT_DETECTION}
              serving={{
                id: 102,
                name: 'object-detection-serving',
                container_info: {
                  port: 8080,
                  state: 'running',
                  host: '10.0.0.35',
                },
              }}
            />
            <ServingGuideDrawer
              open
              onClose={() => undefined}
              algorithmType={DatasetType.TIMESERIES_PREDICT}
              serving={{
                id: 103,
                name: 'timeseries-predict-serving',
                container_info: {
                  port: 8080,
                  state: 'stopped',
                  host: '10.0.0.48',
                },
              }}
            />
          </div>
        </div>
      </section>
    </div>
  );
};

const meta = {
  title: 'Business/MLOps/FamilyOverview',
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
