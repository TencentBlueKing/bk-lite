import type { Meta, StoryObj } from '@storybook/nextjs';
import EntityManagementGrid, {
  type EntityManagementGridApiResponse,
  type EntityManagementGridDataSource,
  type EntityManagementGridFetchParams,
} from '@/app/opspilot/components/entity-management-grid';
import SkillView from '@/app/opspilot/components/custom-chat-sse/SkillView';
import OpspilotApprovalCard from '@/components/opspilot-approval-card';
import OpspilotAvailabilityBadge from '@/components/opspilot-availability-badge';
import OpspilotConfigSeverityBadge from '@/components/opspilot-config-severity-badge';
import EntityCard from '@/components/opspilot-entity-card';
import OpspilotKnowledgeBaseSelector from '@/components/opspilot-knowledge-base-selector';
import OpspilotProviderModelSection from '@/app/opspilot/components/provider/model-section';
import {
  OpspilotProviderGridSkeleton,
  OpspilotProviderModelTreeSkeleton,
} from '@/components/opspilot-provider-skeletons';
import OpspilotProviderVendorConfigFields from '@/app/opspilot/components/provider/vendor-config-fields';
import OpspilotProviderVendorGrid from '@/app/opspilot/components/provider/vendor-grid';
import OpspilotSelectorOperateModal from '@/components/opspilot-selector-operate-modal';
import OpspilotProviderEmptyState from '@/components/opspilot-provider-empty-state';
import {
  CronEditor,
  MonthDayPicker,
  TimeListField,
} from '@/components/opspilot-scheduler-inputs';
import SkillCard from '@/components/opspilot-skill-card';
import SectionHeader from '@/components/section-header';
import StudioCard from '@/components/opspilot-studio-card';
import SummaryDetailLayoutShell from '@/components/summary-detail-layout-shell';
import TopSection from '@/components/top-section';
import React from 'react';
import { Button, Form } from 'antd';
import type { Model, ModelVendor, ModelVendorPayload, ProviderResourceType } from '@/app/opspilot/types/provider';

const now = Date.now();

const knowledgeBases = [
  { id: 1, name: 'Incident Runbooks', introduction: 'Runbook and triage workflows for incidents.' },
  { id: 2, name: 'Kubernetes Guides', introduction: 'Cluster operating knowledge.' },
  { id: 3, name: 'Billing Policies', introduction: 'Finance and approval references.' },
];

const sectionStyle = {
  topGlow: 'linear-gradient(180deg, rgba(231, 240, 253, 0.62) 0%, rgba(244, 249, 255, 0.38) 42%, rgba(255, 255, 255, 0) 100%)',
  panelGlow: 'rgba(147, 197, 253, 0.14)',
  headerBg: 'linear-gradient(135deg, rgba(249, 252, 255, 1) 0%, rgba(238, 246, 255, 0.94) 100%)',
  sectionBg: 'linear-gradient(180deg, rgba(249, 252, 255, 0.97) 0%, rgba(255, 255, 255, 0.99) 34%, rgba(255, 255, 255, 1) 100%)',
  tableBg: 'rgba(255, 255, 255, 0.82)',
  borderColor: 'rgba(191, 219, 254, 0.7)',
  shadow: '0 14px 28px rgba(148, 163, 184, 0.08)',
};

const providerModels: Model[] = [
  {
    id: 1,
    name: 'gpt-4o',
    model: 'gpt-4o',
    enabled: true,
    team: [1],
    team_name: ['Platform'],
  },
  {
    id: 2,
    name: 'text-embedding-3-large',
    model: 'text-embedding-3-large',
    enabled: false,
    team: [2],
    team_name: ['Search'],
  },
];

const providerVendors: ModelVendor[] = [
  {
    id: 1,
    name: 'OpenAI Primary',
    vendor_type: 'openai',
    api_base: 'https://api.openai.com/v1',
    description: 'Primary production vendor for chat and embedding workloads.',
    enabled: true,
    team: [1],
    team_name: ['Platform'],
    model_count: 18,
    llm_model_count: 10,
    embed_model_count: 5,
    rerank_model_count: 2,
    ocr_model_count: 1,
  },
  {
    id: 2,
    name: 'Anthropic Backup',
    vendor_type: 'anthropic',
    api_base: 'https://api.anthropic.com',
    description: 'Fallback vendor used for long-context support and resilience drills.',
    enabled: false,
    team: [2],
    team_name: ['SRE'],
    model_count: 7,
    llm_model_count: 7,
    embed_model_count: 0,
    rerank_model_count: 0,
    ocr_model_count: 0,
  },
];

interface EntityManagementStoryItem {
  id: number;
  name: string;
  introduction: string;
  created_by: string;
  team_name: string[] | string;
  team: string[];
  permissions: string[];
  is_pinned?: boolean;
  skill_type?: number;
  llm_model_name?: string;
  online?: boolean;
  bot_type?: number;
}

interface EntityManagementStoryModalProps {
  visible?: boolean;
  onCancel?: () => void;
  onConfirm?: (values: EntityManagementStoryItem) => void;
  initialValues?: EntityManagementStoryItem | null;
}

const SkillManagementModal: React.FC<EntityManagementStoryModalProps> = ({
  visible,
  onCancel,
  onConfirm,
  initialValues,
}) => {
  if (!visible) return null;

  return (
    <div className="mt-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
      <div className="text-sm font-semibold text-[var(--color-text-1)]">Skill modal surface</div>
      <div className="mt-2 text-sm text-[var(--color-text-3)]">
        The business shell owns modal injection without hard-coding form semantics.
      </div>
      <div className="mt-4 flex gap-2">
        <Button
          type="primary"
          onClick={() => onConfirm?.({
            id: initialValues?.id || Date.now(),
            name: initialValues?.name || 'Mock skill',
            introduction: initialValues?.introduction || 'Created from the Storybook harness.',
            created_by: initialValues?.created_by || 'storybook',
            team_name: initialValues?.team_name || ['Ops'],
            team: initialValues?.team || ['Ops'],
            permissions: initialValues?.permissions || ['View', 'Edit', 'Delete'],
            llm_model_name: initialValues?.llm_model_name || 'gpt-4o',
            skill_type: initialValues?.skill_type || 1,
            is_pinned: initialValues?.is_pinned || false,
          })}
        >
          Save
        </Button>
        <Button onClick={onCancel}>Cancel</Button>
      </div>
    </div>
  );
};

const StudioManagementModal: React.FC<EntityManagementStoryModalProps> = ({
  visible,
  onCancel,
  onConfirm,
  initialValues,
}) => {
  if (!visible) return null;

  return (
    <div className="mt-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
      <div className="text-sm font-semibold text-[var(--color-text-1)]">Studio modal surface</div>
      <div className="mt-2 text-sm text-[var(--color-text-3)]">
        The shell keeps studio-specific create and edit flows outside the shared list frame.
      </div>
      <div className="mt-4 flex gap-2">
        <Button
          type="primary"
          onClick={() => onConfirm?.({
            id: initialValues?.id || Date.now(),
            name: initialValues?.name || 'Mock studio',
            introduction: initialValues?.introduction || 'Created from the Storybook harness.',
            created_by: initialValues?.created_by || 'storybook',
            team_name: initialValues?.team_name || ['SRE'],
            team: initialValues?.team || ['SRE'],
            permissions: initialValues?.permissions || ['View', 'Edit', 'Delete'],
            bot_type: initialValues?.bot_type || 1,
            online: initialValues?.online || false,
            is_pinned: initialValues?.is_pinned || false,
          })}
        >
          Save
        </Button>
        <Button onClick={onCancel}>Cancel</Button>
      </div>
    </div>
  );
};

const skillManagementSeed: EntityManagementStoryItem[] = [
  {
    id: 101,
    name: 'Kubernetes Diagnosis',
    introduction: 'Diagnoses workload configuration risks and proposes safe remediation steps.',
    created_by: 'alice',
    team_name: ['Ops'],
    team: ['Ops'],
    permissions: ['View', 'Edit', 'Delete'],
    llm_model_name: 'gpt-4o',
    skill_type: 1,
    is_pinned: true,
  },
  {
    id: 102,
    name: 'RAG Incident Triage',
    introduction: 'Finds relevant runbooks and summarizes likely incident paths.',
    created_by: 'bob',
    team_name: ['SRE'],
    team: ['SRE'],
    permissions: ['View', 'Edit', 'Delete'],
    llm_model_name: 'gpt-4.1',
    skill_type: 2,
    is_pinned: false,
  },
];

const studioManagementSeed: EntityManagementStoryItem[] = [
  {
    id: 201,
    name: 'Incident Copilot',
    introduction: 'Coordinates approvals, chatflow actions, and follow-up work for incidents.',
    created_by: 'carol',
    team_name: ['SRE'],
    team: ['SRE'],
    permissions: ['View', 'Edit', 'Delete'],
    online: true,
    bot_type: 1,
    is_pinned: true,
  },
  {
    id: 202,
    name: 'Change Review Assistant',
    introduction: 'Helps operators review change plans before rollout.',
    created_by: 'dave',
    team_name: ['Platform'],
    team: ['Platform'],
    permissions: ['View', 'Edit', 'Delete'],
    online: false,
    bot_type: 3,
    is_pinned: false,
  },
];

const createEntityManagementDataSource = (
  getItems: () => EntityManagementStoryItem[],
  setItems: React.Dispatch<React.SetStateAction<EntityManagementStoryItem[]>>
): EntityManagementGridDataSource<EntityManagementStoryItem> => ({
  fetchPage: async (
    params: EntityManagementGridFetchParams
  ): Promise<EntityManagementGridApiResponse<EntityManagementStoryItem>> => {
    let next = getItems();
    const keyword = params.name.trim().toLowerCase();

    if (keyword) {
      next = next.filter((item) => item.name.toLowerCase().includes(keyword));
    }

    if (params.selectedTypes.length > 0 && params.searchField) {
      next = next.filter((item) =>
        params.selectedTypes.includes(Number((item as any)[params.searchField]))
      );
    }

    const start = (params.page - 1) * params.page_size;
    const end = start + params.page_size;

    return {
      count: next.length,
      items: next.slice(start, end),
    };
  },
  createItem: async (values: EntityManagementStoryItem) => {
    setItems((current) => [{ ...values, id: Number(values.id) || Date.now() }, ...current]);
  },
  updateItem: async (item: EntityManagementStoryItem, values: EntityManagementStoryItem) => {
    setItems((current) =>
      current.map((entry) => (entry.id === item.id ? { ...entry, ...values, id: item.id } : entry))
    );
  },
  deleteItem: async (item: EntityManagementStoryItem) => {
    setItems((current) => current.filter((entry) => entry.id !== item.id));
  },
});

const SkillEntityManagementHarness = () => {
  const [items, setItems] = React.useState<EntityManagementStoryItem[]>(skillManagementSeed);
  const itemsRef = React.useRef(items);
  itemsRef.current = items;

  return (
    <EntityManagementGrid<EntityManagementStoryItem>
      dataSource={createEntityManagementDataSource(() => itemsRef.current, setItems)}
      CardComponent={SkillCard}
      ModifyModalComponent={SkillManagementModal}
      itemTypeSingle="skill"
      typeConfig={{
        options: [
          { key: 2, title: 'QA' },
          { key: 1, title: 'Tools' },
          { key: 3, title: 'Plan' },
          { key: 4, title: 'Complex' },
        ],
        searchField: 'skill_type',
      }}
      onCreateFromTemplate={() => undefined}
      onTogglePin={async (item) => {
        setItems((current) =>
          current.map((entry) =>
            entry.id === item.id ? { ...entry, is_pinned: !entry.is_pinned } : entry
          )
        );
      }}
    />
  );
};

const StudioEntityManagementHarness = () => {
  const [items, setItems] = React.useState<EntityManagementStoryItem[]>(studioManagementSeed);
  const itemsRef = React.useRef(items);
  itemsRef.current = items;

  return (
    <EntityManagementGrid<EntityManagementStoryItem>
      dataSource={createEntityManagementDataSource(() => itemsRef.current, setItems)}
      CardComponent={StudioCard}
      ModifyModalComponent={StudioManagementModal}
      itemTypeSingle="studio"
      typeConfig={{
        options: [
          { key: 1, title: 'Pilot' },
          { key: 2, title: 'LobeChat' },
          { key: 3, title: 'Chatflow' },
        ],
        searchField: 'bot_type',
      }}
      onTogglePin={async (item) => {
        setItems((current) =>
          current.map((entry) =>
            entry.id === item.id ? { ...entry, is_pinned: !entry.is_pinned } : entry
          )
        );
      }}
    />
  );
};

const ProviderVendorConfigPreview = ({
  variant,
  mode,
}: {
  variant: 'modal' | 'detail';
  mode: 'add' | 'edit';
}) => {
  const [form] = Form.useForm<ModelVendorPayload>();
  const [apiKeyChanged, setApiKeyChanged] = React.useState(mode === 'add');
  const apiKeyValue = Form.useWatch('api_key', form);

  React.useEffect(() => {
    form.setFieldsValue({
      name: 'OpenAI Primary',
      api_base: 'https://api.openai.com/v1',
      api_key: mode === 'edit' ? '*******' : '',
      team: [1],
      enabled: true,
      description: 'Primary vendor for shared production AI workloads.',
    });
  }, [form, mode]);

  return (
    <Form form={form} layout="vertical">
      <OpspilotProviderVendorConfigFields
        form={form}
        mode={mode}
        variant={variant}
        apiKeyChanged={apiKeyChanged}
        apiKeyValue={apiKeyValue}
        apiKeyAction={variant === 'detail' ? <Button className="mt-px">Test Connection</Button> : undefined}
        onApiBaseChange={() => undefined}
        onApiKeyReset={() => {
          setApiKeyChanged(true);
          form.setFieldValue('api_key', '');
        }}
        onApiKeyChange={(value) => {
          setApiKeyChanged(true);
          form.setFieldValue('api_key', value);
        }}
      />
    </Form>
  );
};

const FamilyOverview = () => {
  const [selectedKnowledgeBases, setSelectedKnowledgeBases] = React.useState<number[]>([1, 2]);
  const [ragSources, setRagSources] = React.useState([
    { id: 1, name: 'Incident Runbooks', introduction: 'Runbook and triage workflows for incidents.', score: 0.82 },
    { id: 2, name: 'Kubernetes Guides', introduction: 'Cluster operating knowledge.', score: 0.67 },
  ]);

  return (
    <div className="space-y-6">
      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Detail workspace shell"
          titleClassName="text-sm font-semibold"
          description="Shared OpsPilot detail routes reuse the same routed shell for navigation, summary context, and optional workflow progress framing."
        />

        <SummaryDetailLayoutShell
          topSection={(
            <TopSection
              title="Knowledge Documents"
              content="Review ingestion progress, switch tabs, and continue knowledge operations from one stable detail shell."
            />
          )}
          summary={{
            title: 'Production Runbook Library',
            description: 'Shared operational knowledge base for internal runbooks and troubleshooting material.',
          }}
          onBackButtonClick={() => undefined}
          customMenuItems={[
            {
              title: 'Documents',
              url: '/opspilot/knowledge/detail/documents',
              icon: 'shujuguanli',
              name: 'knowledge_documents',
              operation: [],
            },
            {
              title: 'Testing',
              url: '/opspilot/knowledge/detail/testing',
              icon: 'ceshi',
              name: 'knowledge_testing',
              operation: [],
            },
          ]}
        >
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-6 text-sm text-[var(--color-text-2)]">
            Shared OpsPilot detail content renders inside this stable business shell.
          </div>
        </SummaryDetailLayoutShell>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Status semantics"
          titleClassName="text-sm font-semibold"
          description="Availability and config-severity badges provide the shared compact status language across studio, reports, and card surfaces."
        />

        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
          <div className="flex flex-wrap items-center gap-3">
            <OpspilotAvailabilityBadge online label="Studio Online" />
            <OpspilotAvailabilityBadge online={false} label="Studio Offline" />
            <OpspilotConfigSeverityBadge severity="critical" />
            <OpspilotConfigSeverityBadge severity="high" />
            <OpspilotConfigSeverityBadge severity="medium" />
            <OpspilotConfigSeverityBadge severity="low" />
            <OpspilotConfigSeverityBadge severity="warning" />
            <OpspilotConfigSeverityBadge severity="info" />
            <OpspilotConfigSeverityBadge severity="unknown" />
            <OpspilotConfigSeverityBadge severity="warning" label="需人工复核" />
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Approval workflow surface"
          titleClassName="text-sm font-semibold"
          description="ApprovalCard governs execution approval interactions across chatflow preview and custom chat execution surfaces."
        />

        <div className="rounded-lg border border-[var(--color-border)] bg-white p-4">
          <OpspilotApprovalCard
            token="mock-token"
            onDecision={() => undefined}
            request={{
              execution_id: 'exec-1',
              node_id: 'node-1',
              tool_call_id: 'tool-1',
              tool_name: 'apply_kubernetes_fix',
              tool_args: {
                cluster: 'prod-cluster',
                namespace: 'default',
                workload: 'nginx-web',
              },
              timeout_seconds: 300,
              received_at: now,
              status: 'pending',
            }}
          />
        </div>

        <div className="grid gap-4 lg:grid-cols-3">
          <div className="rounded-lg border border-[var(--color-border)] bg-white p-4">
            <SectionHeader spacing="compact" title="Approved request" titleClassName="text-sm font-medium" />
            <OpspilotApprovalCard
              token="mock-token"
              onDecision={() => undefined}
              request={{
                execution_id: 'exec-2',
                node_id: 'node-2',
                tool_call_id: 'tool-2',
                tool_name: 'delete_pod',
                tool_args: {
                  namespace: 'ops',
                  pod_name: 'worker-0',
                },
                timeout_seconds: 300,
                received_at: now - 30_000,
                status: 'approved',
              }}
            />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-white p-4">
            <SectionHeader spacing="compact" title="Rejected request" titleClassName="text-sm font-medium" />
            <OpspilotApprovalCard
              token="mock-token"
              onDecision={() => undefined}
              request={{
                execution_id: 'exec-3',
                node_id: 'node-3',
                tool_call_id: 'tool-3',
                tool_name: 'patch_deployment_image',
                tool_args: {
                  namespace: 'prod',
                  workload: 'api-server',
                  image: 'example.com/api:v2',
                },
                timeout_seconds: 120,
                received_at: now - 45_000,
                status: 'rejected',
              }}
            />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-white p-4">
            <SectionHeader spacing="compact" title="Timed-out request" titleClassName="text-sm font-medium" />
            <OpspilotApprovalCard
              token="mock-token"
              onDecision={() => undefined}
              request={{
                execution_id: 'exec-4',
                node_id: 'node-4',
                tool_call_id: 'tool-4',
                tool_name: 'restart_statefulset',
                tool_args: {
                  namespace: 'monitor',
                  workload: 'prometheus',
                },
                timeout_seconds: 10,
                received_at: now - 20_000,
                status: 'pending',
              }}
            />
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Chat-side skill package hits"
          titleClassName="text-sm font-semibold"
          description="SkillView is a lightweight subpanel inside the custom chat SSE workflow, so it stays governed inside the OpsPilot family instead of becoming a standalone Storybook root."
        />

        <div className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-lg border border-[var(--color-border)] bg-white p-4">
            <SectionHeader spacing="compact" title="Matched packages" titleClassName="text-sm font-medium" />
            <div className="mt-3">
              <SkillView
                items={[
                  {
                    id: 'kubernetes-specialist',
                    name: 'Kubernetes Specialist',
                    package_id: 'kubernetes-specialist',
                    description: 'Kubernetes workload troubleshooting',
                    missing_tools: [],
                  } as any,
                ]}
              />
            </div>
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-white p-4">
            <SectionHeader spacing="compact" title="Missing tool bindings" titleClassName="text-sm font-medium" />
            <div className="mt-3">
              <SkillView
                items={[
                  {
                    id: 'agent-browser',
                    name: 'agent-browser',
                    package_id: 'agent-browser',
                    description: 'Browser automation workflow',
                    missing_tools: ['agent_browser'],
                  } as any,
                ]}
              />
            </div>
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Skill knowledge routing workflow"
          titleClassName="text-sm font-semibold"
          description="Skill rule editing and skill settings now share one governed knowledge-base selector and selector modal contract, keeping RAG source selection and scoring aligned across both authoring entry points."
        />

        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
          <OpspilotKnowledgeBaseSelector
            knowledgeBases={knowledgeBases}
            selectedKnowledgeBases={selectedKnowledgeBases}
            setSelectedKnowledgeBases={setSelectedKnowledgeBases}
            ragSources={ragSources}
            setRagSources={setRagSources}
          />
        </div>

        <div className="grid gap-4 xl:grid-cols-2">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader
              spacing="compact"
              title="Knowledge selector modal"
              titleClassName="text-sm font-medium"
              description="The governed selector modal contract powers knowledge-base picking with guide copy, search, and multi-select state."
            />
            <OpspilotSelectorOperateModal
              visible
              okText="Confirm"
              cancelText="Cancel"
              options={knowledgeBases}
              selectedOptions={[1, 3]}
              onOk={() => undefined}
              onCancel={() => undefined}
            />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader
              spacing="compact"
              title="Tool selector modal"
              titleClassName="text-sm font-medium"
              description="The same selector modal also governs tool picking, while exposing richer tooltip detail and no-guide empty behavior."
            />
            <OpspilotSelectorOperateModal
              visible
              title="Select Tool"
              okText="Confirm"
              cancelText="Cancel"
              options={knowledgeBases.map((option, index) => ({
                ...option,
                id: index + 11,
                description: `${option.introduction} Includes live connection metadata.`,
                icon: 'zhishiku',
              }))}
              selectedOptions={[11]}
              showToolDetail
              isNeedGuide={false}
              onOk={() => undefined}
              onCancel={() => undefined}
            />
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Chatflow scheduler workflow"
          titleClassName="text-sm font-semibold"
          description="TimeListField, MonthDayPicker, and CronEditor only surface through the chatflow Celery node configuration workflow, so they stay governed inside the OpsPilot family instead of branching into a second business root."
        />

        <div className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
          <SectionHeader
            spacing="compact"
            title="Scheduler input family"
            titleClassName="text-sm font-medium"
            description="Recurring time lists, month-day selection, and raw cron editing form one stable scheduling contract inside NodeConfigDrawer."
          />

          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-4">
              <SectionHeader spacing="compact" title="Time list field" titleClassName="text-sm font-medium" />
              <TimeListField value={['09:00', '18:00']} onChange={() => undefined} max={4} />
              <TimeListField value={['09:00']} onChange={() => undefined} min={1} />
              <TimeListField
                value={['08:30', '20:00']}
                onChange={() => undefined}
                disabled
              />
            </div>

            <div className="space-y-4">
              <SectionHeader spacing="compact" title="Month day picker" titleClassName="text-sm font-medium" />
              <div className="grid gap-4 md:grid-cols-3">
                <MonthDayPicker value={15} onChange={() => undefined} />
                <MonthDayPicker value={31} onChange={() => undefined} />
                <MonthDayPicker value={7} onChange={() => undefined} disabled />
              </div>
            </div>
          </div>

          <div className="space-y-4">
            <SectionHeader spacing="compact" title="Cron editor" titleClassName="text-sm font-medium" />
            <CronEditor value="0 9 * * 1-5" onChange={() => undefined} />
            <CronEditor value="0 12 * * *" onChange={() => undefined} />
            <CronEditor value="30 2 1 * *" onChange={() => undefined} disabled />
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Entity management catalogs"
          titleClassName="text-sm font-semibold"
          description="EntityManagementGrid, SkillCard, and StudioCard form one governed OpsPilot catalog workflow, so list state, type filtering, modal injection, and pinning stay inside the same family contract."
        />

        <div className="grid gap-4 xl:grid-cols-2">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader
              spacing="compact"
              title="Skill catalog"
              titleClassName="text-sm font-medium"
              description="Skills reuse the shared entity grid while contributing skill-type filtering, model labels, and template-driven creation."
            />
            <div className="mt-3">
              <SkillEntityManagementHarness />
            </div>
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader
              spacing="compact"
              title="Studio catalog"
              titleClassName="text-sm font-medium"
              description="Studios keep the same entity-management workflow but swap in studio cards, bot-type filtering, and a studio-specific modal surface."
            />
            <div className="mt-3">
              <StudioEntityManagementHarness />
            </div>
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Provider management empty-state contract"
          titleClassName="text-sm font-semibold"
          description="Vendor grids, provider model sections, and model card collections now share one governed provider empty-state contract instead of mixing raw Empty blocks with framework-level fallbacks."
        />

        <div className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Vendor catalog" titleClassName="text-sm font-medium" />
            <OpspilotProviderEmptyState
              variant="vendor"
              description="No provider vendors have been configured yet."
            />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Model management" titleClassName="text-sm font-medium" />
            <OpspilotProviderEmptyState
              variant="model"
              description="No models are available for the selected provider."
            />
          </div>
        </div>

        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
          <SectionHeader
            spacing="compact"
            title="Generic fallback"
            titleClassName="text-sm font-medium"
            description="The same provider empty-state primitive also covers neutral no-data panels when the surface is not specifically vendor- or model-scoped."
          />
          <OpspilotProviderEmptyState variant="generic" />
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Provider loading and catalog states"
          titleClassName="text-sm font-semibold"
          description="Vendor grids and model-tree navigation now share one governed provider loading language, while the live vendor grid contract also owns populated and empty catalog states."
        />

        <div className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Vendor grid loading" titleClassName="text-sm font-medium" />
            <OpspilotProviderGridSkeleton />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Model tree loading" titleClassName="text-sm font-medium" />
            <div style={{ height: 320 }}>
              <OpspilotProviderModelTreeSkeleton />
            </div>
          </div>
        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Vendor grid default" titleClassName="text-sm font-medium" />
            <OpspilotProviderVendorGrid
              vendors={providerVendors}
              loading={false}
              onOpen={() => undefined}
              onEdit={() => undefined}
              onDelete={() => undefined}
              onChange={() => undefined}
            />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Vendor grid empty" titleClassName="text-sm font-medium" />
            <OpspilotProviderVendorGrid
              vendors={[]}
              loading={false}
              onOpen={() => undefined}
              onEdit={() => undefined}
              onDelete={() => undefined}
              onChange={() => undefined}
            />
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Provider model sections and config fields"
          titleClassName="text-sm font-semibold"
          description="Model-management sections and vendor configuration fields stay governed inside the same provider workflow lane, with modal/detail variants expressed as business states rather than separate roots."
        />

        <div className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Model section populated" titleClassName="text-sm font-medium" />
            <OpspilotProviderModelSection
              type={'llm_model' as ProviderResourceType}
              title="LLM模型"
              count={providerModels.length}
              switchingKey={null}
              style={sectionStyle}
              getModelIdentifier={(model: Model) => model.model || ''}
              getTeamText={(model: Model) => Array.isArray(model.team_name) ? model.team_name.join('、') : '--'}
              onAdd={() => undefined}
              onEdit={() => undefined}
              onDelete={() => undefined}
              onToggleEnabled={() => undefined}
              models={providerModels}
            />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Model section empty" titleClassName="text-sm font-medium" />
            <OpspilotProviderModelSection
              type={'llm_model' as ProviderResourceType}
              title="LLM模型"
              count={0}
              switchingKey={null}
              style={sectionStyle}
              getModelIdentifier={(model: Model) => model.model || ''}
              getTeamText={(model: Model) => Array.isArray(model.team_name) ? model.team_name.join('、') : '--'}
              onAdd={() => undefined}
              onEdit={() => undefined}
              onDelete={() => undefined}
              onToggleEnabled={() => undefined}
              models={[]}
            />
          </div>
        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Modal config fields" titleClassName="text-sm font-medium" />
            <ProviderVendorConfigPreview variant="modal" mode="add" />
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-2)] p-4">
            <SectionHeader spacing="compact" title="Detail config fields" titleClassName="text-sm font-medium" />
            <ProviderVendorConfigPreview variant="detail" mode="edit" />
          </div>
        </div>
      </section>

      <section className="space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4">
        <SectionHeader
          spacing="flush"
          title="Entity card surface"
          titleClassName="text-sm font-semibold"
          description="EntityCard is the catalog grid surface shared between agent and skill pages. The same render path is reused for both card shapes; only the icon mapping and menu actions differ."
        />
        <div className="grid gap-4 md:grid-cols-2">
          <EntityCard
            id="agent-1"
            name="Smart Assistant"
            introduction="An AI-powered assistant for operations and maintenance tasks."
            created_by="admin"
            team_name="Default"
            team={[{ id: 1, name: 'Default' }]}
            redirectUrl="#"
            iconTypeMapping={['jiqiren2', 'Bot']}
            online
            onMenuClick={() => undefined}
          />
        </div>
      </section>
    </div>
  );
};

const meta = {
  title: 'Business/OpsPilot/FamilyOverview',
  component: FamilyOverview,
  decorators: [
    (Story) => (
      <div style={{ maxWidth: 1080, padding: 24, background: 'var(--color-bg-2)' }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof FamilyOverview>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Overview: Story = {};
