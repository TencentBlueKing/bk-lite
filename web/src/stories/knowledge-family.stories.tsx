import type { Meta, StoryObj } from '@storybook/react';
import ChartEmptyState from '@/components/chart-empty-state';
import KnowledgeDocumentSelectorDrawer from '@/app/opspilot/components/knowledge/document-selector-drawer';
import KnowledgeDocumentTypeBadge from '@/app/opspilot/components/knowledge/document-type-badge';
import KnowledgeEdgeDetailDrawer from '@/app/opspilot/components/knowledge/edge-detail-drawer';
import KnowledgeNodeDetailDrawer from '@/app/opspilot/components/knowledge/node-detail-drawer';
import KnowledgeQADetailDrawer from '@/app/opspilot/components/knowledge/qa-detail-drawer';
import KnowledgeQAEditDrawer from '@/app/opspilot/components/knowledge/qa-edit-drawer';
import KnowledgeQAPairUploadModal from '@/app/opspilot/components/knowledge/qa-pair-upload-modal';
import KnowledgeProcessingStatusBadge from '@/app/opspilot/components/knowledge/processing-status-badge';
import SectionHeader from '@/components/section-header';

const FamilyOverview = () => {
  return (
    <div className="space-y-6">
      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Knowledge document semantics"
          titleClassName="text-sm font-semibold"
          description="Shared document-type badges keep source semantics consistent across knowledge document editing, chunk preview, and graph workflows."
        />

        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
          <div className="flex flex-wrap items-center gap-3">
            <KnowledgeDocumentTypeBadge type="file" label="Local File" />
            <KnowledgeDocumentTypeBadge type="web_page" label="Web Link" />
            <KnowledgeDocumentTypeBadge type="manual" label="Custom Text" />
            <KnowledgeDocumentTypeBadge type="file" label="Local File" active={false} />
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Processing status semantics"
          titleClassName="text-sm font-semibold"
          description="Shared processing-status badges align ingestion, graph construction, and document lifecycle status across knowledge tables and detail views."
        />

        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
          <div className="flex flex-wrap items-center gap-3">
            <KnowledgeProcessingStatusBadge status="pending" label="Pending" />
            <KnowledgeProcessingStatusBadge status="processing" label="Processing" />
            <KnowledgeProcessingStatusBadge status="completed" label="Completed" />
            <KnowledgeProcessingStatusBadge status="failed" label="Failed" />
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Knowledge graph detail workflow"
          titleClassName="text-sm font-semibold"
          description="Knowledge graph exploration and document-testing flows now compose the same governed graph detail drawer shell, so node and edge metadata stop drifting between entry points."
        />

        <div className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <KnowledgeNodeDetailDrawer
              visible
              onClose={() => undefined}
              node={{
                uuid: 'node-7c3f9a4c',
                name: 'Authentication flow',
                summary:
                  'Describes the login handshake and the fallback token refresh branch.',
                labels: ['system', 'workflow', 'auth'],
                fact: 'Refresh tokens are rotated after each successful login.',
              }}
            />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <KnowledgeEdgeDetailDrawer
              visible
              onClose={() => undefined}
              edge={{
                fact:
                  'Auth service writes the session record before emitting the login event.',
                label: 'depends_on',
                source_name: 'Session persistence',
                target_name: 'Login event dispatch',
              }}
            />
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Knowledge graph empty-state contract"
          titleClassName="text-sm font-semibold"
          description="Graph page and graph preview flows now share one governed business empty state for missing entities or edges, keeping graph onboarding and troubleshooting language aligned across entry points."
        />

        <div className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="No extracted entities" titleClassName="text-sm font-medium" />
            <ChartEmptyState
              description="No graph entities have been extracted from the current document set yet."
              compact
              style={{ height: '100%' }}
            />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="No graph relations" titleClassName="text-sm font-medium" />
            <ChartEmptyState
              description="No graph relations are available for the selected knowledge sample."
              compact
              style={{ height: '100%' }}
            />
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Document selection workflow"
          titleClassName="text-sm font-semibold"
          description="Knowledge source-file management and QA grounding now share one governed document-selection drawer contract, including selected-document previews and processing-status metadata."
        />

        <div className="grid gap-4 lg:grid-cols-2">
          <div className="overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)]">
            <div style={{ height: 760 }}>
              <KnowledgeDocumentSelectorDrawer
                open
                title="Select documents"
                onClose={() => undefined}
                onConfirm={() => undefined}
                confirmText="Confirm (2)"
                activeTab="file"
                onTabChange={() => undefined}
                dataSource={[
                  { key: '1', title: 'Incident-handbook.md', chunk_size: 24 },
                  { key: '2', title: 'Service-map.pdf', chunk_size: 12 },
                ]}
                columns={[
                  { title: 'Name', dataIndex: 'title', key: 'title' },
                  { title: 'Chunks', dataIndex: 'chunk_size', key: 'chunk_size', width: 120 },
                ]}
                selectedRowKeys={['1', '2']}
                onSelectionChange={() => undefined}
                currentPage={1}
                pageSize={10}
                total={24}
                onPaginationChange={() => undefined}
                selectedDocuments={[
                  { key: '1', title: 'Incident-handbook.md', type: 'file', status: 'Completed' },
                  { key: '2', title: 'Service-map.pdf', type: 'web_page', status: 'Processing' },
                ]}
                onRemoveDocument={() => undefined}
                onClearAll={() => undefined}
                getDocumentTypeLabel={(type: string) =>
                  ({
                    file: 'Local File',
                    web_page: 'Web Link',
                    manual: 'Custom Text',
                  }[type] || type)
                }
                emptyDescription="Select documents from the table on the left."
                confirmHint="Click confirm to apply the selected documents."
              />
            </div>
          </div>

          <div className="overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)]">
            <div style={{ height: 760 }}>
              <KnowledgeDocumentSelectorDrawer
                open
                title="Select documents"
                onClose={() => undefined}
                onConfirm={() => undefined}
                confirmText="Confirm (2)"
                activeTab="file"
                onTabChange={() => undefined}
                dataSource={[
                  { key: '1', title: 'Incident-handbook.md', chunk_size: 24 },
                  { key: '2', title: 'Service-map.pdf', chunk_size: 12 },
                ]}
                columns={[
                  { title: 'Name', dataIndex: 'title', key: 'title' },
                  { title: 'Chunks', dataIndex: 'chunk_size', key: 'chunk_size', width: 120 },
                ]}
                selectedRowKeys={['1', '2']}
                onSelectionChange={() => undefined}
                currentPage={1}
                pageSize={10}
                total={24}
                onPaginationChange={() => undefined}
                selectedDocuments={[
                  { key: '1', title: 'Incident-handbook.md', type: 'file', status: 'Completed' },
                  { key: '2', title: 'Service-map.pdf', type: 'web_page', status: 'Processing' },
                ]}
                onRemoveDocument={() => undefined}
                onClearAll={() => undefined}
                getDocumentTypeLabel={(type: string) =>
                  ({
                    file: 'Local File',
                    web_page: 'Web Link',
                    manual: 'Custom Text',
                  }[type] || type)
                }
                emptyDescription="Select documents from the table on the left."
                confirmHint="Click confirm to apply the selected documents."
                renderSelectedMeta={(doc) => (
                  <KnowledgeProcessingStatusBadge
                    status={doc.status === 'Completed' ? 'completed' : 'processing'}
                    label={doc.status}
                    className="text-xs"
                  />
                )}
              />
            </div>
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="QA authoring workflow"
          titleClassName="text-sm font-semibold"
          description="Custom QA authoring and QA result review now share governed edit and detail drawers, so add/edit/delete behavior stays aligned across manual authoring and result-management entry points."
        />

        <div className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <KnowledgeQAEditDrawer
              visible
              onClose={() => undefined}
              onSubmit={async () => undefined}
              onSubmitAndContinue={async () => undefined}
              showContinueButton
            />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <KnowledgeQADetailDrawer
              visible
              onClose={() => undefined}
              knowledgeId="doc-42"
              qaPair={{
                id: 'qa-1',
                question: 'How is the login token refreshed?',
                answer:
                  'The client calls the refresh endpoint after a successful silent renew check.',
                base_chunk_id: 'chunk-7',
              }}
              onUpdate={async () => undefined}
              onDelete={async () => undefined}
              getChunkDetailAction={async () => ({
                title: 'Authentication design notes',
                index_name: 'knowledge-authentication',
                content:
                  'Refresh tokens are rotated after each successful login. Silent renew retries once before surfacing a reauthentication prompt.',
              })}
            />
          </div>
        </div>

        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
          <SectionHeader
            className="mb-3"
            title="Edit existing QA pair"
            titleClassName="text-sm font-medium"
            description="The same governed QA edit drawer also owns the edit branch for existing knowledge pairs."
          />
          <KnowledgeQAEditDrawer
            visible
            onClose={() => undefined}
            onSubmit={async () => undefined}
            title="Edit QA Pair"
            initialData={{
              question: 'How is the login token refreshed?',
              answer:
                'The client calls the refresh endpoint after a successful silent renew check.',
            }}
          />
        </div>

        <div className="grid gap-4 lg:grid-cols-3">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Empty upload state" titleClassName="text-sm font-medium" />
            <KnowledgeQAPairUploadModal
              visible
              confirmLoading={false}
              uploadedFiles={[]}
              uploadingFiles={new Set<string>()}
              onOk={() => undefined}
              onCancel={() => undefined}
              onFileUpload={() => false}
              onRemoveFile={() => undefined}
              onDownloadTemplate={() => undefined}
              t={(key: string) =>
                ({
                  'common.import': 'Import Q&A Pairs',
                  'common.confirm': 'Confirm',
                  'common.cancel': 'Cancel',
                  'knowledge.qaPairs.dragOrClick': 'Drag a JSON or CSV file here, or click to upload',
                  'knowledge.qaPairs.uploadHint': 'Each upload is parsed as question and answer pairs for knowledge ingestion.',
                  'knowledge.qaPairs.downloadTemplate': 'Template download',
                  'knowledge.qaPairs.template': 'template',
                }[key] || key)
              }
            />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Ready to import" titleClassName="text-sm font-medium" />
            <KnowledgeQAPairUploadModal
              visible
              confirmLoading={false}
              uploadedFiles={[
                Object.assign(new File(['{}'], 'qa-pairs.json', {
                  type: 'application/json',
                }), { uid: 'qa-pairs.json' }),
              ]}
              uploadingFiles={new Set<string>()}
              onOk={() => undefined}
              onCancel={() => undefined}
              onFileUpload={() => false}
              onRemoveFile={() => undefined}
              onDownloadTemplate={() => undefined}
              t={(key: string) =>
                ({
                  'common.import': 'Import Q&A Pairs',
                  'common.confirm': 'Confirm',
                  'common.cancel': 'Cancel',
                  'knowledge.qaPairs.dragOrClick': 'Drag a JSON or CSV file here, or click to upload',
                  'knowledge.qaPairs.uploadHint': 'Each upload is parsed as question and answer pairs for knowledge ingestion.',
                  'knowledge.qaPairs.downloadTemplate': 'Template download',
                  'knowledge.qaPairs.template': 'template',
                }[key] || key)
              }
            />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Upload in progress" titleClassName="text-sm font-medium" />
            <KnowledgeQAPairUploadModal
              visible
              confirmLoading={false}
              uploadedFiles={[
                Object.assign(new File(['{}'], 'qa-pairs.csv', {
                  type: 'text/csv',
                }), { uid: 'qa-pairs.csv' }),
              ]}
              uploadingFiles={new Set(['qa-pairs.csv'])}
              onOk={() => undefined}
              onCancel={() => undefined}
              onFileUpload={() => false}
              onRemoveFile={() => undefined}
              onDownloadTemplate={() => undefined}
              t={(key: string) =>
                ({
                  'common.import': 'Import Q&A Pairs',
                  'common.confirm': 'Confirm',
                  'common.cancel': 'Cancel',
                  'knowledge.qaPairs.dragOrClick': 'Drag a JSON or CSV file here, or click to upload',
                  'knowledge.qaPairs.uploadHint': 'Each upload is parsed as question and answer pairs for knowledge ingestion.',
                  'knowledge.qaPairs.downloadTemplate': 'Template download',
                  'knowledge.qaPairs.template': 'template',
                }[key] || key)
              }
            />
          </div>
        </div>
      </section>
    </div>
  );
};

const meta = {
  title: 'Business/Knowledge/FamilyOverview',
  component: FamilyOverview,
  decorators: [
    (Story) => (
      <div style={{ maxWidth: 840, padding: 24, background: 'var(--color-bg-2)' }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof FamilyOverview>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Overview: Story = {};
