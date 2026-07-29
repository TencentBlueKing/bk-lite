import type { Meta, StoryObj } from '@storybook/react';
import React from 'react';
import { Button } from 'antd';
import { CloudUploadOutlined, UploadOutlined } from '@ant-design/icons';
import ImportFileModalShell from '@/components/import-file-modal-shell';
import MultiFileUploadPanel from '@/components/multi-file-upload-panel';
import SectionHeader from '@/components/section-header';
import SingleFileUploadPanel from '@/components/single-file-upload-panel';
import UploadDropPanel from '@/components/upload-drop-panel';

const FamilyOverview = () => {
  return (
    <div className="space-y-6">
      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Shared upload surface"
          titleClassName="text-sm font-semibold"
          description="`UploadDropPanel` is the framework-level drag-and-drop primitive. It owns the shared panel structure while consumer flows keep their own file validation and follow-up actions."
        />

        <div className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Single file + template" titleClassName="text-sm font-semibold" />
            <UploadDropPanel
              fileList={[]}
              onChange={() => undefined}
              beforeUpload={() => false}
              maxCount={1}
              accept=".xlsx"
              icon={<CloudUploadOutlined />}
              uploadText="Upload a workbook"
              uploadHint="Use the latest template for the expected columns."
            >
              <Button className="mt-2" type="link">
                Download template
              </Button>
            </UploadDropPanel>
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Directory upload" titleClassName="text-sm font-semibold" />
            <UploadDropPanel
              fileList={[]}
              onChange={() => undefined}
              beforeUpload={() => false}
              name="dataset"
              multiple
              directory
              uploadText="Drag a folder here to upload"
              uploadHint="Directory mode supports image-dataset and bundle-style workflows."
            />
          </div>
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Compatibility wrappers"
          titleClassName="text-sm font-semibold"
          description="`SingleFileUploadPanel` and `MultiFileUploadPanel` stay as stable wrappers for existing business consumers, but they now sit on top of the same shared drop-panel contract."
        />

        <div className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="SingleFilePanel" titleClassName="text-sm font-semibold" />
            <SingleFileUploadPanel
              fileList={[]}
              onChange={() => undefined}
              customRequest={({ onSuccess }) => onSuccess?.('Ok')}
              maxCount={1}
              uploadText="Click or drag a file here to upload"
              uploadHint="Use this wrapper when the consumer contract is explicitly single-file."
            />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="MultiFilePanel" titleClassName="text-sm font-semibold" />
            <MultiFileUploadPanel
              fileList={[]}
              onChange={() => undefined}
              beforeUpload={() => false}
              multiple
              icon={<UploadOutlined />}
              uploadText="Drag files here to upload"
              uploadHint="Use this wrapper when the consumer contract is explicitly multi-file."
            />
          </div>
        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Single-file hidden list" titleClassName="text-sm font-semibold" />
            <SingleFileUploadPanel
              fileList={[]}
              onChange={() => undefined}
              customRequest={({ onSuccess }) => onSuccess?.('Ok')}
              accept=".yaml,.yml"
              showUploadList={false}
              uploadText="Upload a YAML package"
              uploadHint="The file stays hidden after selection when the flow advances immediately."
            />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Single-file rich trigger" titleClassName="text-sm font-semibold" />
            <SingleFileUploadPanel
              fileList={[]}
              onChange={() => undefined}
              customRequest={({ onSuccess }) => onSuccess?.('Ok')}
              accept=".xlsx"
              icon={<CloudUploadOutlined />}
              uploadText={(
                <span className="flex items-center justify-center gap-1">
                  Drag a workbook here
                  <Button type="link" size="small">
                    Browse
                  </Button>
                </span>
              )}
            />
          </div>
        </div>

        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
          <SectionHeader spacing="compact" title="Multi-file hidden list" titleClassName="text-sm font-semibold" />
          <MultiFileUploadPanel
            fileList={[]}
            onChange={() => undefined}
            beforeUpload={() => false}
            showUploadList={false}
            uploadText="Drag files here to upload"
            uploadHint={(
              <>
                <div>Supported: .md .txt .pdf</div>
                <div>Each file must be smaller than 10 MB.</div>
              </>
            )}
          >
            <Button className="mt-2" type="link">
              Download template
            </Button>
          </MultiFileUploadPanel>
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Upload overlays"
          titleClassName="text-sm font-semibold"
          description="`ImportFileModalShell` is the governed overlay contract for single-file import flows. Apps keep their own validation, parsing, and submit logic while reusing the same modal-plus-upload surface."
        />

        <div className="grid gap-4 xl:grid-cols-2">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <ImportFileModalShell
              visible
              width={640}
              title="Import configuration"
              confirmText="Confirm"
              cancelText="Cancel"
              confirmDisabled
              onConfirm={() => undefined}
              onCancel={() => undefined}
              uploadProps={{
                customRequest: ({ onSuccess }) => onSuccess?.('Ok'),
                onChange: () => undefined,
                fileList: [],
                accept: '.json',
                maxCount: 1,
                uploadText: 'Upload JSON',
                uploadHint: 'The file is parsed immediately after selection.',
              }}
            />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <ImportFileModalShell
              visible
              width={640}
              title="Import workbook"
              subTitle="Use the latest template before uploading."
              confirmText="Confirm"
              cancelText="Cancel"
              onConfirm={() => undefined}
              onCancel={() => undefined}
              uploadProps={{
                customRequest: ({ onSuccess }) => onSuccess?.('Ok'),
                onChange: () => undefined,
                fileList: [],
                accept: '.xls,.xlsx',
                maxCount: 1,
                uploadText: 'Upload workbook',
                uploadHint: 'Excel files only.',
              }}
              afterUploadPanel={
                <Button className="mt-[10px]" type="link">
                  Export template
                </Button>
              }
            />
          </div>
        </div>
      </section>
    </div>
  );
};

const meta = {
  title: 'Framework/Forms/Upload/FamilyOverview',
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
