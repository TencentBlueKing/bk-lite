import React, { useEffect, useRef } from 'react';
import type { Meta, StoryObj } from '@storybook/react';
import MlopsDatasetReleaseModal from '@/components/mlops-dataset-release-modal';
import MlopsDatasetUploadModal from '@/components/mlops-dataset-upload-modal';
import type { MlopsDatasetModalRef } from '@/components/mlops-dataset-shared/contracts';
import { DatasetType } from '@/components/mlops-shared';
import SectionHeader from '@/components/section-header';

const DatasetFamilyOverview = () => {
  const uploadRef = useRef<MlopsDatasetModalRef>(null);
  const releaseRef = useRef<MlopsDatasetModalRef>(null);
  const uploadImageRef = useRef<MlopsDatasetModalRef>(null);
  const uploadLogRef = useRef<MlopsDatasetModalRef>(null);
  const releaseVisionRef = useRef<MlopsDatasetModalRef>(null);

  useEffect(() => {
    uploadRef.current?.showModal({
      type: 'upload',
      form: {
        dataset_id: 1,
        name: 'Fraud Training Set',
      },
    });
    releaseRef.current?.showModal({
      type: 'publish',
    });
    uploadImageRef.current?.showModal({
      type: 'upload',
      form: {
        dataset_id: 2,
        name: 'Vision Dataset',
      },
    });
    uploadLogRef.current?.showModal({
      type: 'upload',
      form: {
        dataset_id: 3,
        name: 'Cluster Log Dataset',
      },
    });
    releaseVisionRef.current?.showModal({
      type: 'publish',
    });
  }, []);

  return (
    <div className="space-y-6">
      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          title="Dataset workflow family"
          description="Upload and release flows now form one governed MLOps dataset subtree. They share the same workflow boundary while keeping dataset-type-specific validation and publishing behavior."
        />

        <div className="grid gap-4 xl:grid-cols-2">
          <div className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader
              title="UploadModal"
              description="Handles dataset ingestion with algorithm-specific file validation and import semantics."
              className="mb-3"
            />

            <MlopsDatasetUploadModal
              ref={uploadRef}
              datasetType={DatasetType.IMAGE_CLASSIFICATION}
              onSuccess={() => undefined}
              uploadDataset={async () => undefined}
            />

            <MlopsDatasetUploadModal
              ref={uploadImageRef}
              datasetType={DatasetType.IMAGE_CLASSIFICATION}
              onSuccess={() => undefined}
              uploadDataset={async () => undefined}
            />

            <MlopsDatasetUploadModal
              ref={uploadLogRef}
              datasetType={DatasetType.LOG_CLUSTERING}
              onSuccess={() => undefined}
              uploadDataset={async () => undefined}
            />
          </div>

          <div className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader
              title="ReleaseModal"
              description="Publishes curated dataset splits with version validation and file-role selection."
              className="mb-3"
            />

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

            <MlopsDatasetReleaseModal
              ref={releaseVisionRef}
              datasetId="2"
              datasetType={DatasetType.IMAGE_CLASSIFICATION}
              onSuccess={() => undefined}
              fetchDatasetFiles={async () => [
                {
                  id: 201,
                  name: 'vision-train.zip',
                  is_train_data: true,
                  is_val_data: false,
                  is_test_data: false,
                },
                {
                  id: 202,
                  name: 'vision-val.zip',
                  is_train_data: false,
                  is_val_data: true,
                  is_test_data: false,
                },
              ]}
              createDatasetRelease={async () => undefined}
            />
          </div>
        </div>
      </section>
    </div>
  );
};

const meta = {
  title: 'Business/MLOps/Dataset/FamilyOverview',
  component: DatasetFamilyOverview,
  decorators: [
    (Story) => (
      <div style={{ maxWidth: 1100, padding: 24, background: 'var(--color-bg-2)' }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof DatasetFamilyOverview>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Overview: Story = {};
