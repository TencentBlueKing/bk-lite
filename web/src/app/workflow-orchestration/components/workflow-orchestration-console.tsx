'use client';

import { ArrowLeftOutlined, CloseOutlined, CopyOutlined, HistoryOutlined, PlayCircleOutlined, PlusOutlined, SaveOutlined, SendOutlined, UploadOutlined } from '@ant-design/icons';
import { Background, BackgroundVariant, ReactFlow, type Connection, type Edge, type Node, useEdgesState, useNodesState } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { Alert, App, Button, Descriptions, Drawer, Empty, Form, Input, InputNumber, Popconfirm, Select, Space, Spin, Tag, Timeline, Typography, Upload } from 'antd';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import OperateModal from '@/components/operate-modal';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import useApiClient from '@/utils/request';
import { useTranslation } from '@/utils/i18n';
import { WorkflowCanvasEdge } from './workflow-canvas-edge';
import { defaultNodeInputValues, SchemaNodeField, SchemaNodeForm } from './schema-node-form';
import { WorkflowCanvasNode, type InteractiveWorkflowNodeData, type WorkflowNodeAction } from './workflow-canvas-node';
import { WorkflowCanvasActionRail, WorkflowCanvasControls, WorkflowCanvasEmptyState, WorkflowNodeInspector, WorkflowNodePickerPanel, type WorkflowPickerGroup } from './workflow-editor-surface';
import { AtomIcon } from './atom-icon';
import { FormSchemaEditor } from './form-schema-editor';
import { DocumentRenderForm } from './document-render-form';
import { FileSampleLinks } from './file-sample-links';
import { JobExecuteForm } from './job-execute-form';
import { JobTargetSelectionDialog } from './job-target-selection-dialog';
import { WORKFLOW_OVERLAY_MODAL_Z_INDEX } from './workflow-launch-dialog';
import { normalizeScheduleConfig, ScheduleTriggerEditor, type SchedulePreview } from './schedule-trigger-editor';
import { WebhookTriggerPanel, type WebhookTestSession } from './webhook-trigger-panel';
import { missingRequiredFields } from './workflow-schema-form';
import { defaultTriggerRuntimeInputs, WorkflowTriggerRuntimeForm } from './workflow-trigger-runtime-form';
import { OPSPILOT_ATOM_KEYS, OpsPilotAtomForm } from './opspilot-atom-form';
import { approvalDecisionReference, configureApprovalTask } from '../lib/approval-dsl';
import { localizeAtom } from '../lib/atom-localization';
import { buildWorkflowFlow, commonTriggerInputSchema, expandApprovalCanvasEdges, flattenTasks, projectApprovalCanvasEdges, workflowTriggerNodes, type WorkflowCanvasMetadata, type WorkflowReturnNode, type WorkflowTriggerNode } from '../lib/canvas-dsl';
import { configureConditionTask, type ConditionConfiguration, type ConditionOperator } from '../lib/condition-dsl';
import { layoutWorkflowCanvas } from '../lib/canvas-layout';
import { buildDataReferenceOptions, buildWorkflowOutputReferenceOptions, dataReferencePreview, resolveNodeTestInputs, type DataReferenceOption } from '../lib/data-references';
import { buildNodeTestInputContract, materializeNodeTestInputs } from '../lib/node-test-input-contract';
import type { AtomCatalogItem, ConductorDefinition, ConductorTask, ExecutionRecord, JsonSchema, PaginatedResponse, WorkflowRecord, WorkflowTriggerType, WorkflowVersionRecord } from '../lib/types';
import { useAutoRequest, useRequestCoordinator } from '../lib/use-request-coordinator';
import { createUnsavedWorkflowDraft } from '../lib/workflow-draft';
import { WorkflowPermission } from './workflow-permission';
import { AtomConfigTemplateActions } from './atom-config-template-actions';

const API = '/workflow_orchestration/api';
const EMPTY_TARGET_REFERENCES: string[] = [];
const nodeTypes = { workflowCanvas: WorkflowCanvasNode };
const edgeTypes = { workflowCanvas: WorkflowCanvasEdge };
const connectionLineStyle = { stroke: 'var(--color-border-3)', strokeWidth: 2 };
const TERMINAL_EXECUTION_STATUSES = new Set(['SUCCEEDED', 'FAILED', 'TIMED_OUT', 'TERMINATED']);
const CONDITION_OPERATOR_DEFAULTS: Record<ConditionOperator, string> = {
  EQ: '等于', NEQ: '不等于', GT: '大于', GTE: '大于等于', LT: '小于', LTE: '小于等于', CONTAINS: '包含',
  NOT_CONTAINS: '不包含', STARTS_WITH: '开头是', ENDS_WITH: '结尾是',
};
function buildScheduleOutputSchema(t: (key: string, defaultMessage?: string) => string): JsonSchema {
  return {
    type: 'object',
    properties: {
      triggered_at: { type: 'string', title: t('workflowOrchestration.editor.scheduleOutputTriggeredAt', '触发时间') },
      scheduled_at: { type: 'string', title: t('workflowOrchestration.editor.scheduleOutputScheduledAt', '计划时间') },
      timezone: { type: 'string', title: t('workflowOrchestration.editor.scheduleOutputTimezone', '生效时区') },
      schedule: { type: 'array', title: t('workflowOrchestration.editor.scheduleOutputRules', '调度规则'), items: { type: 'string' } },
      test: { type: 'boolean', title: t('workflowOrchestration.editor.scheduleOutputIsTest', '是否测试') },
    },
    required: ['triggered_at', 'scheduled_at', 'timezone', 'schedule', 'test'],
    additionalProperties: false,
  };
}
function buildWebhookInputSchema(t: (key: string, defaultMessage?: string) => string): JsonSchema {
  return {
    type: 'object',
    properties: {
      body: {
        type: 'object',
        title: t('workflowOrchestration.editor.webhookRequestBody', '请求正文'),
        properties: {},
        additionalProperties: true,
      },
    },
    required: ['body'],
    additionalProperties: false,
  };
}

interface NatsTestSession {
  token: string;
  subject: string;
  timeout_seconds: number;
}

interface NatsTestResult {
  event: Record<string, unknown>;
  inputs: Record<string, unknown>;
}

interface ReportTemplateReference {
  kind: 'uploaded';
  name: string;
  format: 'docx' | 'xlsx';
  size: number;
  placeholders: string[];
  token: string;
}

interface DocumentTestTemplateEcho {
  name: string;
  format: string;
  size?: number;
  placeholders: string[];
}

interface DocumentTestTemplateState {
  echo: DocumentTestTemplateEcho;
  uploaded?: ReportTemplateReference;
  snapshot?: Record<string, unknown>;
}

function asUploadedReportTemplate(value: unknown): ReportTemplateReference | undefined {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return undefined;
  const item = value as Record<string, unknown>;
  if (item.kind !== 'uploaded') return undefined;
  const format = String(item.format || '').toLowerCase();
  if (format !== 'docx' && format !== 'xlsx') return undefined;
  const token = String(item.token || '');
  if (!token) return undefined;
  return {
    kind: 'uploaded',
    name: String(item.name || `template.${format}`),
    format,
    size: typeof item.size === 'number' ? item.size : 0,
    placeholders: Array.isArray(item.placeholders) ? item.placeholders.map(String) : [],
    token,
  };
}

function asDocumentTestTemplateState(inputs: Record<string, unknown>): DocumentTestTemplateState | undefined {
  const uploaded = asUploadedReportTemplate(inputs.template);
  if (uploaded) {
    return {
      echo: {
        name: uploaded.name,
        format: uploaded.format,
        size: uploaded.size,
        placeholders: uploaded.placeholders,
      },
      uploaded,
    };
  }
  const snapshot = inputs.template_snapshot;
  if (!snapshot || typeof snapshot !== 'object' || Array.isArray(snapshot)) return undefined;
  const frozen = snapshot as Record<string, unknown>;
  const format = String(frozen.format || '').toLowerCase();
  if (format !== 'docx' && format !== 'xlsx') return undefined;
  const prefix = String(frozen.filename_prefix || 'report').trim() || 'report';
  return {
    echo: {
      name: `${prefix}.${format}`,
      format,
      size: typeof frozen.size === 'number' ? frozen.size : undefined,
      placeholders: [],
    },
    snapshot: frozen,
  };
}

function asDocumentTestDataObject(value: unknown): Record<string, unknown> | undefined {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return undefined;
  return value as Record<string, unknown>;
}

function conditionOperators(type: string | undefined, t: (id: string, defaultMessage?: string) => string) {
  const operators = Object.entries(CONDITION_OPERATOR_DEFAULTS).map(([value, label]) => ({ value: value as ConditionOperator, label: t(`workflowOrchestration.editor.operator.${value}`, label) }));
  if (type === 'integer' || type === 'number') return operators.filter((item) => ['EQ', 'NEQ', 'GT', 'GTE', 'LT', 'LTE'].includes(item.value));
  if (type === 'string') return operators.filter((item) => ['EQ', 'NEQ', 'CONTAINS', 'NOT_CONTAINS', 'STARTS_WITH', 'ENDS_WITH'].includes(item.value));
  if (type === 'array') return operators.filter((item) => ['EQ', 'NEQ', 'CONTAINS', 'NOT_CONTAINS'].includes(item.value));
  return operators.filter((item) => ['EQ', 'NEQ'].includes(item.value));
}

function notificationRecipientLabels(value: unknown, schema?: JsonSchema): string[] | null {
  if (!Array.isArray(value)) return null;
  const items = schema?.properties?.recipients?.items;
  const labels = items?.['x-enum-labels'] || {};
  const usernameToLabel = new Map(
    Object.entries(items?.['x-enum-usernames'] || {}).map(([id, username]) => [String(username), labels[id] || String(username)]),
  );
  return value.map((item) => {
    const raw = String(item);
    return labels[raw] || usernameToLabel.get(raw) || raw;
  });
}

function uniqueId(prefix: string, used: Set<string>) {
  let value = prefix;
  let suffix = 2;
  while (used.has(value)) value = `${prefix}_${suffix++}`;
  return value;
}

function updateTask(tasks: ConductorTask[], reference: string, patch: (task: ConductorTask) => ConductorTask): ConductorTask[] {
  return tasks.map((task) => ({
    ...(task.taskReferenceName === reference ? patch(task) : task),
    ...(task.forkTasks ? { forkTasks: task.forkTasks.map((branch) => updateTask(branch, reference, patch)) } : {}),
    ...(task.decisionCases ? { decisionCases: Object.fromEntries(Object.entries(task.decisionCases).map(([key, branch]) => [key, updateTask(branch, reference, patch)])) } : {}),
    ...(task.defaultCase ? { defaultCase: updateTask(task.defaultCase, reference, patch) } : {}),
  }));
}

function ConditionEditor({
  value,
  references,
  readOnly,
  nodeTitle,
  onChange,
  onNodeTitleChange,
}: {
  value: ConditionConfiguration;
  references: DataReferenceOption[];
  readOnly: boolean;
  nodeTitle: string;
  onChange: (value: ConditionConfiguration) => void;
  onNodeTitleChange: (value: string) => void;
}) {
  const { t } = useTranslation();
  const patchRule = (index: number, patch: Partial<ConditionConfiguration['rules'][number]>) => onChange({
    ...value,
    rules: value.rules.map((rule, ruleIndex) => ruleIndex === index ? { ...rule, ...patch } : rule),
  });
  return <Form className="flex flex-col gap-5" layout="vertical">
    <Form.Item className="mb-0" label={t('workflowOrchestration.editor.nodeName', '节点名称')} required>
      <Input disabled={readOnly} value={nodeTitle} placeholder={t('workflowOrchestration.editor.enterNodeName', '请输入节点名称')} onChange={(event) => onNodeTitleChange(event.target.value)} />
    </Form.Item>
    <Alert
      type="info"
      showIcon
      message={t('workflowOrchestration.editor.structuredConditionHint', '条件由结构化规则生成 Conductor SWITCH，不接受自由表达式')}
      description={t('workflowOrchestration.editor.conditionBooleanBranchHint', '多条规则按「满足全部 / 满足任意」合成一个判断结果，画布只提供「满足」和「不满足」两条出口，不会按条件条数拆成多路分支。')}
    />
    <Form.Item className="mb-0" label={t('workflowOrchestration.editor.ruleRelation', '规则关系')}><Select disabled={readOnly} value={value.logic} options={[{ value: 'ALL', label: t('workflowOrchestration.editor.matchAll', '满足全部') }, { value: 'ANY', label: t('workflowOrchestration.editor.matchAny', '满足任意一条') }]} onChange={(logic) => onChange({ ...value, logic })} /></Form.Item>
    <div className="flex flex-col gap-3">{value.rules.map((rule, index) => {
      const leftReference = references.find((item) => item.value === rule.left);
      const operators = conditionOperators(leftReference?.type, t);
      const compatibleRightReferences = references.filter((item) => item.type === leftReference?.type || (leftReference?.type === 'number' && item.type === 'integer'));
      return <section key={index} className="rounded-lg border border-[var(--color-border-1)] p-3">
      <Select showSearch optionFilterProp="label" disabled={readOnly} className="w-full" placeholder={t('workflowOrchestration.editor.selectLeftField', '选择左值字段')} value={rule.left || undefined} options={references.map((item) => ({ value: item.value, label: item.label }))} onChange={(left) => {
        const nextType = references.find((item) => item.value === left)?.type;
        const nextOperator = conditionOperators(nextType, t).some((item) => item.value === rule.operator) ? rule.operator : 'EQ';
        patchRule(index, { left, operator: nextOperator, right: '' });
      }} />
      <div className="mt-2 grid grid-cols-2 gap-2">
        <Select disabled={readOnly} value={rule.operator} options={operators} onChange={(operator) => patchRule(index, { operator })} />
        <Select disabled={readOnly} value={rule.rightKind} options={[{ value: 'literal', label: t('workflowOrchestration.editor.literal', '固定值') }, { value: 'reference', label: t('workflowOrchestration.editor.fieldReference', '字段引用') }]} onChange={(rightKind) => patchRule(index, { rightKind, right: '' })} />
      </div>
      <div className="mt-2">{rule.rightKind === 'reference'
        ? <Select showSearch optionFilterProp="label" disabled={readOnly} className="w-full" placeholder={t('workflowOrchestration.editor.selectRightField', '选择同类型右值字段')} value={String(rule.right || '') || undefined} options={compatibleRightReferences.map((item) => ({ value: item.value, label: item.label }))} onChange={(right) => patchRule(index, { right })} />
        : leftReference?.type === 'number' || leftReference?.type === 'integer'
          ? <InputNumber disabled={readOnly} className="w-full" placeholder={t('workflowOrchestration.editor.enterNumber', '输入数值')} value={typeof rule.right === 'number' ? rule.right : null} onChange={(right) => patchRule(index, { right })} />
          : leftReference?.type === 'boolean'
            ? <Select disabled={readOnly} className="w-full" value={typeof rule.right === 'boolean' ? rule.right : undefined} options={[{ value: true, label: t('common.yes', '是') }, { value: false, label: t('common.no', '否') }]} onChange={(right) => patchRule(index, { right })} />
            : <Input disabled={readOnly} placeholder={t('workflowOrchestration.editor.enterLiteral', '输入固定值')} value={String(rule.right ?? '')} onChange={(event) => patchRule(index, { right: event.target.value })} />}</div>
      {!readOnly && value.rules.length > 1 ? <WorkflowPermission operation="Edit"><Button className="mt-2 px-0!" type="link" danger size="small" onClick={() => onChange({ ...value, rules: value.rules.filter((_, ruleIndex) => ruleIndex !== index) })}>{t('workflowOrchestration.editor.deleteCondition', '删除条件')}</Button></WorkflowPermission> : null}
    </section>;
    })}</div>
    {!readOnly && value.rules.length < 10 ? <WorkflowPermission operation="Edit" className="block"><Button block icon={<PlusOutlined />} onClick={() => onChange({ ...value, rules: [...value.rules, { left: '${system.execution_id}', operator: 'EQ', rightKind: 'literal', right: '' }] })}>{t('workflowOrchestration.editor.addCondition', '添加条件')}</Button></WorkflowPermission> : null}
  </Form>;
}

export function WorkflowOrchestrationConsole({ workflowId, initialName, mode = 'edit' }: { workflowId: number | null; initialName?: string; mode?: 'view' | 'edit' }) {
  const router = useRouter();
  const { message, modal } = App.useApp();
  const { get, patch, post } = useApiClient();
  const { t } = useTranslation();
  const scheduleOutputSchema = useMemo(() => buildScheduleOutputSchema(t), [t]);
  const webhookInputSchema = useMemo(() => buildWebhookInputSchema(t), [t]);
  const { convertToLocalizedTime } = useLocalizedTime();
  const effectiveInitialName = initialName || t('workflowOrchestration.editor.newWorkflow', '新建流程');
  const [workflow, setWorkflow] = useState<WorkflowRecord>();
  const readOnly = mode === 'view' || (workflow?.permission !== undefined && !workflow.permission.includes('Operate'));
  const [definition, setDefinition] = useState<ConductorDefinition>();
  const [metadata, setMetadata] = useState<WorkflowCanvasMetadata>({});
  const [atoms, setAtoms] = useState<AtomCatalogItem[]>([]);
  const [nodes, setNodes, onNodesChange] = useNodesState<Node<InteractiveWorkflowNodeData>>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [selectedId, setSelectedId] = useState<string>();
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pendingSource, setPendingSource] = useState<{ id: string; handle?: string }>();
  const [query, setQuery] = useState('');
  const [versions, setVersions] = useState<WorkflowVersionRecord[]>([]);
  const [versionsOpen, setVersionsOpen] = useState(false);
  const [versionsLoading, setVersionsLoading] = useState(false);
  const [debugOpen, setDebugOpen] = useState(false);
  const [debugTriggerId, setDebugTriggerId] = useState('');
  const [debugInputs, setDebugInputs] = useState<Record<string, unknown>>({});
  const [debugExecution, setDebugExecution] = useState<ExecutionRecord>();
  const [nodeTestOpen, setNodeTestOpen] = useState(false);
  const [nodeTestBusy, setNodeTestBusy] = useState(false);
  const [nodeTestError, setNodeTestError] = useState('');
  const [nodeTestReference, setNodeTestReference] = useState('');
  const [nodeTestTriggerId, setNodeTestTriggerId] = useState('');
  const [nodeTestInputs, setNodeTestInputs] = useState<Record<string, unknown>>({});
  const [documentTestTemplate, setDocumentTestTemplate] = useState<DocumentTestTemplateState>();
  const [documentTestData, setDocumentTestData] = useState<unknown>();
  const [documentTemplateUploading, setDocumentTemplateUploading] = useState(false);
  const [natsTestSession, setNatsTestSession] = useState<NatsTestSession>();
  const [natsTestBusy, setNatsTestBusy] = useState(false);
  const [natsTestError, setNatsTestError] = useState('');
  const natsTestAbort = useRef<AbortController | undefined>(undefined);
  const [webhookTestSession, setWebhookTestSession] = useState<WebhookTestSession>();
  const [webhookTestBusy, setWebhookTestBusy] = useState(false);
  const [webhookTestError, setWebhookTestError] = useState('');
  const webhookTestAbort = useRef<AbortController | undefined>(undefined);
  const [jobTargetSelectorOpen, setJobTargetSelectorOpen] = useState(false);
  const [jobTargetSelectorPurpose, setJobTargetSelectorPurpose] = useState<'params' | 'test'>('params');
  const [jobTestTargetsField, setJobTestTargetsField] = useState('');
  const [jobTargetRecords, setJobTargetRecords] = useState<Record<string, import('../lib/types').NodeTarget>>({});
  const [schedulePreview, setSchedulePreview] = useState<SchedulePreview>();
  const [schedulePreviewBusy, setSchedulePreviewBusy] = useState(false);
  const [schedulePreviewError, setSchedulePreviewError] = useState('');
  const [issues, setIssues] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const requestCoordinator = useRequestCoordinator(setLoading);
  const versionsRequestCoordinator = useRequestCoordinator(setVersionsLoading);
  const triggerLabels: Record<WorkflowTriggerType, string> = {
    FORM: t('workflowOrchestration.editor.formTrigger', '表单触发器'),
    SCHEDULE: t('workflowOrchestration.editor.scheduleTrigger', '定时触发器'),
    WEBHOOK: t('workflowOrchestration.editor.webhookTrigger', 'Webhook 触发器'),
    NATS: t('workflowOrchestration.editor.natsTrigger', '事件触发器（NATS）'),
  };
  const returnLabels: Record<WorkflowReturnNode['return_type'], string> = {
    WEBHOOK: t('workflowOrchestration.editor.webhookResponse', 'Webhook 响应'),
  };

  const rebuild = useCallback((nextDefinition: ConductorDefinition, nextMetadata: WorkflowCanvasMetadata, catalog: AtomCatalogItem[]) => {
    const localizedCatalog = catalog.map((item) => localizeAtom(item, t));
    const labels = Object.fromEntries(localizedCatalog.map((item) => [item.key, item.name]));
    const categories = Object.fromEntries(localizedCatalog.map((item) => [item.key, item.category]));
    const flow = buildWorkflowFlow(nextDefinition, nextMetadata, labels, categories);
    setNodes(flow.nodes);
    setEdges(flow.edges);
  }, [setEdges, setNodes, t]);

  const load = useCallback(async () => {
    const ticket = requestCoordinator.begin({ visible: true });
    if (!ticket) return;
    try {
      if (workflowId === null) {
        const catalog = await get<AtomCatalogItem[]>(`${API}/workflows/atoms/`, { signal: ticket.signal });
        if (!requestCoordinator.shouldApply(ticket)) return;
        const draft = createUnsavedWorkflowDraft(effectiveInitialName, {
          riskSummary: t('workflowOrchestration.editor.blankWorkflowRisk', '空白流程，尚未添加节点。'),
        });
        setWorkflow(draft.workflow); setDefinition(draft.definition); setMetadata(draft.metadata); setAtoms(catalog || []);
        rebuild(draft.definition, draft.metadata, catalog || []);
        return;
      }
      const [record, catalog] = await Promise.all([
        get<WorkflowRecord>(`${API}/workflows/${workflowId}/`, { signal: ticket.signal }),
        get<AtomCatalogItem[]>(`${API}/workflows/atoms/`, { signal: ticket.signal }),
      ]);
      if (!requestCoordinator.shouldApply(ticket)) return;
      const rawMetadata = record.canvas_metadata as WorkflowCanvasMetadata;
      const nextMetadata: WorkflowCanvasMetadata = rawMetadata.trigger_nodes
        ? rawMetadata
        : { ...rawMetadata, trigger_nodes: workflowTriggerNodes(rawMetadata), return_nodes: rawMetadata.return_nodes || [] };
      setWorkflow(record); setDefinition(record.definition); setMetadata(nextMetadata); setAtoms(catalog || []);
      rebuild(record.definition, nextMetadata, catalog || []);
    } catch {
      if (requestCoordinator.shouldApply(ticket)) {
        setWorkflow(undefined);
        setDefinition(undefined);
        setAtoms([]);
      }
    } finally { requestCoordinator.finish(ticket); }
  }, [effectiveInitialName, get, rebuild, requestCoordinator, t, workflowId]);

  useAutoRequest(`workflow-editor:${workflowId ?? `new:${effectiveInitialName}`}`, load);
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty]);

  const tasks = useMemo(() => flattenTasks(definition?.tasks || []), [definition]);
  const selectedTask = tasks.find((task) => task.taskReferenceName === selectedId);
  const selectedTrigger = workflowTriggerNodes(metadata).find((item) => item.id === selectedId);
  const selectedReturn = (metadata.return_nodes || []).find((item) => item.id === selectedId);
  const localizedAtoms = useMemo(() => atoms.map((item) => localizeAtom(item, t)), [atoms, t]);
  const selectedAtom = localizedAtoms.find((item) => item.key === selectedTask?.name);
  const isOpsPilotStyleAtom = Boolean(selectedTask?.type === 'SIMPLE' && OPSPILOT_ATOM_KEYS.has(selectedTask.name));
  const referenceLabels = useMemo(() => ({
    triggerInput: t('workflowOrchestration.editor.triggerInput', '触发输入'),
    systemContext: t('workflowOrchestration.editor.systemContext', '系统上下文'),
    allOutputs: t('workflowOrchestration.editor.allOutputs', '全部输出'),
  }), [t]);
  const references = useMemo(() => selectedTask && definition ? buildDataReferenceOptions(definition, selectedTask.taskReferenceName, localizedAtoms, commonTriggerInputSchema(metadata), referenceLabels, metadata.edges) : [], [definition, localizedAtoms, metadata, referenceLabels, selectedTask]);
  const inspectorTriggers = useMemo(() => workflowTriggerNodes(metadata), [metadata]);
  const inspectorTestTrigger = inspectorTriggers.find((item) => item.id === nodeTestTriggerId) || inspectorTriggers.find((item) => item.trigger_type === 'FORM') || inspectorTriggers[0];
  const nodeTestInputContract = useMemo(() => buildNodeTestInputContract(selectedTask, selectedAtom?.input_schema, inspectorTestTrigger?.input_schema), [inspectorTestTrigger, selectedAtom?.input_schema, selectedTask]);
  const inspectorTestData = metadata.node_test_data || {};
  const inspectorTestInputs = inspectorTestTrigger && inspectorTestData[inspectorTestTrigger.id] && typeof inspectorTestData[inspectorTestTrigger.id] === 'object' && !Array.isArray(inspectorTestData[inspectorTestTrigger.id])
    ? inspectorTestData[inspectorTestTrigger.id] as Record<string, unknown>
    : {};
  const inspectorReferences = useMemo(() => references.map((item) => ({
    key: item.value,
    label: item.label,
    value: item.value,
    type: item.type,
    source: item.source,
    path: item.path,
    preview: dataReferencePreview(item, inspectorTestInputs, inspectorTestData),
  })), [inspectorTestData, inspectorTestInputs, references]);
  const returnReferences = useMemo(() => definition ? buildWorkflowOutputReferenceOptions(definition, localizedAtoms) : [], [definition, localizedAtoms]);
  const selectedCondition = selectedTask?.type === 'SWITCH' && selectedTask.name === 'condition'
    ? metadata.condition_nodes?.[selectedTask.taskReferenceName] || { logic: 'ALL' as const, rules: [{ left: '${system.execution_id}', operator: 'EQ' as const, rightKind: 'literal' as const, right: '' }] }
    : undefined;
  const visibleAtoms = localizedAtoms.filter((item) => !query.trim() || `${item.name} ${item.key} ${item.category}`.toLowerCase().includes(query.trim().toLowerCase()));
  const selectedScheduleConfigKey = selectedTrigger?.trigger_type === 'SCHEDULE'
    ? JSON.stringify(normalizeScheduleConfig(selectedTrigger.config))
    : '';
  const selectedScheduleId = selectedTrigger?.trigger_type === 'SCHEDULE' ? selectedTrigger.id : '';

  useEffect(() => {
    if (!inspectorOpen || !selectedScheduleId || !selectedScheduleConfigKey) {
      setSchedulePreview(undefined);
      setSchedulePreviewError('');
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(async () => {
      setSchedulePreviewBusy(true);
      setSchedulePreviewError('');
      try {
        const result = await post<SchedulePreview>(`${API}/triggers/schedule-preview/`, {
          config: JSON.parse(selectedScheduleConfigKey),
          count: 6,
        });
        if (!cancelled) setSchedulePreview(result);
      } catch (error) {
        if (!cancelled) {
          setSchedulePreview(undefined);
          setSchedulePreviewError(error instanceof Error ? error.message : t('workflowOrchestration.editor.schedulePreviewFailed', '无法计算下次执行时间'));
        }
      } finally {
        if (!cancelled) setSchedulePreviewBusy(false);
      }
    }, 300);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [inspectorOpen, post, selectedScheduleConfigKey, selectedScheduleId]);

  const snapshotMetadata = useCallback((): WorkflowCanvasMetadata => {
    const visibleEdges = edges.map(({ id, source, target, sourceHandle, targetHandle }) => ({ id, source, target, sourceHandle, targetHandle }));
    return {
      ...metadata,
      positions: Object.fromEntries(nodes.map((node) => [node.id, node.position])),
      edges: definition ? expandApprovalCanvasEdges(definition, visibleEdges) : visibleEdges,
    };
  }, [definition, edges, metadata, nodes]);

  const closeInspector = () => {
    natsTestAbort.current?.abort();
    natsTestAbort.current = undefined;
    setNatsTestBusy(false);
    setNatsTestSession(undefined);
    setNatsTestError('');
    webhookTestAbort.current?.abort();
    webhookTestAbort.current = undefined;
    setWebhookTestBusy(false);
    setWebhookTestSession(undefined);
    setWebhookTestError('');
    setInspectorOpen(false);
  };

  const commit = (nextDefinition: ConductorDefinition, nextMetadata = metadata) => {
    setDefinition(nextDefinition); setMetadata(nextMetadata); setDirty(true); rebuild(nextDefinition, nextMetadata, atoms);
  };

  const changeMetadata = (next: WorkflowCanvasMetadata) => {
    setMetadata(next); setDirty(true); if (definition) rebuild(definition, next, atoms);
  };

  const addNodeToCanvas = (target: string, nextDefinition: ConductorDefinition, nextMetadata: WorkflowCanvasMetadata) => {
    const projectedEdges = projectApprovalCanvasEdges(nextDefinition, nextMetadata.edges || []);
    const stagedVisibleEdges = pendingSource
      ? [
        ...projectedEdges.filter((edge) => !(pendingSource.handle && edge.source === pendingSource.id && (edge.sourceHandle || undefined) === pendingSource.handle)),
        { id: `${pendingSource.id}-${target}-${Date.now()}`, source: pendingSource.id, sourceHandle: pendingSource.handle, target },
      ]
      : projectedEdges;
    const stagedMetadata = { ...nextMetadata, edges: expandApprovalCanvasEdges(nextDefinition, stagedVisibleEdges) };
    commit(nextDefinition, stagedMetadata);
    setPendingSource(undefined);
    setSelectedId(target);
    setPickerOpen(false);
    setInspectorOpen(true);
  };

  const addAtom = (atom: AtomCatalogItem) => {
    if (!definition) return;
    const reference = uniqueId(atom.key.replace(/^bklite_/, '').replace(/[^a-z0-9_]/gi, '_'), new Set(tasks.map((item) => item.taskReferenceName)));
    const next = { ...definition, tasks: [...definition.tasks, { name: atom.key, taskReferenceName: reference, type: 'SIMPLE' as const, inputParameters: defaultNodeInputValues(atom.input_schema, atom.ui_schema) }] };
    addNodeToCanvas(reference, next, snapshotMetadata());
  };

  const addControl = (type: 'SWITCH' | 'HUMAN') => {
    if (!definition) return;
    const used = new Set(tasks.map((item) => item.taskReferenceName));
    let created: ConductorTask[] = [];
    if (type === 'HUMAN') {
      const approvalReference = uniqueId('approval', used);
      used.add(approvalReference);
      created = [
        { name: 'manual_approval', taskReferenceName: approvalReference, type: 'HUMAN', inputParameters: { interactionType: 'APPROVAL', title: t('workflowOrchestration.editor.humanApproval', '人工审批'), description: '', candidates: ['admin'], publicContext: {} } },
        {
          name: 'approval_decision', taskReferenceName: uniqueId(`${approvalReference}_decision`, used), type: 'SWITCH',
          inputParameters: { decision: `\${${approvalReference}.output.approved}` }, evaluatorType: 'value-param', expression: 'decision',
          decisionCases: { true: [], false: [] }, defaultCase: [],
        },
      ];
    }
    if (type === 'SWITCH') created = [{ name: 'condition', taskReferenceName: uniqueId('condition', used), type: 'SWITCH', decisionCases: { true: [], false: [] }, defaultCase: [] }];
    let next: ConductorDefinition = { ...definition, tasks: [...definition.tasks, ...created] };
    let nextMetadata = snapshotMetadata();
    if (type === 'HUMAN') {
      nextMetadata = {
        ...nextMetadata,
        node_titles: {
          ...(nextMetadata.node_titles || {}),
          [created[0].taskReferenceName]: t('workflowOrchestration.editor.humanApproval', '人工审批'),
        },
        edges: [
          ...(nextMetadata.edges || []),
          { id: `${created[0].taskReferenceName}-${created[1].taskReferenceName}`, source: created[0].taskReferenceName, target: created[1].taskReferenceName },
        ],
      };
    }
    if (type === 'SWITCH') {
      const config: ConditionConfiguration = { logic: 'ALL', rules: [{ left: '${system.execution_id}', operator: 'EQ', rightKind: 'literal', right: '' }] };
      next = configureConditionTask(next, created[0].taskReferenceName, config);
      nextMetadata = {
        ...nextMetadata,
        node_titles: {
          ...(nextMetadata.node_titles || {}),
          [created[0].taskReferenceName]: t('workflowOrchestration.editor.conditionBranch', '条件分支'),
        },
        condition_nodes: { ...(metadata.condition_nodes || {}), [created[0].taskReferenceName]: config },
      };
    }
    if (created[0]?.taskReferenceName) addNodeToCanvas(created[0].taskReferenceName, next, nextMetadata);
  };

  const addTrigger = (type: WorkflowTriggerType) => {
    if (!definition) return;
    const existing = workflowTriggerNodes(metadata);
    const id = uniqueId(`trigger_${type.toLowerCase()}`, new Set([...existing.map((item) => item.id), ...tasks.map((item) => item.taskReferenceName)]));
    const item: WorkflowTriggerNode = { id, name: triggerLabels[type], trigger_type: type, input_schema: type === 'NATS' ? { type: 'object', properties: {}, required: [], additionalProperties: true } : type === 'SCHEDULE' ? scheduleOutputSchema : type === 'WEBHOOK' ? webhookInputSchema : { type: 'object', properties: {}, required: [], additionalProperties: false }, config: type === 'SCHEDULE' ? { frequency: 'daily', time: ['02:00'] } : type === 'WEBHOOK' ? { response_mode: 'IMMEDIATE' } : {} };
    addNodeToCanvas(id, definition, { ...snapshotMetadata(), trigger_nodes: [...existing, item] });
  };

  const addReturn = (type: WorkflowReturnNode['return_type']) => {
    if (!definition) return;
    const existing = metadata.return_nodes || [];
    const id = uniqueId(`return_${type.toLowerCase()}`, new Set([...existing.map((item) => item.id), ...tasks.map((item) => item.taskReferenceName)]));
    const item: WorkflowReturnNode = { id, name: returnLabels[type], return_type: type, config: { body: '' } };
    addNodeToCanvas(id, definition, { ...snapshotMetadata(), return_nodes: [...existing, item] });
  };

  const removeNode = (id: string) => {
    if (!definition) return;
    const trigger = workflowTriggerNodes(metadata).find((item) => item.id === id);
    const returnNode = (metadata.return_nodes || []).find((item) => item.id === id);
    if (trigger) {
      const triggers = workflowTriggerNodes(metadata);
      const current = snapshotMetadata();
      const nextTestData = { ...(current.node_test_data || {}) };
      const nextPositions = { ...(current.positions || {}) };
      delete nextTestData[id];
      delete nextPositions[id];
      const nextMetadata = {
        ...current,
        trigger_nodes: triggers.filter((item) => item.id !== id),
        edges: edges.filter((edge) => edge.source !== id && edge.target !== id),
        node_test_data: nextTestData,
        positions: nextPositions,
      };
      changeMetadata({ ...nextMetadata, input_schema: commonTriggerInputSchema(nextMetadata) });
    } else if (returnNode) {
      changeMetadata({ ...snapshotMetadata(), return_nodes: (metadata.return_nodes || []).filter((item) => item.id !== id), edges: edges.filter((edge) => edge.source !== id && edge.target !== id) });
    } else if (definition.tasks.some((item) => item.taskReferenceName === id)) {
      const decisionReference = approvalDecisionReference(definition.tasks, id);
      const removedReferences = new Set([id, ...(decisionReference ? [decisionReference] : [])]);
      const next = { ...definition, tasks: definition.tasks.filter((item) => !removedReferences.has(item.taskReferenceName)) };
      const current = snapshotMetadata();
      commit(next, {
        ...current,
        edges: (current.edges || []).filter((edge) => !removedReferences.has(edge.source) && !removedReferences.has(edge.target)),
      });
    } else message.warning(t('workflowOrchestration.editor.adjustNestedNode', '嵌套节点请在所属控制节点中调整'));
    setSelectedId(undefined); setInspectorOpen(false);
  };

  const changeTaskInputs = (value: Record<string, unknown>) => {
    if (!definition || !selectedTask) return;
    setDefinition({ ...definition, tasks: updateTask(definition.tasks, selectedTask.taskReferenceName, (task) => ({ ...task, inputParameters: value })) });
    setDirty(true);
  };

  const changeTaskTitle = (value: string) => {
    if (!selectedTask) return;
    const nodeTitles = { ...(metadata.node_titles || {}) };
    if (value) nodeTitles[selectedTask.taskReferenceName] = value;
    else delete nodeTitles[selectedTask.taskReferenceName];
    changeMetadata({ ...snapshotMetadata(), node_titles: nodeTitles });
  };

  const cacheInspectorTestData = (key: string, value: unknown) => {
    setMetadata((current) => ({ ...current, node_test_data: { ...(current.node_test_data || {}), [key]: value } }));
    setDirty(true);
  };

  const cancelNatsTest = () => {
    natsTestAbort.current?.abort();
    natsTestAbort.current = undefined;
    setNatsTestBusy(false);
    setNatsTestSession(undefined);
    setNatsTestError('');
  };

  const startNatsTest = async (persistedWorkflowId = workflow?.id, trigger = selectedTrigger) => {
    if (!persistedWorkflowId || trigger?.trigger_type !== 'NATS') return;
    const nodeKey = trigger.id;
    natsTestAbort.current?.abort();
    const controller = new AbortController();
    natsTestAbort.current = controller;
    setNodeTestReference(nodeKey);
    setNatsTestBusy(true);
    setNatsTestError('');
    setNatsTestSession(undefined);
    try {
      const session = await post<NatsTestSession>(`${API}/triggers/nats-test-session/`, {
        workflow_id: persistedWorkflowId,
        node_key: nodeKey,
      });
      if (controller.signal.aborted) return;
      setNatsTestSession(session);
      const result = await post<NatsTestResult>(
        `${API}/triggers/nats-test-listen/`,
        { token: session.token },
        { signal: controller.signal, timeout: (session.timeout_seconds + 5) * 1000, suppressErrorNotification: true },
      );
      if (controller.signal.aborted) return;
      cacheInspectorTestData(nodeKey, result.inputs);
      message.success(t('workflowOrchestration.editor.natsEventCaptured', '已捕获 NATS 测试事件，payload 已回填到右侧'));
    } catch (error) {
      if (!controller.signal.aborted) setNatsTestError(error instanceof Error ? error.message : t('workflowOrchestration.editor.natsListenFailed', 'NATS 测试监听失败'));
    } finally {
      if (natsTestAbort.current === controller) natsTestAbort.current = undefined;
      if (!controller.signal.aborted) setNatsTestBusy(false);
    }
  };

  const cancelWebhookTest = () => {
    webhookTestAbort.current?.abort();
    webhookTestAbort.current = undefined;
    setWebhookTestBusy(false);
    setWebhookTestSession(undefined);
    setWebhookTestError('');
  };

  const startWebhookTest = async (persistedWorkflowId = workflow?.id, trigger = selectedTrigger) => {
    if (!persistedWorkflowId || trigger?.trigger_type !== 'WEBHOOK') return;
    const nodeKey = trigger.id;
    webhookTestAbort.current?.abort();
    const controller = new AbortController();
    webhookTestAbort.current = controller;
    setNodeTestReference(nodeKey);
    setWebhookTestBusy(true);
    setWebhookTestError('');
    setWebhookTestSession(undefined);
    try {
      const session = await post<WebhookTestSession>(`${API}/triggers/webhook-test-session/`, {
        workflow_id: persistedWorkflowId,
        node_key: nodeKey,
      });
      if (controller.signal.aborted) return;
      setWebhookTestSession(session);
      const result = await post<{ body: Record<string, unknown> }>(
        `${API}/triggers/webhook-test-listen/`,
        { token: session.token },
        { signal: controller.signal, timeout: (session.timeout_seconds + 5) * 1000, suppressErrorNotification: true },
      );
      if (controller.signal.aborted) return;
      cacheInspectorTestData(nodeKey, result);
      message.success(t('workflowOrchestration.editor.webhookRequestCaptured', '已捕获 Webhook 测试请求，请求正文已回填到右侧'));
    } catch (error) {
      if (!controller.signal.aborted) setWebhookTestError(error instanceof Error ? error.message : t('workflowOrchestration.editor.webhookListenFailed', 'Webhook 测试监听失败'));
    } finally {
      if (webhookTestAbort.current === controller) webhookTestAbort.current = undefined;
      if (!controller.signal.aborted) setWebhookTestBusy(false);
    }
  };

  const runScheduleTest = async (trigger = selectedTrigger) => {
    if (trigger?.trigger_type !== 'SCHEDULE') return;
    setNodeTestReference(trigger.id);
    setNodeTestBusy(true);
    setNodeTestError('');
    try {
      const result = await post<SchedulePreview>(`${API}/triggers/schedule-preview/`, {
        config: normalizeScheduleConfig(trigger.config),
        count: 6,
      });
      setSchedulePreview(result);
      cacheInspectorTestData(selectedTrigger.id, result.test_output);
      message.success(t('workflowOrchestration.editor.scheduleTestSucceeded', '已立即模拟一次定时触发，未创建正式调度'));
    } catch (error) {
      setNodeTestError(error instanceof Error ? error.message : t('workflowOrchestration.editor.scheduleTestFailed', '定时触发测试失败'));
    } finally {
      setNodeTestBusy(false);
    }
  };

  const runNodeTest = async (
    taskReference: string,
    triggerId: string,
    inputs: Record<string, unknown>,
    nodeInputsOverride?: Record<string, unknown>,
    persistedWorkflowId = workflow?.id,
  ) => {
    if (!persistedWorkflowId || !definition) return;
    const task = flattenTasks(definition.tasks).find((item) => item.taskReferenceName === taskReference);
    if (!task || task.type !== 'SIMPLE') return;
    const testData = { ...(metadata.node_test_data || {}), [triggerId]: inputs };
    const resolved = nodeInputsOverride
      ? { value: nodeInputsOverride, unresolved: [] }
      : resolveNodeTestInputs(task.inputParameters || {}, inputs, testData);
    if (resolved.unresolved.length) {
      const sources = resolved.unresolved.join('、');
      setNodeTestError(t('workflowOrchestration.editor.missingUpstreamTestData', '缺少上游测试数据：{sources}。请先测试对应上游节点。', { sources }));
      setNodeTestOpen(false);
      return;
    }
    setNodeTestBusy(true);
    setNodeTestError('');
    cacheInspectorTestData(triggerId, inputs);
    try {
      let execution = await post<ExecutionRecord>(`${API}/workflows/${persistedWorkflowId}/debug/`, {
        inputs,
        trigger_id: triggerId,
        task_reference: taskReference,
        node_inputs: resolved.value,
        confirmed: true,
        definition,
        canvas_metadata: metadata,
      });
      setDebugExecution(execution);
      setNodeTestOpen(false);
      for (let attempt = 0; attempt < 75 && !TERMINAL_EXECUTION_STATUSES.has(execution.status); attempt += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 800));
        execution = await get<ExecutionRecord>(`${API}/executions/${execution.id}/`);
        setDebugExecution(execution);
      }
      if (execution.status !== 'SUCCEEDED') {
        setNodeTestError(execution.error_message || t('workflowOrchestration.editor.nodeTestDidNotSucceed', '节点测试未成功完成'));
        return;
      }
      const output = Object.hasOwn(execution.output || {}, 'result') ? execution.output.result : execution.output;
      cacheInspectorTestData(taskReference, output);
      message.success(t('workflowOrchestration.editor.nodeTestSucceeded', '节点测试完成，输出已回填到右侧'));
    } catch (error) {
      setNodeTestError(error instanceof Error ? error.message : t('workflowOrchestration.editor.nodeTestDidNotSucceed', '节点测试未成功完成'));
    } finally {
      setNodeTestBusy(false);
    }
  };

  const prepareNodeTest = (taskReference: string, persistedWorkflowId = workflow?.id) => {
    if (!persistedWorkflowId || !definition) return;
    const trigger = inspectorTestTrigger;
    const task = flattenTasks(definition.tasks).find((item) => item.taskReferenceName === taskReference) || selectedTask;
    setNodeTestReference(taskReference);
    setNodeTestTriggerId(trigger?.id || '');
    setNodeTestError('');
    const atom = localizedAtoms.find((item) => item.key === task?.name);
    const testContract = buildNodeTestInputContract(task, atom?.input_schema, trigger?.input_schema);
    const seededInputs = { ...defaultTriggerRuntimeInputs(testContract.schema), ...inspectorTestInputs };
    const targetsField = Object.entries(testContract.nodeOverrides).find(([, field]) => field === 'targets')?.[0] || '';
    setJobTestTargetsField(targetsField);
    if (
      targetsField
      && Array.isArray(task?.inputParameters?.targets)
      && task.inputParameters.targets.every((item) => typeof item === 'string')
    ) {
      const seededTargets = seededInputs[targetsField];
      // defaultTriggerRuntimeInputs seeds arrays as []; still prefer node-fixed hosts for confirm.
      if (!Array.isArray(seededTargets) || seededTargets.length === 0) {
        seededInputs[targetsField] = task.inputParameters.targets;
      }
    }
    setNodeTestInputs(seededInputs);
    if (task?.name === 'bklite_document_render') {
      const configured = {
        ...(task.inputParameters || {}),
        ...(selectedTask?.taskReferenceName === taskReference ? selectedTask.inputParameters : {}),
      };
      setDocumentTestTemplate(asDocumentTestTemplateState(configured));
      setDocumentTestData(configured.data);
      setNodeTestOpen(true);
      return;
    }
    if (task?.name === 'bklite_http_request') {
      void runNodeTest(taskReference, trigger?.id || '', inspectorTestInputs, undefined, persistedWorkflowId);
      return;
    }
    if (task?.name === 'bklite_notification') {
      const configuredRecipients = task.inputParameters?.recipients;
      const recipientLabels = notificationRecipientLabels(configuredRecipients, atom?.input_schema);
      const recipients = recipientLabels
        ? recipientLabels.join('、') || t('workflowOrchestration.editor.noRecipientsConfigured', '未配置')
        : typeof configuredRecipients === 'string' && configuredRecipients.trim()
          ? configuredRecipients
          : t('workflowOrchestration.editor.upstreamRecipients', '由上游数据决定');
      modal.confirm({
        title: t('workflowOrchestration.editor.sendRealTestNotification', '发送真实测试通知？'),
        content: <div className="flex flex-col gap-2 text-sm">
          <p className="m-0 text-[var(--color-text-2)]">{t('workflowOrchestration.editor.realNotificationWarning', '将调用当前组织的真实通知渠道，请确认渠道、接收人和内容均属于测试范围。')}</p>
          <div><span className="text-[var(--color-text-3)]">{t('workflowOrchestration.editor.notificationRecipients', '接收人')}：</span>{recipients}</div>
        </div>,
        okText: t('workflowOrchestration.editor.sendTestNotification', '发送测试通知'),
        cancelText: t('common.cancel', '取消'),
        onOk: () => runNodeTest(taskReference, trigger?.id || '', inspectorTestInputs, undefined, persistedWorkflowId),
      });
      return;
    }
    if (!Object.keys(testContract.schema.properties || {}).length && atom?.safety_level === 'READ_ONLY') {
      void runNodeTest(taskReference, trigger?.id || '', inspectorTestInputs, undefined, persistedWorkflowId);
      return;
    }
    setNodeTestOpen(true);
  };

  const prepareFormTriggerTest = (trigger: WorkflowTriggerNode) => {
    const cached = metadata.node_test_data?.[trigger.id];
    setNodeTestReference(trigger.id);
    setNodeTestTriggerId(trigger.id);
    setNodeTestInputs(cached && typeof cached === 'object' && !Array.isArray(cached)
      ? cached as Record<string, unknown>
      : defaultTriggerRuntimeInputs(trigger.input_schema));
    setNodeTestError('');
    setNodeTestOpen(true);
  };

  const runFormTriggerTest = (trigger: WorkflowTriggerNode) => {
    const missing = missingRequiredFields(trigger.input_schema, nodeTestInputs);
    if (missing.length) {
      message.warning(t('workflowOrchestration.form.completeRequired', '请完成必填字段：{fields}', {
        fields: missing.map((key) => trigger.input_schema.properties?.[key]?.title || key).join('、'),
      }));
      return;
    }
    cacheInspectorTestData(trigger.id, nodeTestInputs);
    setNodeTestOpen(false);
    message.success(t('workflowOrchestration.editor.formTriggerTestReady', '表单输入已回填，可继续测试下游节点'));
  };

  const uploadDocumentTestTemplate = async (file: File) => {
    if (!workflow?.id) {
      message.error(t('workflowOrchestration.editor.saveBeforeNodeTest', '请先保存流程草稿，再执行当前节点'));
      return;
    }
    const extension = file.name.toLowerCase().split('.').pop();
    if (!extension || !['docx', 'xlsx'].includes(extension)) {
      message.error(t('workflowOrchestration.editor.invalidReportTemplateType', '仅支持 .docx 或 .xlsx 模板'));
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      message.error(t('workflowOrchestration.editor.reportTemplateTooLarge', '模板文件不能超过 5 MiB'));
      return;
    }
    setDocumentTemplateUploading(true);
    try {
      const body = new FormData();
      body.append('file', file);
      const uploaded = await post<ReportTemplateReference>(`${API}/workflows/${workflow.id}/report-template-test-upload/`, body, { headers: { 'Content-Type': 'multipart/form-data' } });
      setDocumentTestTemplate({
        echo: {
          name: uploaded.name,
          format: uploaded.format,
          size: uploaded.size,
          placeholders: uploaded.placeholders,
        },
        uploaded,
      });
      message.success(t('workflowOrchestration.editor.reportTemplateReady', '测试模板已上传并完成占位符检查'));
    } finally {
      setDocumentTemplateUploading(false);
    }
  };

  const runDocumentNodeTest = () => {
    if (!inspectorTestTrigger || !definition) return;
    if (!documentTestTemplate?.uploaded && !documentTestTemplate?.snapshot) {
      message.error(t('workflowOrchestration.editor.uploadTemplateBeforeTest', '请先上传 Word 或 Excel 测试模板'));
      return;
    }
    if (documentTestData === undefined || documentTestData === null || documentTestData === '') {
      message.error(t('workflowOrchestration.editor.testDocumentDataRequired', '请填写测试文档数据'));
      return;
    }
    const testData = { ...(metadata.node_test_data || {}), [inspectorTestTrigger.id]: nodeTestInputs };
    const resolved = resolveNodeTestInputs({ data: documentTestData }, nodeTestInputs, testData);
    if (resolved.unresolved.length) {
      setNodeTestError(t(
        'workflowOrchestration.editor.missingUpstreamTestData',
        '缺少上游测试数据：{sources}。请先测试对应上游节点。',
        { sources: resolved.unresolved.join('、') },
      ));
      return;
    }
    const data = asDocumentTestDataObject(resolved.value.data);
    if (!data) {
      message.error(t('workflowOrchestration.editor.testDocumentDataRequired', '请填写测试文档数据'));
      return;
    }
    const nodeInputs: Record<string, unknown> = { data };
    if (documentTestTemplate.uploaded) nodeInputs.template = documentTestTemplate.uploaded;
    else nodeInputs.template_snapshot = documentTestTemplate.snapshot;
    void runNodeTest(nodeTestReference, inspectorTestTrigger.id, nodeTestInputs, nodeInputs);
  };

  const runConfiguredNodeTest = () => {
    if (!selectedTask || !inspectorTestTrigger) return;
    const missing = missingRequiredFields(nodeTestInputContract.schema, nodeTestInputs);
    if (missing.length) {
      message.warning(t('workflowOrchestration.form.completeRequired', '请完成必填字段：{fields}', {
        fields: missing.map((key) => nodeTestInputContract.schema.properties?.[key]?.title || key).join('、'),
      }));
      return;
    }
    const materialized = materializeNodeTestInputs(
      nodeTestInputContract,
      selectedTask.inputParameters || {},
      nodeTestInputs,
      inspectorTestData,
    );
    if (materialized.unresolved.length) {
      setNodeTestError(t('workflowOrchestration.editor.missingUpstreamTestData', '缺少上游测试数据：{sources}。请先测试对应上游节点。', { sources: materialized.unresolved.join('、') }));
      return;
    }
    void runNodeTest(
      nodeTestReference,
      inspectorTestTrigger.id,
      materialized.workflowInputs,
      materialized.nodeInputs,
    );
  };

  const changeTrigger = (patch: Partial<WorkflowTriggerNode>) => {
    if (!selectedTrigger) return;
    const currentCanvas = snapshotMetadata();
    const triggers = workflowTriggerNodes(currentCanvas).map((item) => item.id === selectedTrigger.id ? { ...item, ...patch } : item);
    const nextMetadata = { ...currentCanvas, trigger_nodes: triggers };
    changeMetadata({ ...nextMetadata, input_schema: commonTriggerInputSchema(nextMetadata) });
  };

  const changeReturn = (patch: Partial<WorkflowReturnNode>) => {
    if (!selectedReturn) return;
    const currentCanvas = snapshotMetadata();
    changeMetadata({ ...currentCanvas, return_nodes: (currentCanvas.return_nodes || []).map((item) => item.id === selectedReturn.id ? { ...item, ...patch } : item) });
  };

  const changeCondition = (config: ConditionConfiguration) => {
    if (!definition || !selectedTask || selectedTask.type !== 'SWITCH') return;
    setDefinition(configureConditionTask(definition, selectedTask.taskReferenceName, config));
    setMetadata((current) => ({ ...current, condition_nodes: { ...(current.condition_nodes || {}), [selectedTask.taskReferenceName]: config } }));
    setDirty(true);
  };

  const changeApproval = (patch: Partial<{ title: string; description: string; candidates: string[]; publicContext: Record<string, string> }>) => {
    if (!definition || !selectedTask || selectedTask.type !== 'HUMAN') return;
    const inputs = selectedTask.inputParameters || {};
    setDefinition(configureApprovalTask(definition, selectedTask.taskReferenceName, {
      title: patch.title ?? String(inputs.title || ''),
      description: patch.description ?? String(inputs.description || ''),
      candidates: patch.candidates ?? (inputs.candidates || []) as string[],
      publicContext: patch.publicContext ?? (inputs.publicContext || {}) as Record<string, string>,
    }));
    setDirty(true);
  };

  // MVP 暂不展示工具栏「校验」；发布/调试已覆盖同一套服务端校验。改为 true 即可重新开放按钮。
  const showValidateButton = false;

  const validate = async () => {
    if (!workflow || !definition) return;
    if (!workflow.id) { message.info(t('workflowOrchestration.editor.saveBeforeValidate', '请先保存草稿再校验')); return; }
    try {
      await post(`${API}/workflows/${workflow.id}/validate/`, { definition, canvas_metadata: snapshotMetadata() });
      setIssues([]); message.success(t('workflowOrchestration.editor.validationPassed', '流程结构、节点配置、引用与类型校验通过'));
    } catch (error) { setIssues([error instanceof Error ? error.message : t('workflowOrchestration.editor.validationFailed', '流程校验未通过')]); }
  };

  const persistDraft = async (): Promise<WorkflowRecord | undefined> => {
    if (!workflow || !definition) return;
    const payload = { name: workflow.name.trim(), description: workflow.description, definition, canvas_metadata: snapshotMetadata() };
    const saved = workflow.id
      ? await patch<WorkflowRecord>(`${API}/workflows/${workflow.id}/`, { ...payload, draft_revision: workflow.draft_revision })
      : await post<WorkflowRecord>(`${API}/workflows/`, { ...payload, starter: 'blank' });
    setWorkflow(saved); setDefinition(saved.definition); setMetadata(saved.canvas_metadata as WorkflowCanvasMetadata); setDirty(false);
    if (!workflow.id) router.replace(`/workflow-orchestration/workflows/${saved.id}?mode=edit`);
    return saved;
  };

  const save = async () => {
    setBusy(true);
    try {
      const saved = await persistDraft();
      if (!saved) return;
      message.success(t('workflowOrchestration.editor.draftSaved', '草稿已保存'));
    } finally { setBusy(false); }
  };

  const withPersistedDraft = (continueAction: (workflowId: number) => void) => {
    if (workflow?.id) {
      continueAction(workflow.id);
      return;
    }
    modal.confirm({
      title: t('workflowOrchestration.editor.saveDraftBeforeTestTitle', '保存草稿后继续测试？'),
      content: t('workflowOrchestration.editor.saveDraftBeforeTestHint', '测试需要流程标识。确认后会先保存当前草稿，再继续本次操作。'),
      okText: t('workflowOrchestration.editor.saveAndContinueTest', '保存并继续'),
      cancelText: t('common.cancel', '取消'),
      onOk: async () => {
        setBusy(true);
        try {
          const saved = await persistDraft();
          if (!saved) return;
          message.success(t('workflowOrchestration.editor.draftSavedForTest', '草稿已保存，请继续测试'));
          continueAction(saved.id);
        } finally {
          setBusy(false);
        }
      },
    });
  };

  const publish = async () => {
    if (!workflow || !definition) return;
    setBusy(true);
    try {
      const canvasMetadata = snapshotMetadata();
      const persisted = workflow.id
        ? workflow
        : await post<WorkflowRecord>(`${API}/workflows/`, { name: workflow.name.trim(), description: workflow.description, definition, canvas_metadata: canvasMetadata, starter: 'blank' });
      const published = await post<WorkflowRecord>(`${API}/workflows/${persisted.id}/publish/`, { name: persisted.name, description: persisted.description, definition, canvas_metadata: canvasMetadata, draft_revision: persisted.draft_revision });
      setWorkflow(published); setDefinition(published.definition); setMetadata(published.canvas_metadata as WorkflowCanvasMetadata); setDirty(false);
      if (!workflow.id) router.replace(`/workflow-orchestration/workflows/${published.id}?mode=edit`);
      message.success(t('workflowOrchestration.editor.publishedSuccess', 'v{version} 已发布，流程{status}', { version: published.current_version, status: published.enabled ? t('workflowOrchestration.editor.remainsEnabled', '保持启用') : t('workflowOrchestration.editor.remainsDisabled', '保持停用') }));
    } finally { setBusy(false); }
  };

  const debug = async (persistedWorkflowId = workflow?.id) => {
    if (!persistedWorkflowId || !definition || !debugTrigger) return;
    const missing = missingRequiredFields(debugTrigger.input_schema, debugInputs);
    if (missing.length) {
      message.warning(t('workflowOrchestration.form.completeRequired', '请完成必填字段：{fields}', {
        fields: missing.map((key) => debugTrigger.input_schema.properties?.[key]?.title || key).join('、'),
      }));
      return;
    }
    const execution = await post<ExecutionRecord>(`${API}/workflows/${persistedWorkflowId}/debug/`, { inputs: debugInputs, trigger_id: debugTrigger.id, definition, canvas_metadata: snapshotMetadata() });
    setDebugExecution(execution); setDebugOpen(false); message.success(t('workflowOrchestration.editor.debugStartedFromSnapshot', '已使用当前未保存快照启动调试'));
  };

  const openDebugDialog = () => {
    const preferred = workflowTriggerNodes(metadata).find((item) => item.trigger_type === 'FORM') || workflowTriggerNodes(metadata)[0];
    if (!preferred) {
      message.warning(t('workflowOrchestration.editor.noTriggerForDebug', '请先添加触发器再调试流程'));
      return;
    }
    withPersistedDraft(() => {
      setDebugTriggerId(preferred.id);
      const cached = metadata.node_test_data?.[preferred.id];
      setDebugInputs(cached && typeof cached === 'object' && !Array.isArray(cached)
        ? cached as Record<string, unknown>
        : defaultTriggerRuntimeInputs(preferred.input_schema));
      setDebugOpen(true);
    });
  };

  const openVersions = async () => {
    if (!workflow?.id) return;
    setVersionsOpen(true);
    const ticket = versionsRequestCoordinator.begin({ visible: true });
    if (!ticket) return;
    try {
      const response = await get<PaginatedResponse<WorkflowVersionRecord>>(`${API}/workflows/${workflow.id}/versions/?page_size=100`, { signal: ticket.signal });
      if (versionsRequestCoordinator.shouldApply(ticket)) setVersions(response?.items || []);
    } catch {
      if (versionsRequestCoordinator.shouldApply(ticket)) setVersions([]);
    } finally {
      versionsRequestCoordinator.finish(ticket);
    }
  };

  const restoreVersion = async (version: number) => {
    if (!workflow) return;
    const restored = await post<WorkflowRecord>(`${API}/workflows/${workflow.id}/versions/${version}/restore-draft/`, { draft_revision: workflow.draft_revision });
    const nextMetadata = restored.canvas_metadata as WorkflowCanvasMetadata;
    setWorkflow(restored); setDefinition(restored.definition); setMetadata(nextMetadata);
    rebuild(restored.definition, nextMetadata, atoms); setDirty(false); setVersionsOpen(false);
    message.success(t('workflowOrchestration.editor.versionRestored', '已基于 v{version} 覆盖当前草稿，当前生产版本未改变', { version }));
  };

  const action = (kind: WorkflowNodeAction, id: string, sourceHandle?: string) => {
    setSelectedId(id);
    if (kind === 'add') {
      setPendingSource({ id, handle: sourceHandle });
      setInspectorOpen(false);
      setPickerOpen(true);
    }
    if (kind === 'configure') setInspectorOpen(true);
    if (kind === 'test' && definition) {
      const trigger = workflowTriggerNodes(metadata).find((item) => item.id === id);
      if (trigger?.trigger_type === 'FORM') withPersistedDraft(() => prepareFormTriggerTest(trigger));
      else if (trigger?.trigger_type === 'SCHEDULE') void runScheduleTest(trigger);
      else if (trigger?.trigger_type === 'NATS') withPersistedDraft((savedWorkflowId) => void startNatsTest(savedWorkflowId, trigger));
      else if (trigger?.trigger_type === 'WEBHOOK') withPersistedDraft((savedWorkflowId) => void startWebhookTest(savedWorkflowId, trigger));
      else if (flattenTasks(definition.tasks).some((item) => item.taskReferenceName === id)) withPersistedDraft((savedWorkflowId) => prepareNodeTest(id, savedWorkflowId));
    }
    if (kind === 'delete') modal.confirm({ title: t('workflowOrchestration.editor.deleteNodeConfirm', '删除当前节点？'), content: t('workflowOrchestration.editor.deleteNodeHint', '与该节点相连的路径也会被删除。'), okText: t('common.delete', '删除'), okButtonProps: { danger: true }, onOk: () => removeNode(id) });
  };

  if (loading || !workflow || !definition) return <div className="flex h-full min-h-0 max-h-full items-center justify-center overflow-hidden"><Spin aria-label={t('workflowOrchestration.editor.loadingWorkflow', '加载流程')} /></div>;

  const selectedNode = nodes.find((item) => item.id === selectedId);
  const debugTriggers = workflowTriggerNodes(metadata);
  const debugTrigger = debugTriggers.find((item) => item.id === debugTriggerId) || debugTriggers[0];
  const interactive = nodes.map((node) => ({ ...node, data: { ...node.data, readOnly, locked: Boolean(debugExecution), onAction: action } }));
  const interactiveEdges = edges.map((edge) => ({
    ...edge,
    type: 'workflowCanvas',
    sourceHandle: edge.sourceHandle ?? (nodes.find((node) => node.id === edge.source)?.data.taskType === 'SWITCH' ? 'true' : undefined),
  }));
  const tidyCanvas = async () => {
    setNodes(await layoutWorkflowCanvas(nodes, edges));
    setDirty(true);
  };
  const matchesPickerQuery = (value: string) => !query.trim() || value.toLowerCase().includes(query.trim().toLowerCase());
  const firstNodeOnly = nodes.length === 0;
  const waitingWebhookExists = workflowTriggerNodes(metadata).some((item) => item.trigger_type === 'WEBHOOK' && item.config.response_mode === 'WAIT');
  const webhookResponseExists = (metadata.return_nodes || []).some((item) => item.return_type === 'WEBHOOK');
  const allPickerGroups: WorkflowPickerGroup[] = [
    {
      key: 'trigger',
      title: t('workflowOrchestration.atom.nodeType.trigger', '触发'),
      description: t('workflowOrchestration.editor.triggerGroupHint', '定义流程从何时、以什么输入开始。'),
      items: (pendingSource ? [] : ['FORM', 'SCHEDULE', 'WEBHOOK', 'NATS'] as const)
        .filter((type) => matchesPickerQuery(`${triggerLabels[type]} ${type}`))
        .map((type) => ({ key: type, title: triggerLabels[type], description: t('workflowOrchestration.editor.createEntry', '创建一个流程入口'), icon: <AtomIcon nodeType="TRIGGER" className="text-2xl" />, onClick: () => addTrigger(type) })),
    },
    {
      key: 'action',
      title: t('workflowOrchestration.atom.nodeType.action', '动作'),
      description: t('workflowOrchestration.editor.actionGroupHint', '调用作业平台和其他已注册的运维能力。'),
      items: visibleAtoms.map((atom) => ({
        key: atom.key,
        title: atom.name,
        description: atom.description,
        icon: <AtomIcon nodeType="ACTION" category={atom.category} className="text-2xl" />,
        onClick: () => addAtom(atom),
      })),
    },
    {
      key: 'control',
      title: t('workflowOrchestration.atom.nodeType.control', '控制'),
      description: t('workflowOrchestration.editor.controlGroupHint', '分支、汇聚或暂停流程等待人工决定。'),
      items: [
        { key: 'condition', title: t('workflowOrchestration.editor.conditionBranch', '条件分支'), description: t('workflowOrchestration.editor.conditionBranchHint', '根据结构化条件选择执行路径'), icon: <AtomIcon nodeType="CONTROL" controlKind="condition" className="text-2xl" />, onClick: () => addControl('SWITCH') },
        { key: 'approval', title: t('workflowOrchestration.editor.humanApproval', '人工审批'), description: t('workflowOrchestration.editor.humanApprovalHint', '等待审批通过或驳回后继续'), icon: <AtomIcon nodeType="CONTROL" controlKind="approval" className="text-2xl" />, onClick: () => addControl('HUMAN') },
      ].filter((item) => matchesPickerQuery(`${item.title} ${item.description}`)),
    },
    {
      key: 'return',
      title: t('workflowOrchestration.atom.nodeType.return', '响应'),
      description: t('workflowOrchestration.editor.responseGroupHint', '把流程结果返回给对应的触发入口。'),
      items: (waitingWebhookExists && !webhookResponseExists ? ['WEBHOOK'] as const : [])
        .filter((type) => matchesPickerQuery(`${returnLabels[type]} ${type}`))
        .map((type) => ({ key: type, title: returnLabels[type], description: t('workflowOrchestration.editor.returnHint', '结束当前路径并返回结果'), icon: <AtomIcon nodeType="RETURN" className="text-2xl" />, onClick: () => addReturn(type) })),
    },
  ];
  const pickerGroups = allPickerGroups.filter((group) => group.items.length > 0 && (!firstNodeOnly || group.key === 'trigger'));

  return <main className="flex h-full min-h-0 max-h-full w-full flex-col overflow-hidden bg-[var(--color-bg-1)]">
    <header className="relative flex h-[65px] shrink-0 items-center gap-3 border-b border-[var(--color-border-1)] bg-[var(--color-bg)] px-5">
      <WorkflowPermission operation="View"><Button type="text" aria-label={t('common.back', '返回')} icon={<ArrowLeftOutlined />} onClick={() => dirty ? modal.confirm({ title: t('workflowOrchestration.editor.leaveConfirm', '离开并丢失未保存修改？'), okText: t('workflowOrchestration.editor.leave', '离开'), okButtonProps: { danger: true }, onOk: () => router.push('/workflow-orchestration/workflows') }) : router.push('/workflow-orchestration/workflows')} /></WorkflowPermission>
      <div className="min-w-0 flex-1">
        <Input variant="borderless" className="max-w-96 font-semibold" value={workflow.name} readOnly={readOnly} onChange={(event) => { setWorkflow({ ...workflow, name: event.target.value }); setDirty(true); }} />
        <div className="flex items-center gap-2 px-3 text-xs text-[var(--color-text-3)]">
          {workflow.current_version ? <Tag color={workflow.enabled ? 'success' : 'default'}>{workflow.enabled ? t('workflowOrchestration.status.enabled', '已启用') : t('workflowOrchestration.status.disabled', '已停用')} · v{workflow.current_version}</Tag> : <Tag>{t('workflowOrchestration.status.draftOnly', '纯草稿')}</Tag>}
          {(workflow.has_draft || dirty) && workflow.current_version > 0 ? t('workflowOrchestration.editor.hasUnpublishedChanges', '有未发布更改') : t('workflowOrchestration.editor.publishedUnaffected', '发布版本不受草稿修改影响')}
        </div>
      </div>
      <WorkflowPermission operation="View" instancePermissions={workflow.permission}><Button disabled={!workflow.id} onClick={() => router.push(`/workflow-orchestration/executions?query=${encodeURIComponent(workflow.name)}`)}>{t('workflowOrchestration.execution.records', '执行记录')}</Button></WorkflowPermission>
      <WorkflowPermission operation="View" instancePermissions={workflow.permission}><Button disabled={!workflow.id} icon={<HistoryOutlined />} onClick={() => void openVersions()}>{t('common.version', '版本')}</Button></WorkflowPermission>
      {!readOnly && <>
        {showValidateButton ? <WorkflowPermission operation="Edit" instancePermissions={workflow.permission}><Button onClick={() => void validate()}>{t('workflowOrchestration.editor.validate', '校验')}</Button></WorkflowPermission> : null}
        <WorkflowPermission operation="Edit" instancePermissions={workflow.permission}><Button icon={<SaveOutlined />} loading={busy} onClick={() => void save()}>{t('workflowOrchestration.editor.saveDraft', '保存草稿')}</Button></WorkflowPermission>
        <WorkflowPermission operation="Publish" instancePermissions={workflow.permission}><Popconfirm title={t('workflowOrchestration.editor.publishConfirm', '发布为新的不可变版本？')} description={t('workflowOrchestration.editor.publishHint', '未保存的当前画布也会一并发布，但不会自动启用流程。')} onConfirm={() => void publish()}><Button type="primary" icon={<SendOutlined />} loading={busy}>{t('workflowOrchestration.editor.publish', '发布')}</Button></Popconfirm></WorkflowPermission>
      </>}
    </header>
    <div className="flex min-h-0 flex-1">
      <section className="relative min-w-0 flex-1 bg-[var(--color-fill-1)]">
        <WorkflowCanvasActionRail readOnly={readOnly} onOpenPicker={() => { setPendingSource(undefined); closeInspector(); setPickerOpen(true); }} />
        <ReactFlow className="h-[calc(100%-37px)]!" nodes={interactive} edges={interactiveEdges} nodeTypes={nodeTypes} edgeTypes={edgeTypes} connectionLineStyle={connectionLineStyle} fitView fitViewOptions={{ maxZoom: 1 }} proOptions={{ hideAttribution: true }} deleteKeyCode={null} nodesDraggable={!readOnly} nodesConnectable={!readOnly}
          onNodesChange={(changes) => { if (changes.some((item) => item.type === 'position')) setDirty(true); onNodesChange(changes); }}
          onEdgesChange={(changes) => { setDirty(true); onEdgesChange(changes); }}
          onConnect={(connection: Connection) => {
            if (!connection.source || !connection.target || connection.source === connection.target) return;
            if (edges.some((edge) => edge.source === connection.source && edge.target === connection.target)) { message.warning(t('workflowOrchestration.editor.pathExists', '这条路径已经存在')); return; }
            const topLevel = new Set(definition.tasks.map((task) => task.taskReferenceName));
            const triggerIds = new Set(workflowTriggerNodes(metadata).map((item) => item.id));
            const returnIds = new Set((metadata.return_nodes || []).map((item) => item.id));
            const supported = (triggerIds.has(connection.source) && topLevel.has(connection.target))
              || (topLevel.has(connection.source) && topLevel.has(connection.target))
              || (topLevel.has(connection.source) && returnIds.has(connection.target));
            if (!supported) { message.warning(t('workflowOrchestration.editor.unsupportedConnection', 'MVP 仅支持连接触发器、顶层节点和响应节点；嵌套路径由控制节点配置')); return; }
            setEdges((items) => [
              ...items.filter((edge) => !(connection.sourceHandle && edge.source === connection.source && edge.sourceHandle === connection.sourceHandle)),
              { id: `${connection.source}-${connection.target}-${Date.now()}`, source: connection.source!, target: connection.target!, sourceHandle: connection.sourceHandle, targetHandle: connection.targetHandle },
            ]);
            setDirty(true);
          }}
          onPaneClick={() => setSelectedId(undefined)}
          onNodeClick={(_, node) => setSelectedId(node.id)}
          onNodeDoubleClick={(_, node) => { setSelectedId(node.id); setInspectorOpen(true); }}>
          <Background variant={BackgroundVariant.Dots} gap={16} size={1} color="var(--color-border-3)" bgColor="var(--color-fill-1)" />
          <WorkflowCanvasControls onTidy={tidyCanvas} />
        </ReactFlow>
        {nodes.length === 0 && !readOnly && (
          <WorkflowPermission operation="Edit" instancePermissions={workflow.permission} className="contents">
            <WorkflowCanvasEmptyState
              onOpenPicker={() => { setPendingSource(undefined); closeInspector(); setPickerOpen(true); }}
            />
          </WorkflowPermission>
        )}
        {!readOnly && !pickerOpen && <WorkflowPermission operation="Execute" instancePermissions={workflow.permission}><Button
          className="absolute bottom-[53px] left-1/2 z-20 h-9! -translate-x-1/2 rounded-md! border-[var(--theme-color-status-warning)]! bg-[var(--theme-color-status-warning)]! text-white! shadow-md"
          icon={<PlayCircleOutlined />}
          onClick={openDebugDialog}
        >{t('workflowOrchestration.editor.debugWorkflow', '调试流程')}</Button></WorkflowPermission>}
        <div className="absolute inset-x-0 bottom-0 z-20 flex h-[37px] items-center justify-between border-t border-[var(--color-border-1)] bg-[var(--color-bg)] px-3 text-xs text-[var(--color-text-2)]">
          <span>{t('workflowOrchestration.editor.debugOutput', '调试输出')}</span>
          <WorkflowPermission operation="View" area="executions" instancePermissions={debugExecution?.permission}>
            <Button
              type="link"
              size="small"
              className="h-auto! p-0! text-xs!"
              disabled={!debugExecution}
              onClick={() => debugExecution && router.push(`/workflow-orchestration/executions/${debugExecution.id}`)}
            >
              {debugExecution ? t('common.viewDetails', '查看详情') : t('workflowOrchestration.editor.runToViewDetails', '运行后可查看执行详情')}
            </Button>
          </WorkflowPermission>
        </div>
        {issues.length > 0 && <Alert className="absolute bottom-[53px] left-1/2 z-10 w-[min(640px,calc(100%-32px))] -translate-x-1/2" type="error" showIcon closable message={t('workflowOrchestration.editor.pendingIssues', '流程存在待处理问题')} description={issues[0]} onClose={() => setIssues([])} />}

        <WorkflowNodePickerPanel firstNodeOnly={firstNodeOnly} open={pickerOpen} query={query} groups={pickerGroups} onQueryChange={setQuery} onClose={() => { setPendingSource(undefined); setPickerOpen(false); }} />
      </section>
      {selectedNode && <WorkflowNodeInspector
        open={inspectorOpen}
        title={selectedNode.data.title}
        meta={selectedNode.data.meta}
        references={inspectorReferences}
        readOnly={readOnly}
        parameterActions={!readOnly && selectedTask?.type === 'SIMPLE' && selectedAtom ? <AtomConfigTemplateActions
          atomKey={selectedAtom.key}
          parameters={selectedTask.inputParameters || {}}
          onLoad={changeTaskInputs}
        /> : undefined}
        outputSchema={selectedTrigger?.trigger_type === 'SCHEDULE' ? scheduleOutputSchema : selectedTrigger?.trigger_type === 'WEBHOOK' ? webhookInputSchema : selectedTrigger?.input_schema || selectedAtom?.output_schema}
        outputData={metadata.node_test_data?.[selectedNode.id]}
        outputBusy={selectedTrigger?.trigger_type === 'NATS' ? natsTestBusy : selectedTrigger?.trigger_type === 'WEBHOOK' ? webhookTestBusy : nodeTestBusy && nodeTestReference === selectedNode.id}
        outputError={selectedTrigger?.trigger_type === 'NATS' ? natsTestError : selectedTrigger?.trigger_type === 'WEBHOOK' ? webhookTestError : nodeTestReference === selectedNode.id ? nodeTestError : ''}
        onExecute={!readOnly && (selectedTrigger || selectedTask?.type === 'SIMPLE') ? () => action('test', selectedNode.id) : undefined}
        executeLabel={selectedTrigger?.trigger_type === 'NATS' ? t('workflowOrchestration.editor.listenForTestEvent', '监听测试事件') : selectedTrigger?.trigger_type === 'WEBHOOK' ? t('workflowOrchestration.editor.listenForWebhook', '监听测试请求') : undefined}
        onClose={closeInspector}
        hideUpstreamInput={Boolean(selectedTrigger)}
      >
        <div className="flex flex-col gap-5">
          {selectedTrigger && <Form className="flex flex-col gap-5" layout="vertical"><Form.Item className="mb-0" label={t('workflowOrchestration.editor.nodeName', '节点名称')}><Input disabled={readOnly} value={selectedTrigger.name} onChange={(event) => changeTrigger({ name: event.target.value })} /></Form.Item>
            {selectedTrigger.trigger_type === 'FORM' && <section className="flex flex-col gap-4"><Alert type="info" showIcon message={t('workflowOrchestration.editor.triggerInputHint', '{trigger} 定义本入口的运行输入', { trigger: triggerLabels[selectedTrigger.trigger_type] })} /><FormSchemaEditor context="form" readOnly={readOnly} value={selectedTrigger.input_schema} onChange={(inputSchema) => changeTrigger({ input_schema: inputSchema })} /></section>}
            {selectedTrigger.trigger_type === 'SCHEDULE' && <ScheduleTriggerEditor
              value={selectedTrigger.config}
              readOnly={readOnly}
              preview={schedulePreview}
              previewBusy={schedulePreviewBusy}
              previewError={schedulePreviewError}
              onChange={(config) => changeTrigger({ config, input_schema: scheduleOutputSchema })}
            />}
            {selectedTrigger.trigger_type === 'WEBHOOK' && <>
              <WebhookTriggerPanel
                workflowId={workflow.id || null}
                nodeKey={selectedTrigger.id}
                currentVersion={workflow.current_version}
                testSession={webhookTestSession}
                testBusy={webhookTestBusy}
                testError={webhookTestError}
                onCancelTest={cancelWebhookTest}
              />
              <Form.Item className="mb-0" label={t('workflowOrchestration.editor.responseMode', '响应模式')} tooltip={t('workflowOrchestration.editor.responseModeHint', '立即响应只确认已受理，流程继续异步执行；等待结果会保持请求，直到达 Webhook 响应节点。')}>
                <Select
                  disabled={readOnly}
                  value={String(selectedTrigger.config.response_mode || 'IMMEDIATE')}
                  options={[
                    { value: 'IMMEDIATE', label: t('workflowOrchestration.editor.immediateResponse', '立即响应（返回 execution_id）') },
                    { value: 'WAIT', label: t('workflowOrchestration.editor.waitWebhookReturn', '等待流程结果（同步）') },
                  ]}
                  onChange={(value) => changeTrigger({ config: { ...selectedTrigger.config, response_mode: value }, input_schema: webhookInputSchema })}
                />
              </Form.Item>
            </>}
            {selectedTrigger.trigger_type === 'NATS' && natsTestSession ? <section aria-label={t('workflowOrchestration.editor.natsTestSession', 'NATS 测试监听')} className="rounded-lg border border-[var(--color-border-1)] bg-[var(--color-fill-1)] p-4">
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2"><Tag color={natsTestBusy ? 'processing' : natsTestError ? 'error' : 'success'}>{natsTestBusy ? t('workflowOrchestration.editor.waitingForEvent', '等待事件') : natsTestError ? t('workflowOrchestration.editor.listenFailed', '监听失败') : t('workflowOrchestration.editor.eventCaptured', '已捕获事件')}</Tag><span className="text-xs text-[var(--color-text-3)]">{t('workflowOrchestration.editor.testSubjectExpires', '{seconds} 秒内有效', { seconds: natsTestSession.timeout_seconds })}</span></div>
                <Space size={4}>
                  <WorkflowPermission operation="View"><Button size="small" icon={<CopyOutlined />} onClick={() => void navigator.clipboard.writeText(natsTestSession.subject).then(() => message.success(t('workflowOrchestration.editor.subjectCopied', '测试主题已复制')))}>{t('common.copy', '复制')}</Button></WorkflowPermission>
                  {natsTestBusy ? <WorkflowPermission operation="Execute"><Button size="small" danger onClick={cancelNatsTest}>{t('workflowOrchestration.editor.cancelListening', '取消监听')}</Button></WorkflowPermission> : null}
                </Space>
              </div>
              <div className="mt-3 text-xs text-[var(--color-text-3)]">{t('workflowOrchestration.editor.publishTestEventHint', '向以下临时主题发送一条标准事件，捕获后 payload 会显示在右侧。')}</div>
              <code className="mt-2 block break-all rounded-md bg-[var(--color-bg)] px-3 py-2 text-xs text-[var(--color-text-2)]">{natsTestSession.subject}</code>
            </section> : null}
          </Form>}
          {selectedTask && <section className="flex flex-col gap-5">{!isOpsPilotStyleAtom ? <Descriptions size="small" column={1} items={[
            { key: 'reference', label: t('workflowOrchestration.editor.nodeReference', '节点引用'), children: selectedTask.taskReferenceName },
            { key: 'type', label: t('workflowOrchestration.atom.nodeTypeLabel', '节点类型'), children: selectedTask.type },
            ...(selectedAtom?.default_timeout_seconds ? [{ key: 'timeout', label: t('workflowOrchestration.editor.effectiveTimeout', '生效超时'), children: t('workflowOrchestration.editor.effectiveTimeoutValue', '{seconds} 秒（由原子契约固定）', { seconds: selectedAtom.default_timeout_seconds }) }] : []),
            ...(selectedAtom?.retry_count !== undefined ? [{ key: 'retry', label: t('workflowOrchestration.editor.effectiveRetry', '失败重试'), children: selectedAtom.retry_count ? t('workflowOrchestration.editor.effectiveRetryValue', '{count} 次，间隔 {seconds} 秒', { count: selectedAtom.retry_count, seconds: selectedAtom.retry_delay_seconds || 0 }) : t('workflowOrchestration.editor.noAutomaticRetry', '不自动重试') }] : []),
          ]} /> : null}
            {selectedTask.type === 'SIMPLE' && (selectedTask.name === 'bklite_document_render'
              ? <DocumentRenderForm
                schema={selectedAtom?.input_schema}
                value={selectedTask.inputParameters || {}}
                references={references}
                nodeTitle={selectedNode?.data.title || selectedAtom?.name || selectedTask.name}
                readOnly={readOnly}
                workflowId={workflow.id || null}
                onChange={changeTaskInputs}
                onNodeTitleChange={changeTaskTitle}
              />
              : selectedTask.name === 'bklite_job_execute'
                ? <JobExecuteForm
                  key={selectedTask.taskReferenceName}
                  schema={selectedAtom?.input_schema}
                  value={selectedTask.inputParameters || {}}
                  references={references}
                  readOnly={readOnly}
                  targetRecords={jobTargetRecords}
                  fieldActions={readOnly ? {} : {
                    targets: <Button onClick={() => {
                      setJobTargetSelectorPurpose('params');
                      setJobTargetSelectorOpen(true);
                    }}>{t('workflowOrchestration.editor.selectJobPlatformHosts', '选择作业平台主机')}</Button>,
                  }}
                  onChange={changeTaskInputs}
                />
                : OPSPILOT_ATOM_KEYS.has(selectedTask.name)
                  ? <OpsPilotAtomForm
                    atomKey={selectedTask.name}
                    schema={selectedAtom?.input_schema}
                    value={selectedTask.inputParameters || {}}
                    references={references}
                    workflowId={workflow.id || null}
                    nodeTitle={selectedNode?.data.title || selectedAtom?.name || selectedTask.name}
                    readOnly={readOnly}
                    onChange={changeTaskInputs}
                    onNodeTitleChange={changeTaskTitle}
                  />
                  : <SchemaNodeForm
                    schema={selectedAtom?.input_schema}
                    uiSchema={selectedAtom?.ui_schema}
                    value={selectedTask.inputParameters || {}}
                    references={references}
                    onChange={changeTaskInputs}
                  />)}
            {selectedCondition && <ConditionEditor
              value={selectedCondition}
              references={references}
              readOnly={readOnly}
              nodeTitle={selectedNode?.data.title || t('workflowOrchestration.editor.conditionBranch', '条件分支')}
              onChange={changeCondition}
              onNodeTitleChange={changeTaskTitle}
            />}
            {selectedTask.type === 'HUMAN' && <Form className="flex flex-col gap-5" layout="vertical">
              <Form.Item className="mb-0" label={t('workflowOrchestration.editor.nodeName', '节点名称')} required>
                <Input
                  disabled={readOnly}
                  value={selectedNode?.data.title || t('workflowOrchestration.editor.humanApproval', '人工审批')}
                  placeholder={t('workflowOrchestration.editor.enterNodeName', '请输入节点名称')}
                  onChange={(event) => changeTaskTitle(event.target.value)}
                />
              </Form.Item>
              <Form.Item className="mb-0" label={t('workflowOrchestration.editor.approvalTitle', '审批标题')} required>
                <Input disabled={readOnly} value={String(selectedTask.inputParameters?.title || '')} onChange={(event) => changeApproval({ title: event.target.value })} />
              </Form.Item>
              <Form.Item className="mb-0" label={t('workflowOrchestration.approval.candidates', '候选审批人')}>
                <Select mode="tags" disabled={readOnly} value={(selectedTask.inputParameters?.candidates || []) as string[]} onChange={(candidates) => changeApproval({ candidates })} />
              </Form.Item>
            </Form>}
          </section>}
          {selectedReturn && <Form className="flex flex-col gap-5" layout="vertical"><Form.Item className="mb-0" label={t('workflowOrchestration.editor.nodeName', '节点名称')}><Input disabled={readOnly} value={selectedReturn.name} onChange={(event) => changeReturn({ name: event.target.value })} /></Form.Item><Form.Item className="mb-0" label={t('workflowOrchestration.editor.returnReference', '返回数据引用')} tooltip={t('workflowOrchestration.editor.returnReferenceHint', '从可用节点输出中选择，不支持自由表达式')}><Select showSearch optionFilterProp="label" disabled={readOnly} value={String(selectedReturn.config.body || '') || undefined} placeholder={t('workflowOrchestration.editor.selectNodeOutput', '选择节点输出')} options={returnReferences.map((item) => ({ value: item.value, label: item.label }))} onChange={(body) => changeReturn({ config: { ...selectedReturn.config, body } })} /></Form.Item></Form>}
        </div>
      </WorkflowNodeInspector>}
    </div>

    <OperateModal
      title={t('workflowOrchestration.editor.testCurrentNode', '测试当前节点')}
      open={nodeTestOpen}
      zIndex={WORKFLOW_OVERLAY_MODAL_Z_INDEX}
      confirmLoading={nodeTestBusy}
      okText={t('workflowOrchestration.editor.executeNode', '执行节点')}
      okButtonProps={{ disabled: selectedTrigger?.trigger_type === 'FORM' ? false : !inspectorTestTrigger }}
      onOk={() => selectedTrigger?.trigger_type === 'FORM' && nodeTestReference === selectedTrigger.id
        ? runFormTriggerTest(selectedTrigger)
        : selectedTask?.name === 'bklite_document_render'
          ? runDocumentNodeTest()
          : runConfiguredNodeTest()}
      onCancel={() => { if (!nodeTestBusy) setNodeTestOpen(false); }}
    >
      {selectedTrigger?.trigger_type === 'FORM' && nodeTestReference === selectedTrigger.id && workflow.id ? <WorkflowTriggerRuntimeForm workflowId={workflow.id} schema={selectedTrigger.input_schema} value={nodeTestInputs} onChange={setNodeTestInputs} /> : selectedTask?.name === 'bklite_document_render' ? <div className="flex flex-col gap-4">
        <Form className="flex flex-col gap-5" layout="vertical">
          <Form.Item
            className="mb-0"
            label={t('workflowOrchestration.editor.documentTemplate', '报告模板')}
            required
          >
            <div className="flex flex-col gap-2">
              {documentTestTemplate ? <div className="flex items-start gap-3 rounded-md border border-[var(--color-border-1)] bg-[var(--color-fill-1)] px-3 py-2">
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium text-[var(--color-text-1)]" title={documentTestTemplate.echo.name}>{documentTestTemplate.echo.name}</div>
                  <Typography.Text className="text-xs" type="secondary">
                    {[
                      documentTestTemplate.echo.format ? documentTestTemplate.echo.format.toUpperCase() : '',
                      documentTestTemplate.snapshot ? t('workflowOrchestration.editor.publishedTemplateSnapshot', '已发布固化') : '',
                    ].filter(Boolean).join(' · ')}
                  </Typography.Text>
                  {documentTestTemplate.echo.placeholders.length ? <Typography.Text className="mt-1 block text-xs" type="secondary">
                    {t('workflowOrchestration.editor.detectedPlaceholders', '识别到的占位符')}：{documentTestTemplate.echo.placeholders.join('、')}
                  </Typography.Text> : null}
                </div>
                <Button
                  type="text"
                  size="small"
                  aria-label={t('workflowOrchestration.editor.removeTestTemplate', '移除测试模板')}
                  icon={<CloseOutlined />}
                  onClick={() => setDocumentTestTemplate(undefined)}
                />
              </div> : <Upload
                accept=".docx,.xlsx"
                maxCount={1}
                showUploadList={false}
                beforeUpload={(file) => {
                  void uploadDocumentTestTemplate(file);
                  return Upload.LIST_IGNORE;
                }}
              >
                <Button loading={documentTemplateUploading} icon={<UploadOutlined />}>
                  {t('workflowOrchestration.editor.uploadTestTemplate', '上传测试模板')}
                </Button>
              </Upload>}
              <FileSampleLinks schema={{
                'x-file-options': {
                  accept: ['docx', 'xlsx'],
                  maxSizeMiB: 5,
                  maxCount: 1,
                  sourceModes: ['upload'],
                  sampleFiles: [
                    { name: 'Word', url: '/workflow-orchestration/templates/health-inspection-example.docx' },
                    { name: 'Excel', url: '/workflow-orchestration/templates/health-inspection-example.xlsx' },
                  ],
                },
              }} />
            </div>
          </Form.Item>
          <Form.Item
            className="mb-0"
            label={t('workflowOrchestration.editor.testDocumentData', '测试文档数据')}
            required
          >
            <SchemaNodeField
              schema={{
                ...(selectedAtom?.input_schema?.properties?.data || { type: 'object', title: t('workflowOrchestration.editor.documentData', '文档数据') }),
                'x-widget': 'json',
                'x-rows': 12,
                jsonEditorAllowed: true,
              }}
              value={documentTestData}
              references={references}
              onChange={setDocumentTestData}
            />
          </Form.Item>
        </Form>
      </div> : <>
      <Alert
        className="mb-4"
        type={selectedAtom?.safety_level === 'READ_ONLY' ? 'info' : 'warning'}
        showIcon
        message={selectedAtom?.safety_level === 'READ_ONLY'
          ? t('workflowOrchestration.editor.nodeTestInputHint', '这些数据作为本次节点测试的触发输入，执行结果会回填到右侧输出区。')
          : t('workflowOrchestration.editor.realExecutionWarning', '该节点会调用真实平台能力，可能对目标系统产生变更。请确认测试数据和节点参数。')}
      />
      {inspectorTriggers.length > 1 ? <Form layout="vertical">
        <Form.Item className="mb-4" label={t('workflowOrchestration.editor.debugEntry', '调试入口')} required>
          <Select
            value={inspectorTestTrigger?.id}
            options={inspectorTriggers.map((item) => ({ value: item.id, label: `${item.name} · ${item.trigger_type}` }))}
            onChange={(id) => {
              const trigger = inspectorTriggers.find((item) => item.id === id);
              setNodeTestTriggerId(id);
              const cached = inspectorTestData[id];
              const contract = buildNodeTestInputContract(selectedTask, selectedAtom?.input_schema, trigger?.input_schema);
              setNodeTestInputs({
                ...defaultTriggerRuntimeInputs(contract.schema),
                ...(cached && typeof cached === 'object' && !Array.isArray(cached) ? cached as Record<string, unknown> : {}),
              });
            }}
          />
        </Form.Item>
      </Form> : null}
      {inspectorTestTrigger
        ? Object.keys(nodeTestInputContract.schema.properties || {}).length
          ? selectedTask?.name === 'bklite_job_execute' && jobTestTargetsField
            ? <Form layout="vertical" className="flex flex-col gap-4">
              <Form.Item className="mb-0" label={t('workflowOrchestration.editor.targetHosts', '目标主机')} required>
                <button
                  type="button"
                  className="flex w-full items-center justify-between gap-4 rounded-lg border border-[var(--color-border-1)] px-4 py-3 text-left transition-colors hover:border-[var(--color-primary)] focus-visible:outline-2 focus-visible:outline-[var(--color-primary)]"
                  onClick={() => {
                    setJobTargetSelectorPurpose('test');
                    setJobTargetSelectorOpen(true);
                  }}
                >
                  <span>
                    <span className="block text-sm font-medium text-[var(--color-text-1)]">
                      {Array.isArray(nodeTestInputs[jobTestTargetsField]) && (nodeTestInputs[jobTestTargetsField] as unknown[]).length
                        ? t('workflowOrchestration.launch.hostsSelected', '已选择 {count} 台主机', { count: (nodeTestInputs[jobTestTargetsField] as unknown[]).length })
                        : t('workflowOrchestration.launch.selectHosts', '请选择目标主机')}
                    </span>
                    <span className="mt-1 block text-xs text-[var(--color-text-3)]">
                      {t('workflowOrchestration.launch.selectorHint', '点击打开主机选择器，确认后回填本执行表单')}
                    </span>
                  </span>
                  <span className="shrink-0 text-sm text-[var(--color-primary)]">
                    {t('workflowOrchestration.editor.selectJobPlatformHosts', '选择作业平台主机')}
                  </span>
                </button>
              </Form.Item>
              {Object.keys(nodeTestInputContract.schema.properties || {}).filter((key) => key !== jobTestTargetsField).length && workflow.id
                ? <WorkflowTriggerRuntimeForm
                  workflowId={workflow.id}
                  schema={{
                    ...nodeTestInputContract.schema,
                    properties: Object.fromEntries(Object.entries(nodeTestInputContract.schema.properties || {}).filter(([key]) => key !== jobTestTargetsField)),
                    required: (nodeTestInputContract.schema.required || []).filter((key) => key !== jobTestTargetsField),
                  }}
                  value={nodeTestInputs}
                  onChange={setNodeTestInputs}
                />
                : null}
            </Form>
            : workflow.id ? <WorkflowTriggerRuntimeForm workflowId={workflow.id} schema={nodeTestInputContract.schema} value={nodeTestInputs} onChange={setNodeTestInputs} /> : null
          : <Empty description={t('workflowOrchestration.editor.noAdditionalNodeTestInput', '当前节点无需额外测试输入')} />
        : <Empty description={t('workflowOrchestration.editor.noTriggers', '当前流程没有触发器')} />}
      </>}
    </OperateModal>
    <JobTargetSelectionDialog
      open={jobTargetSelectorOpen}
      value={jobTargetSelectorPurpose === 'test' && jobTestTargetsField
        ? (Array.isArray(nodeTestInputs[jobTestTargetsField]) ? (nodeTestInputs[jobTestTargetsField] as unknown[]).map(String) : EMPTY_TARGET_REFERENCES)
        : (Array.isArray(selectedTask?.inputParameters?.targets) ? selectedTask.inputParameters.targets as string[] : EMPTY_TARGET_REFERENCES)}
      maxCount={selectedAtom?.input_schema?.properties?.targets?.maxItems}
      onCancel={() => setJobTargetSelectorOpen(false)}
      onConfirm={(targets, records) => {
        setJobTargetRecords((current) => ({
          ...current,
          ...Object.fromEntries(records.map((item) => [item.id, item])),
        }));
        if (jobTargetSelectorPurpose === 'test' && jobTestTargetsField) {
          setNodeTestInputs({ ...nodeTestInputs, [jobTestTargetsField]: targets });
        } else if (selectedTask) {
          changeTaskInputs({ ...(selectedTask.inputParameters || {}), targets });
        }
        setJobTargetSelectorOpen(false);
      }}
    />
    <OperateModal
      title={t('workflowOrchestration.editor.debugCurrentDraft', '调试当前草稿')}
      open={debugOpen}
      zIndex={WORKFLOW_OVERLAY_MODAL_Z_INDEX}
      okText={t('workflowOrchestration.editor.startDebug', '开始调试')}
      okButtonProps={{ disabled: !debugTrigger }}
      onOk={() => void debug()}
      onCancel={() => setDebugOpen(false)}
    >
      <Alert className="mb-4" type="info" showIcon message={t('workflowOrchestration.editor.debugSnapshotHint', '调试使用当前未保存快照，会生成 DEBUG 执行记录')} />
      {debugTriggers.length > 1 ? <Form layout="vertical"><Form.Item label={t('workflowOrchestration.editor.debugEntry', '调试入口')} required><Select value={debugTrigger?.id} options={debugTriggers.map((item) => ({ value: item.id, label: `${item.name} · ${item.trigger_type}` }))} onChange={(id) => {
        const trigger = debugTriggers.find((item) => item.id === id);
        setDebugTriggerId(id);
        setDebugInputs(trigger ? defaultTriggerRuntimeInputs(trigger.input_schema) : {});
      }} /></Form.Item></Form> : null}
      {debugTrigger && workflow.id ? <WorkflowTriggerRuntimeForm workflowId={workflow.id} schema={debugTrigger.input_schema} value={debugInputs} onChange={setDebugInputs} /> : <Empty description={t('workflowOrchestration.editor.noTriggers', '当前流程没有触发器')} />}
    </OperateModal>
    <Drawer
      title={t('workflowOrchestration.editor.versionRecordsPlain', '流程版本记录')}
      width={660}
      open={versionsOpen}
      onClose={() => { versionsRequestCoordinator.invalidate(); setVersionsOpen(false); }}
    >
      <Spin spinning={versionsLoading}>
        {versions.length ? (
          <Timeline
            className="mt-1 px-1"
            items={versions.map((item) => {
              const isCurrent = item.version === workflow.current_version;
              return {
                key: String(item.id),
                color: isCurrent ? 'blue' : 'gray',
                children: (
                  <div className="flex items-start justify-between gap-4 pb-1">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-medium text-[var(--color-text-1)]">v{item.version}</span>
                        {isCurrent ? <Tag className="!m-0" color="blue">{t('workflowOrchestration.editor.currentPublishedVersion', '当前发布版本')}</Tag> : null}
                      </div>
                      <div className="mt-1 text-xs text-[var(--color-text-3)]">
                        {item.created_by || '--'}
                        {' · '}
                        {item.created_at ? convertToLocalizedTime(item.created_at) : '--'}
                        {' · '}
                        {t('workflowOrchestration.editor.executionCount', '{count} 次执行', { count: item.execution_count ?? '--' })}
                      </div>
                    </div>
                    {!readOnly ? (
                      <WorkflowPermission operation="Edit" instancePermissions={workflow.permission}>
                        <Popconfirm
                          title={t('workflowOrchestration.editor.restoreConfirm', '基于 v{version} 覆盖当前草稿？', { version: item.version })}
                          description={t('workflowOrchestration.editor.restoreHint', '当前发布版本和历史执行不受影响。')}
                          onConfirm={() => void restoreVersion(item.version)}
                        >
                          <Button type="link" size="small" className="h-auto shrink-0 px-0">
                            {t('workflowOrchestration.editor.createDraftFromVersion', '恢复草稿')}
                          </Button>
                        </Popconfirm>
                      </WorkflowPermission>
                    ) : null}
                  </div>
                ),
              };
            })}
          />
        ) : (
          <Empty description={t('workflowOrchestration.editor.noPublishedVersions', '尚未发布版本')} />
        )}
      </Spin>
    </Drawer>
  </main>;
}
