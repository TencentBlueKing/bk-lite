'use client';

import { ReloadOutlined, SearchOutlined, UploadOutlined } from '@ant-design/icons';
import { Alert, App, Button, Empty, Form, Input, InputNumber, Popconfirm, Select, Spin, Switch, Tabs, Tag, Upload } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useCallback, useEffect, useMemo, useState } from 'react';
import type { Key } from 'react';

import DualSelector from '@/components/dual-selector';
import OperateModal from '@/components/operate-modal';
import { useTranslation } from '@/utils/i18n';
import useApiClient, { HandledRequestError } from '@/utils/request';
import type {
  ExecutionRecord,
  JsonSchema,
  NodeTarget,
  TargetListResponse,
  TargetSource,
  WorkflowLaunchPlan,
  WorkflowTargetField,
} from '../lib/types';
import { useAutoRequest, useRequestCoordinator } from '../lib/use-request-coordinator';
import { FileSampleLinks } from './file-sample-links';
import { WorkflowPermission } from './workflow-permission';

const API = '/workflow_orchestration/api';

/** Nested above node inspector / launch dialogs so selectors stay on top. */
export const WORKFLOW_OVERLAY_MODAL_Z_INDEX = 1100;
export const WORKFLOW_NESTED_SELECTOR_Z_INDEX = 1200;

function defaultInputs(schema: JsonSchema): Record<string, unknown> {
  return Object.fromEntries(Object.entries(schema.properties || {}).flatMap(([key, field]) => {
    if ('default' in field) return [[key, field.default]];
    if (field.type === 'boolean') return [[key, false]];
    if (field.type === 'array') return [[key, []]];
    return [];
  }));
}

function RuntimeInputField({ schema, value, onChange }: { schema: JsonSchema; value: unknown; onChange: (value: unknown) => void }) {
  const { t } = useTranslation();
  if (schema.enum) return <Select className="w-full" allowClear value={value as string | number | undefined} options={schema.enum.map((item) => ({ value: item as string | number, label: String(item) }))} onChange={onChange} />;
  if (schema.type === 'boolean') return <Switch checked={Boolean(value)} onChange={onChange} />;
  if (schema.type === 'integer' || schema.type === 'number') return <InputNumber className="w-full" min={schema.minimum} max={schema.maximum} value={typeof value === 'number' ? value : undefined} onChange={onChange} />;
  if (schema.type === 'array' && schema.items && !['object', 'array'].includes(String(schema.items.type))) {
    return <Select mode="tags" className="w-full" value={Array.isArray(value) ? value.map(String) : []} placeholder={t('workflowOrchestration.launch.enterAndPressReturn', '输入后按回车添加')} onChange={onChange} />;
  }
  if (schema.type === 'object' && schema.properties) {
    const current = value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
    return <div className="space-y-3 rounded-md border border-[var(--color-border-1)] p-3">{Object.entries(schema.properties).map(([key, child]) => <div key={key}><div className="mb-1.5 text-xs text-[var(--color-text-3)]">{child.title || key}</div><RuntimeInputField schema={child} value={current[key]} onChange={(next) => onChange({ ...current, [key]: next })} /></div>)}</div>;
  }
  return <Input value={String(value ?? '')} placeholder={schema.description} onChange={(event) => onChange(event.target.value)} />;
}

function RuntimeFileUpload({ workflowId, fieldKey, launchToken, schema, value, onChange }: { workflowId: number; fieldKey: string; launchToken: string; schema: JsonSchema; value: unknown; onChange: (value: unknown) => void }) {
  const { post } = useApiClient();
  const { message } = App.useApp();
  const { t } = useTranslation();
  const current = value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
  const fileOptions = schema['x-file-options'];
  const acceptedFormats = fileOptions?.accept?.length ? fileOptions.accept : ['docx', 'xlsx'];
  const maxSizeMiB = fileOptions?.maxSizeMiB || 5;
  const [uploading, setUploading] = useState(false);
  return <div className="space-y-3 rounded-lg border border-[var(--color-border-1)] p-4">
    <Upload accept={acceptedFormats.map((item) => `.${item}`).join(',')} maxCount={fileOptions?.maxCount || 1} showUploadList={false} beforeUpload={async (file) => {
      if (file.size > maxSizeMiB * 1024 * 1024) { message.error(t('workflowOrchestration.launch.templateTooLarge', '文件不能超过 {size} MiB', { size: maxSizeMiB })); return Upload.LIST_IGNORE; }
      setUploading(true);
      try {
        const body = new FormData(); body.append('launch_token', launchToken); body.append('field_key', fieldKey); body.append('file', file);
        const uploaded = await post<Record<string, unknown>>(`${API}/workflows/${workflowId}/report-template-upload/`, body, { headers: { 'Content-Type': 'multipart/form-data' } });
        onChange(uploaded); message.success(t('workflowOrchestration.launch.templateUploaded', '报告模板已上传'));
      } finally { setUploading(false); }
      return Upload.LIST_IGNORE;
    }}><Button loading={uploading} icon={<UploadOutlined />}>{current.name ? t('workflowOrchestration.launch.replaceTemplate', '更换模板') : t('workflowOrchestration.launch.chooseTemplate', '选择 Word / Excel 模板')}</Button></Upload>
    {current.name ? <div className="text-xs text-[var(--color-text-3)]">{String(current.name)} · {Math.ceil(Number(current.size || 0) / 1024)} KiB</div> : null}
    <FileSampleLinks schema={schema} />
    <div className="text-xs leading-5 text-[var(--color-text-3)]">{t('workflowOrchestration.launch.templateHint', '支持 {formats}，单文件不超过 {size} MiB。', { formats: acceptedFormats.map((item) => `.${item}`).join(' / '), size: maxSizeMiB })}</div>
  </div>;
}

function idBelongsToSource(id: string, source: TargetSource) {
  return source === 'node_mgmt' ? id.startsWith('node:') : id.startsWith('manual:');
}

function preferredSource(value: string[], allowed: TargetSource[]): TargetSource {
  for (const id of value) {
    if (id.startsWith('node:') && allowed.includes('node_mgmt')) return 'node_mgmt';
    if (id.startsWith('manual:') && allowed.includes('job_mgmt')) return 'job_mgmt';
  }
  return allowed[0];
}

interface TargetSelectorProps {
  field: WorkflowTargetField;
  value: string[];
  onChange: (value: string[]) => void;
  onBlockingChange: (blocked: boolean) => void;
  recordCache: Record<string, NodeTarget>;
  onRecordsDiscovered: (records: NodeTarget[]) => void;
}

export function RuntimeTargetSelector({ field, value, onChange, onBlockingChange, recordCache, onRecordsDiscovered }: TargetSelectorProps) {
  const { get } = useApiClient();
  const { message } = App.useApp();
  const { t } = useTranslation();
  const sourceLabel: Record<TargetSource, string> = {
    node_mgmt: t('workflowOrchestration.launch.nodeManagement', '节点管理'),
    job_mgmt: t('workflowOrchestration.launch.jobPlatform', '作业平台'),
  };
  const [activeSource, setActiveSource] = useState<TargetSource>(() => preferredSource(value, field.allowed_sources));
  const [records, setRecords] = useState<Partial<Record<TargetSource, NodeTarget[]>>>({});
  const [counts, setCounts] = useState<Partial<Record<TargetSource, number>>>({});
  const [errors, setErrors] = useState<Partial<Record<TargetSource, string>>>({});
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [queryDraft, setQueryDraft] = useState('');
  const [query, setQuery] = useState('');
  const requestCoordinator = useRequestCoordinator(setLoading);

  const load = useCallback(async (source: TargetSource, nextPage = page) => {
    const ticket = requestCoordinator.begin({ visible: true });
    if (!ticket) return;
    try {
      const params = new URLSearchParams({ source, page: String(nextPage), page_size: '10' });
      if (query.trim()) params.set('query', query.trim());
      const response = await get<TargetListResponse>(`${API}/workflows/targets/?${params.toString()}`, { signal: ticket.signal });
      if (!requestCoordinator.shouldApply(ticket)) return;
      setRecords((current) => ({ ...current, [source]: response.items || [] }));
      setCounts((current) => ({ ...current, [source]: response.count || 0 }));
      setErrors((current) => ({ ...current, [source]: undefined }));
      onRecordsDiscovered(response.items || []);
    } catch (error) {
      if (!requestCoordinator.shouldApply(ticket)) return;
      setErrors((current) => ({
        ...current,
        [source]: error instanceof Error
          ? error.message
          : t('workflowOrchestration.launch.sourceUnavailable', '{source}暂时不可用', { source: sourceLabel[source] }),
      }));
    } finally {
      requestCoordinator.finish(ticket);
    }
  }, [get, onRecordsDiscovered, page, query, requestCoordinator, t]);

  const allowedSourcesKey = field.allowed_sources.join(',');
  useEffect(() => {
    const nextSource = preferredSource(value, field.allowed_sources);
    setPage(1);
    setQueryDraft('');
    setQuery('');
    setActiveSource(nextSource);
    const exclusive = value.filter((id) => idBelongsToSource(id, nextSource));
    if (exclusive.length !== value.length) onChange(exclusive);
    // Only re-normalize when the field's allowed sources change (dialog remount covers reopen).
  }, [allowedSourcesKey]);

  useAutoRequest(`${activeSource}:${page}:${query}`, () => load(activeSource, page));

  const selectedItems = useMemo(
    () => value.map((id) => recordCache[id]).filter(Boolean),
    [recordCache, value],
  );

  useEffect(() => {
    const selectedUnavailable = Boolean(errors[activeSource]) && value.some((item) => idBelongsToSource(item, activeSource));
    const unsupportedOperatingSystem = selectedItems.some((target) => (
      Boolean(field.allowed_operating_systems?.length && !field.allowed_operating_systems.includes(target.operating_system))
    ));
    onBlockingChange(selectedUnavailable || unsupportedOperatingSystem);
  }, [activeSource, errors, field.allowed_operating_systems, onBlockingChange, selectedItems, value]);

  const changeSelection = (keys: Key[]) => {
    const next = keys.map(String).filter((id) => idBelongsToSource(id, activeSource));
    if (next.length > field.max_count) {
      message.warning(t('workflowOrchestration.launch.maxHosts', '最多选择 {count} 台主机', { count: field.max_count }));
      return;
    }
    onChange(next);
  };

  const switchSource = (source: TargetSource) => {
    if (source === activeSource) return;
    onChange([]);
    setPage(1);
    setQueryDraft('');
    setQuery('');
    setActiveSource(source);
  };

  const columns: ColumnsType<NodeTarget> = [
    { title: t('workflowOrchestration.launch.hostName', '主机名'), dataIndex: 'name', render: (name: string) => <span className="font-medium text-[var(--color-text-1)]">{name || t('workflowOrchestration.launch.unnamedHost', '未命名主机')}</span> },
    { title: 'IP', dataIndex: 'ip', width: 160, render: (ip: string) => <span className="font-mono text-xs text-[var(--color-text-2)]">{ip || '--'}</span> },
    { title: t('workflowOrchestration.launch.system', '系统'), dataIndex: 'operating_system', width: 100, render: (text: string) => text || '--' },
  ];
  const activeRecords = records[activeSource] || [];

  return <div className="space-y-5">
    <div>
      <div className="font-medium text-[var(--color-text-1)]">{field.name}</div>
      <div className="mt-1 text-xs leading-5 text-[var(--color-text-3)]">
        {t('workflowOrchestration.launch.selectRangeExclusive', '可选 {min}–{max} 台；节点管理与作业平台不能混选，切换来源会清空已选', {
          min: field.min_count,
          max: field.max_count,
        })}
      </div>
    </div>
    {selectedItems.some((item) => item.connected === false) && <Alert
      type="warning"
      showIcon
      message={t('workflowOrchestration.launch.offlineSelected', '已选项中包含离线主机')}
      description={t('workflowOrchestration.launch.offlineSelectedHint', '离线属于连接状态告警，启动前会再次校验并要求确认。')}
    />}
    <DualSelector<NodeTarget>
      rowKey="id"
      dataSource={errors[activeSource] ? [] : activeRecords}
      loading={loading}
      columns={columns}
      selectedKeys={value}
      onChange={changeSelection}
      getCheckboxProps={(target) => ({ disabled: Boolean(field.allowed_operating_systems?.length && !field.allowed_operating_systems.includes(target.operating_system)) })}
      selectedRecordsData={selectedItems}
      pagination={{ current: page, pageSize: 10, total: counts[activeSource] || 0, showSizeChanger: false }}
      onPageChange={(nextPage) => setPage(nextPage)}
      rightTitle={t('workflowOrchestration.launch.selectedHosts', '已选 {count} 台', { count: value.length })}
      clearAllText={t('workflowOrchestration.launch.clearAll', '全部清除')}
      emptySelectionText={t('workflowOrchestration.launch.noTargetsSelected', '暂未选择主机')}
      selectedPreviewLabel={t('workflowOrchestration.launch.selectedPreview', '已选项预览')}
      getRemoveLabel={(target) => t('workflowOrchestration.launch.removeTarget', '移除 {name}', { name: target.name || target.ip })}
      renderSelectedItem={(target) => <div className="truncate font-medium text-[var(--color-text-1)]">{target.name || t('workflowOrchestration.launch.unnamedHost', '未命名主机')}</div>}
      leftTitle={<div className="mb-4 space-y-3">
        <Tabs
          className="mb-0"
          activeKey={activeSource}
          onChange={(source) => switchSource(source as TargetSource)}
          items={field.allowed_sources.map((source) => ({
            key: source,
            label: `${sourceLabel[source]}${source === activeSource && value.length ? ` (${value.length})` : ''}`,
          }))}
        />
        <div className="flex gap-2">
          <Input.Search
            allowClear
            value={queryDraft}
            placeholder={t('workflowOrchestration.launch.searchHost', '搜索主机名或 IP')}
            enterButton={<SearchOutlined />}
            onChange={(event) => {
              const next = event.target.value;
              setQueryDraft(next);
              if (!next) {
                setPage(1);
                setQuery('');
              }
            }}
            onSearch={(next) => {
              setPage(1);
              setQuery(next.trim());
            }}
          />
          <WorkflowPermission operation="Execute">
            <Button
              aria-label={t('workflowOrchestration.launch.refreshSource', '刷新{source}目标', { source: sourceLabel[activeSource] })}
              icon={<ReloadOutlined aria-hidden="true" />}
              onClick={() => void load(activeSource, page)}
            />
          </WorkflowPermission>
        </div>
        {errors[activeSource] ? <Alert
          type="error"
          showIcon
          message={t('workflowOrchestration.launch.sourceLoadFailed', '{source}加载失败', { source: sourceLabel[activeSource] })}
          description={errors[activeSource]}
          action={<WorkflowPermission operation="Execute"><Button size="small" onClick={() => void load(activeSource, page)}>{t('common.retry', '重试')}</Button></WorkflowPermission>}
        /> : null}
      </div>}
      height="min(520px, calc(100vh - 330px))"
    />
  </div>;
}

interface Props {
  open: boolean;
  title: string;
  planUrl: string;
  submitUrl: string;
  initialPlan?: WorkflowLaunchPlan;
  onClose: () => void;
  onStarted: (execution: ExecutionRecord) => void;
  onSubmittingChange?: (submitting: boolean) => void;
  instancePermissions?: string[];
}

export function WorkflowLaunchDialog({ open, title, planUrl, submitUrl, initialPlan, onClose, onStarted, onSubmittingChange, instancePermissions }: Props) {
  const { get, post } = useApiClient();
  const { message } = App.useApp();
  const { t } = useTranslation();
  const [plan, setPlan] = useState<WorkflowLaunchPlan>();
  const [inputs, setInputs] = useState<Record<string, unknown>>({});
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [offlineTargets, setOfflineTargets] = useState<NodeTarget[]>([]);
  const [targetBlocking, setTargetBlocking] = useState<Record<string, boolean>>({});
  const [targetDialogField, setTargetDialogField] = useState<WorkflowTargetField>();
  const [targetDraft, setTargetDraft] = useState<string[]>([]);
  const [targetDraftBlocked, setTargetDraftBlocked] = useState(false);
  const [targetRecords, setTargetRecords] = useState<Record<string, NodeTarget>>({});
  const [targetDraftRecords, setTargetDraftRecords] = useState<Record<string, NodeTarget>>({});
  const planRequestCoordinator = useRequestCoordinator(setLoading);
  const discoverTargetDraftRecords = useCallback((nextRecords: NodeTarget[]) => {
    setTargetDraftRecords((current) => ({
      ...current,
      ...Object.fromEntries(nextRecords.map((target) => [target.id, target])),
    }));
  }, []);

  const initializePlan = useCallback(async () => {
    setPlan(undefined);
    setOfflineTargets([]);
    setTargetBlocking({});
    setTargetDialogField(undefined);
    setTargetRecords({});
    setTargetDraftRecords({});
    if (initialPlan) {
      setPlan(initialPlan);
      setInputs(defaultInputs(initialPlan.input_schema || {}));
      return;
    }
    const ticket = planRequestCoordinator.begin({ visible: true });
    if (!ticket) return;
    try {
      const next = await get<WorkflowLaunchPlan>(planUrl, { signal: ticket.signal });
      if (!planRequestCoordinator.shouldApply(ticket)) return;
      setPlan(next);
      setInputs(defaultInputs(next.input_schema || {}));
    } catch (error) {
      if (planRequestCoordinator.shouldApply(ticket)) message.error(error instanceof Error ? error.message : t('workflowOrchestration.launch.planFailed', '无法生成启动计划'));
    } finally {
      planRequestCoordinator.finish(ticket);
    }
  }, [get, initialPlan, message, planRequestCoordinator, planUrl]);

  useAutoRequest(open ? `launch-plan:${planUrl}:${initialPlan?.launch_token || 'remote'}` : undefined, initializePlan);
  useEffect(() => {
    if (open) return;
    planRequestCoordinator.invalidate();
    setPlan(undefined);
    setInputs({});
    setOfflineTargets([]);
    setTargetBlocking({});
    setTargetDialogField(undefined);
    setTargetDraft([]);
    setTargetDraftBlocked(false);
    setTargetRecords({});
    setTargetDraftRecords({});
  }, [open, planRequestCoordinator]);

  const targetFieldMap = useMemo(() => Object.fromEntries((plan?.target_fields || []).map((field) => [field.key, field])), [plan]);
  const properties = Object.entries(plan?.input_schema?.properties || {});
  const uniqueTargetTotal = new Set((plan?.target_fields || []).flatMap((field) => Array.isArray(inputs[field.key]) ? inputs[field.key] as string[] : [])).size;
  const formBlocked = Boolean(plan && (
    Object.values(targetBlocking).some(Boolean)
    || (plan.target_fields || []).some((field) => {
      const selected = Array.isArray(inputs[field.key]) ? inputs[field.key] as unknown[] : [];
      return selected.length < field.min_count || selected.length > field.max_count;
    })
    || properties.some(([key, schema]) => {
      const ui = plan.ui_schema?.[key];
      const widget = (ui && typeof ui === 'object' && !Array.isArray(ui) ? (ui as Record<string, unknown>)['ui:widget'] : undefined) || schema['x-widget'];
      const value = inputs[key];
      if (widget === 'file-upload') return !value || typeof value !== 'object' || Array.isArray(value) || ((value as Record<string, unknown>).kind === 'uploaded' && !(value as Record<string, unknown>).token);
      return false;
    })
  ));
  const submit = async (offlineConfirmed = false) => {
    if (!plan) return;
    setSubmitting(true);
    onSubmittingChange?.(true);
    try {
      const execution = await post<ExecutionRecord>(submitUrl, { launch_token: plan.launch_token, inputs, offline_confirmed: offlineConfirmed });
      message.success(t('workflowOrchestration.launch.started', '已启动流程执行'));
      onStarted(execution);
    } catch (error) {
      if (error instanceof HandledRequestError && error.code === 'OFFLINE_CONFIRMATION_REQUIRED') {
        const payload = error.payload as { offline_targets?: NodeTarget[] } | undefined;
        setOfflineTargets(payload?.offline_targets || []);
      } else if (!(error instanceof HandledRequestError)) message.error(error instanceof Error ? error.message : t('workflowOrchestration.launch.startFailed', '启动失败'));
    } finally { setSubmitting(false); onSubmittingChange?.(false); }
  };

  const openTargetDialog = (field: WorkflowTargetField) => {
    setTargetDialogField(field);
    setTargetDraft(Array.isArray(inputs[field.key]) ? inputs[field.key] as string[] : []);
    setTargetDraftBlocked(Boolean(targetBlocking[field.key]));
    setTargetDraftRecords(targetRecords);
  };

  const confirmTargetDialog = () => {
    if (!targetDialogField) return;
    setOfflineTargets([]);
    setInputs((current) => ({ ...current, [targetDialogField.key]: targetDraft }));
    setTargetBlocking((current) => ({ ...current, [targetDialogField.key]: targetDraftBlocked }));
    setTargetRecords((current) => ({
      ...current,
      ...Object.fromEntries(targetDraft.flatMap((id) => targetDraftRecords[id] ? [[id, targetDraftRecords[id]]] : [])),
    }));
    setTargetDialogField(undefined);
  };

  return <><OperateModal width={880} title={title} open={open} destroyOnHidden footer={<div className="flex items-center justify-between gap-3"><div className="text-left text-xs text-[var(--color-text-3)]">{plan ? t('workflowOrchestration.launch.frozenVersion', '冻结版本 v{version} · {count} 台目标', { version: plan.workflow_version, count: uniqueTargetTotal }) : ''}</div><div className="flex gap-2"><WorkflowPermission operation="Execute" instancePermissions={instancePermissions}><Button onClick={onClose}>{t('common.cancel', '取消')}</Button></WorkflowPermission>{offlineTargets.length > 0 ? <WorkflowPermission operation="Execute" instancePermissions={instancePermissions}><Popconfirm title={t('workflowOrchestration.launch.offlineConfirm', '确认对 {count} 台当前离线主机仍然启动？', { count: offlineTargets.length })} description={t('workflowOrchestration.launch.offlineConfirmHint', '离线主机可能采集失败，本次确认会记入执行快照。')} okText={t('workflowOrchestration.launch.confirmStart', '确认启动')} cancelText={t('workflowOrchestration.launch.returnToEdit', '返回修改')} onConfirm={() => void submit(true)}><Button danger type="primary" loading={submitting} disabled={formBlocked}>{t('workflowOrchestration.launch.startAnyway', '仍然启动')}</Button></Popconfirm></WorkflowPermission> : <WorkflowPermission operation="Execute" instancePermissions={instancePermissions}><Button type="primary" loading={submitting} disabled={loading || formBlocked} onClick={() => void submit(false)}>{t('workflowOrchestration.launch.start', '启动执行')}</Button></WorkflowPermission>}</div></div>} styles={{ body: { paddingBlock: 24 }, footer: { marginTop: 8 } }} onCancel={onClose}>
    {loading ? <div className="flex min-h-64 items-center justify-center"><Spin tip={t('workflowOrchestration.launch.generatingPlan', '正在生成启动计划')} /></div> : !plan ? <Empty description={t('workflowOrchestration.launch.cannotGetPlan', '无法获取启动计划')} /> : <div className="max-h-[68vh] space-y-6 overflow-y-auto pr-1">
      <div className="grid gap-3 rounded-lg bg-[var(--color-fill-1)] px-4 py-3 text-sm sm:grid-cols-2"><div><span className="mr-3 text-[var(--color-text-3)]">{t('workflowOrchestration.workflow.shortName', '流程')}</span><span className="font-medium text-[var(--color-text-1)]">{plan.workflow_name}</span></div><div><span className="mr-3 text-[var(--color-text-3)]">{t('workflowOrchestration.launch.activeVersion', '生效版本')}</span><span className="font-medium text-[var(--color-text-1)]">v{plan.workflow_version}</span></div></div>
      {offlineTargets.length > 0 && <Alert type="warning" showIcon message={t('workflowOrchestration.launch.offlineFound', '发现 {count} 台离线主机', { count: offlineTargets.length })} description={<div className="mt-1 flex flex-wrap gap-1">{offlineTargets.map((item) => <Tag key={item.id} color="warning">{item.name || item.ip} · {item.ip}</Tag>)}</div>} closable onClose={() => setOfflineTargets([])} />}
      <Form layout="vertical">{properties.map(([key, schema]) => {
        const ui = plan.ui_schema?.[key];
        const widget = (ui && typeof ui === 'object' && !Array.isArray(ui) ? (ui as Record<string, unknown>)['ui:widget'] : undefined) || schema['x-widget'];
        const change = (next: unknown) => setInputs((current) => ({ ...current, [key]: next }));
        return <Form.Item key={key} label={schema.title || key} required={plan.input_schema.required?.includes(key)} tooltip={schema.description || undefined}>{targetFieldMap[key] ? <WorkflowPermission operation="Execute" instancePermissions={instancePermissions} className="block w-full"><button type="button" className="flex w-full items-center justify-between gap-4 rounded-lg border border-[var(--color-border-1)] px-4 py-3 text-left transition-colors hover:border-[var(--color-primary)] focus-visible:outline-2 focus-visible:outline-[var(--color-primary)]" onClick={() => openTargetDialog(targetFieldMap[key])}><span><span className="block text-sm font-medium text-[var(--color-text-1)]">{inputs[key] && Array.isArray(inputs[key]) && inputs[key].length ? t('workflowOrchestration.launch.hostsSelected', '已选择 {count} 台主机', { count: inputs[key].length }) : t('workflowOrchestration.launch.selectHosts', '请选择目标主机')}</span><span className="mt-1 block text-xs text-[var(--color-text-3)]">{t('workflowOrchestration.launch.selectorHint', '点击打开主机选择器，确认后回填本执行表单')}</span></span><span className="shrink-0 text-sm text-[var(--color-primary)]">{t('workflowOrchestration.launch.selectTarget', '选择主机')}</span></button></WorkflowPermission> : widget === 'file-upload' ? <RuntimeFileUpload workflowId={plan.workflow_id} fieldKey={key} launchToken={plan.launch_token} schema={schema} value={inputs[key]} onChange={change} /> : <RuntimeInputField schema={schema} value={inputs[key]} onChange={change} />}</Form.Item>;
      })}</Form>
      {properties.length === 0 && <div className="text-sm text-[var(--color-text-3)]">{t('workflowOrchestration.launch.noParameters', '该流程无需填写运行参数。')}</div>}
      {plan.risk_summary?.description && <section className="rounded-lg bg-[var(--color-fill-1)] p-4"><div className="text-sm font-medium text-[var(--color-text-1)]">{t('workflowOrchestration.launch.impact', '执行影响')}</div><div className="mt-2 text-sm leading-6 text-[var(--color-text-2)]">{plan.risk_summary.description}</div></section>}
    </div>}
  </OperateModal><OperateModal width={1040} zIndex={WORKFLOW_NESTED_SELECTOR_Z_INDEX} title={targetDialogField ? t('workflowOrchestration.launch.selectTargetTitle', '选择主机 · {name}', { name: targetDialogField.name }) : t('workflowOrchestration.launch.selectTarget', '选择主机')} open={Boolean(open && targetDialogField)} destroyOnHidden footer={<div className="flex justify-end gap-2"><WorkflowPermission operation="Execute" instancePermissions={instancePermissions}><Button onClick={() => setTargetDialogField(undefined)}>{t('common.cancel', '取消')}</Button></WorkflowPermission><WorkflowPermission operation="Execute" instancePermissions={instancePermissions}><Button type="primary" disabled={!targetDialogField || targetDraft.length < targetDialogField.min_count || targetDraft.length > targetDialogField.max_count || targetDraftBlocked} onClick={confirmTargetDialog}>{t('workflowOrchestration.launch.confirmSelection', '确认选择')}</Button></WorkflowPermission></div>} styles={{ body: { maxHeight: 'calc(100vh - 220px)', overflowY: 'auto', paddingBlock: 24 }, footer: { marginTop: 8 } }} onCancel={() => setTargetDialogField(undefined)}>{targetDialogField && <RuntimeTargetSelector field={targetDialogField} value={targetDraft} onChange={setTargetDraft} onBlockingChange={setTargetDraftBlocked} recordCache={targetDraftRecords} onRecordsDiscovered={discoverTargetDraftRecords} />}</OperateModal></>;
}
