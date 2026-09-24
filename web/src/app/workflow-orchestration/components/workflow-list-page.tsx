'use client';

import { MoreOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { App, Button, Dropdown, Empty, Input, Popconfirm, Switch, Tag, Tooltip } from 'antd';
import type { MenuProps } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useRouter, useSearchParams } from 'next/navigation';
import { useCallback, useMemo, useState } from 'react';

import CustomTable from '@/components/custom-table';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import OperateModal from '@/components/operate-modal';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { useTranslation } from '@/utils/i18n';
import useApiClient from '@/utils/request';
import type { ExecutionRecord, PaginatedResponse, WorkflowRecord, WorkflowTriggerType } from '../lib/types';
import { useAutoRequest, useRequestCoordinator } from '../lib/use-request-coordinator';
import { createDefaultWorkflowName, createDuplicateWorkflowName } from '../lib/workflow-draft';
import { WorkflowLaunchDialog } from './workflow-launch-dialog';
import { WorkflowPermission } from './workflow-permission';
import { WorkflowTablePanel } from './workflow-table-panel';

const API = '/workflow_orchestration/api';
type ListStatus = 'DRAFT' | 'PUBLISHED';
type EnabledFilter = 'true' | 'false';

export function WorkflowListPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { message, modal } = App.useApp();
  const { t } = useTranslation();
  const { convertToLocalizedTime } = useLocalizedTime();
  const { get, post, del } = useApiClient();
  const [records, setRecords] = useState<WorkflowRecord[]>([]);
  const [count, setCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [queryDraft, setQueryDraft] = useState('');
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState<ListStatus | undefined>(() => {
    const initial = searchParams.get('status');
    return initial === 'DRAFT' || initial === 'PUBLISHED' ? initial : undefined;
  });
  const [enabledFilter, setEnabledFilter] = useState<EnabledFilter>();
  const [triggerType, setTriggerType] = useState<WorkflowTriggerType>();
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20 });
  const [busyId, setBusyId] = useState<number>();
  const [duplicateWorkflow, setDuplicateWorkflow] = useState<WorkflowRecord>();
  const [duplicateName, setDuplicateName] = useState('');
  const [runWorkflow, setRunWorkflow] = useState<WorkflowRecord>();
  const requestCoordinator = useRequestCoordinator(setLoading);
  const triggerLabels: Record<WorkflowTriggerType, string> = {
    FORM: t('workflowOrchestration.trigger.form', '表单'),
    SCHEDULE: t('workflowOrchestration.trigger.schedule', '定时'),
    WEBHOOK: 'Webhook',
    NATS: 'NATS',
  };

  const load = useCallback(async () => {
    const ticket = requestCoordinator.begin({ visible: true });
    if (!ticket) return;
    try {
      const params = new URLSearchParams({ page: String(pagination.current), page_size: String(pagination.pageSize) });
      if (query.trim()) params.set('query', query.trim());
      if (status) params.set('status', status);
      if (enabledFilter) params.set('enabled', enabledFilter);
      if (triggerType) params.set('trigger_type', triggerType);
      const response = await get<PaginatedResponse<WorkflowRecord>>(`${API}/workflows/?${params.toString()}`, { signal: ticket.signal });
      if (!requestCoordinator.shouldApply(ticket)) return;
      setRecords(response?.items || []); setCount(response?.count || 0);
    } catch {
      if (!requestCoordinator.shouldApply(ticket)) return;
      setRecords([]);
      setCount(0);
    } finally { requestCoordinator.finish(ticket); }
  }, [enabledFilter, get, pagination.current, pagination.pageSize, query, requestCoordinator, status, triggerType]);

  const requestKey = useMemo(() => JSON.stringify([pagination.current, pagination.pageSize, query, status, enabledFilter, triggerType]), [enabledFilter, pagination.current, pagination.pageSize, query, status, triggerType]);
  useAutoRequest(requestKey, load);

  const create = () => {
    const name = createDefaultWorkflowName(new Date(), t('workflowOrchestration.workflow.defaultNamePrefix', '流程'));
    router.push(`/workflow-orchestration/workflows/new?mode=edit&name=${encodeURIComponent(name)}`);
  };

  const toggle = async (record: WorkflowRecord) => {
    setBusyId(record.id);
    try {
      const updated = await post<WorkflowRecord>(`${API}/workflows/${record.id}/enabled/`, { enabled: !record.enabled });
      setRecords((items) => items.map((item) => item.id === record.id ? updated : item));
      message.success(updated.enabled
        ? t('workflowOrchestration.workflow.enabledSuccess', '流程已启用')
        : t('workflowOrchestration.workflow.disabledSuccess', '流程已停用，不影响历史执行'));
    } finally { setBusyId(undefined); }
  };

  const duplicate = async () => {
    const name = duplicateName.trim();
    if (!duplicateWorkflow || !name) return;
    setBusyId(duplicateWorkflow.id);
    try {
      const copied = await post<WorkflowRecord>(`${API}/workflows/${duplicateWorkflow.id}/duplicate/`, { name });
      setRecords((items) => [copied, ...items]);
      setCount((value) => value + 1);
      setDuplicateWorkflow(undefined);
      setDuplicateName('');
      message.success(t('workflowOrchestration.workflow.duplicatedSuccess', '已复制为新的纯草稿'));
    } finally {
      setBusyId(undefined);
    }
  };

  const remove = async (record: WorkflowRecord) => {
    setBusyId(record.id);
    try { await del(`${API}/workflows/${record.id}/`); setRecords((items) => items.filter((item) => item.id !== record.id)); setCount((value) => Math.max(0, value - 1)); message.success(t('workflowOrchestration.workflow.deletedSuccess', '流程已删除，历史执行仍保留')); }
    finally { setBusyId(undefined); }
  };

  const execute = (record: WorkflowRecord) => {
    setRunWorkflow(record);
  };

  const openMoreAction = (key: string, record: WorkflowRecord) => {
    if (key === 'executions') {
      router.push(`/workflow-orchestration/executions?query=${encodeURIComponent(record.name)}`);
      return;
    }
    if (key === 'duplicate') {
      setDuplicateWorkflow(record);
      setDuplicateName(createDuplicateWorkflowName(record.name, t('workflowOrchestration.workflow.duplicateSuffix', '（副本）')));
      return;
    }
    if (key === 'delete') {
      modal.confirm({
        title: t('workflowOrchestration.workflow.deleteConfirm', '确认删除流程？'),
        content: t('workflowOrchestration.workflow.deleteHint', '流程本身不可恢复，历史版本快照与执行记录仍保留。'),
        okText: t('common.delete', '删除'),
        cancelText: t('common.cancel', '取消'),
        okButtonProps: { danger: true },
        onOk: () => remove(record),
      });
    }
  };

  const moreActions = (record: WorkflowRecord): MenuProps['items'] => [
    { key: 'executions', label: <WorkflowPermission operation="View"><span>{t('workflowOrchestration.execution.records', '执行记录')}</span></WorkflowPermission> },
    { key: 'duplicate', label: <WorkflowPermission operation="Add"><span>{t('common.copy', '复制')}</span></WorkflowPermission> },
    { type: 'divider' },
    { key: 'delete', label: <WorkflowPermission operation="Delete" instancePermissions={record.permission}><span>{t('common.delete', '删除')}</span></WorkflowPermission>, danger: true },
  ];

  const runDisabledReason = (record: WorkflowRecord) => {
    if (!record.current_version) return t('workflowOrchestration.workflow.runRequiresPublish', '请先发布流程');
    if (!record.enabled) return t('workflowOrchestration.workflow.runRequiresEnable', '请先启用流程');
    if (record.trigger_summary?.includes('FORM')) return '';
    const types = record.trigger_summary || [];
    if (types.length === 1 && types[0] === 'SCHEDULE') {
      return t('workflowOrchestration.workflow.scheduleRunHint', '流程将按配置时间自动触发；如需验证，请到编辑页测试定时触发器');
    }
    if (types.length === 1 && types[0] === 'WEBHOOK') {
      return t('workflowOrchestration.workflow.webhookRunHint', '请通过 Postman、curl 或外部系统向正式 Webhook 地址发送 POST 请求');
    }
    if (types.length === 1 && types[0] === 'NATS') {
      return t('workflowOrchestration.workflow.natsRunHint', '流程由 NATS 事件自动触发；如需验证，请到编辑页监听测试事件');
    }
    return t('workflowOrchestration.workflow.externalRunHint', '该流程由定时、Webhook 或 NATS 入口自动触发；请到编辑页查看入口或测试触发器');
  };

  const columns: ColumnsType<WorkflowRecord> = [
    {
      title: t('workflowOrchestration.workflow.name', '流程名称'),
      dataIndex: 'name',
      key: 'name',
      width: 220,
      render: (value: string) => <EllipsisWithTooltip text={value || '--'} className="w-full overflow-hidden text-ellipsis whitespace-nowrap" />,
    },
    {
      title: t('workflowOrchestration.workflow.publishStatus', '发布状态'),
      key: 'status',
      width: 105,
      filters: [
        { value: 'DRAFT', text: t('workflowOrchestration.status.draftOnly', '纯草稿') },
        { value: 'PUBLISHED', text: t('workflowOrchestration.status.published', '已发布') },
      ],
      filterMultiple: false,
      filteredValue: status ? [status] : null,
      render: (_, record) => record.current_version
        ? <Tag color="blue">{t('workflowOrchestration.status.published', '已发布')}</Tag>
        : <Tag>{t('workflowOrchestration.status.draftOnly', '纯草稿')}</Tag>,
    },
    {
      title: t('workflowOrchestration.workflow.enableStatus', '启用状态'),
      key: 'enabled',
      width: 105,
      filters: [
        { value: 'true', text: t('workflowOrchestration.status.enabled', '已启用') },
        { value: 'false', text: t('workflowOrchestration.status.disabled', '已停用') },
      ],
      filterMultiple: false,
      filteredValue: enabledFilter ? [enabledFilter] : null,
      render: (_, record) => {
        const unavailable = !record.current_version;
        const title = unavailable
          ? t('workflowOrchestration.workflow.enableRequiresPublish', '发布后可启用')
          : undefined;
        const control = <Switch
          size="small"
          checked={record.enabled}
          disabled={unavailable}
          loading={busyId === record.id}
          aria-label={t('workflowOrchestration.workflow.enableSwitchFor', '启用状态：{name}', { name: record.name })}
        />;
        if (unavailable) return <Tooltip title={title}><span className="inline-flex">{control}</span></Tooltip>;
        return <WorkflowPermission operation="Publish" instancePermissions={record.permission}>
          <Popconfirm
            title={record.enabled ? t('workflowOrchestration.workflow.disableConfirm', '停用该流程？') : t('workflowOrchestration.workflow.enableConfirm', '启用当前发布版本？')}
            description={record.enabled
              ? t('workflowOrchestration.workflow.disableHint', '停用后将拒绝新的触发事件，正在执行的流程不受影响。')
              : t('workflowOrchestration.workflow.enableHint', '启用后，定时、Webhook 和 NATS 正式入口将立即生效。')}
            okText={record.enabled ? t('common.disable', '停用') : t('common.enable', '启用')}
            cancelText={t('common.cancel', '取消')}
            okButtonProps={record.enabled ? { danger: true } : undefined}
            onConfirm={() => toggle(record)}
          >
            <span className="inline-flex">{control}</span>
          </Popconfirm>
        </WorkflowPermission>;
      },
    },
    {
      title: t('common.version', '版本'),
      key: 'version',
      width: 160,
      render: (_, record) => {
        const value = record.current_version
          ? `v${record.current_version}${record.has_draft ? t('workflowOrchestration.workflow.unpublishedSuffix', ' · 有未发布更改') : ''}`
          : '--';
        return <EllipsisWithTooltip text={value} className="w-full overflow-hidden text-ellipsis whitespace-nowrap" />;
      },
    },
    {
      title: t('workflowOrchestration.trigger.title', '触发器'),
      dataIndex: 'trigger_summary',
      key: 'trigger_type',
      width: 150,
      filters: Object.entries(triggerLabels).map(([value, text]) => ({ value, text })),
      filterMultiple: false,
      filteredValue: triggerType ? [triggerType] : null,
      render: (value: WorkflowTriggerType[]) => {
        const text = value?.length ? value.map((item) => triggerLabels[item] || '--').join(',') : '--';
        return <EllipsisWithTooltip text={text} className="w-full overflow-hidden text-ellipsis whitespace-nowrap" />;
      },
    },
    {
      title: t('common.updatedBy', '更新人'),
      dataIndex: 'updated_by',
      key: 'updated_by',
      width: 110,
      render: (value: string) => <EllipsisWithTooltip text={value || '--'} className="w-full overflow-hidden text-ellipsis whitespace-nowrap" />,
    },
    { title: t('common.updatedTime', '更新时间'), dataIndex: 'updated_at', key: 'updated_at', width: 170, render: (value: string) => <span className="whitespace-nowrap tabular-nums">{value ? convertToLocalizedTime(value) : '--'}</span> },
    {
      title: t('common.actions', '操作'),
      key: 'actions',
      width: 136,
      fixed: 'right',
      render: (_, record) => (
        <div className="flex items-center gap-1 whitespace-nowrap">
          <WorkflowPermission operation="Edit" instancePermissions={record.permission}><Button type="link" size="small" onClick={() => router.push(`/workflow-orchestration/workflows/${record.id}?mode=edit`)}>{t('common.edit', '编辑')}</Button></WorkflowPermission>
          <WorkflowPermission operation="Execute" instancePermissions={record.permission}>
            <Tooltip title={runDisabledReason(record) || undefined}>
              <span><Button type="link" size="small" disabled={Boolean(runDisabledReason(record))} onClick={() => void execute(record)}>{t('workflowOrchestration.action.run', '运行')}</Button></span>
            </Tooltip>
          </WorkflowPermission>
          <WorkflowPermission operation="View" instancePermissions={record.permission}>
            <Dropdown
              trigger={['click']}
              menu={{ items: moreActions(record), onClick: ({ key }) => openMoreAction(key, record) }}
            >
              <Button
              type="text"
              size="small"
              loading={busyId === record.id}
              aria-label={t('workflowOrchestration.action.moreFor', '更多操作：{name}', { name: record.name })}
              icon={<MoreOutlined />}
              />
            </Dropdown>
          </WorkflowPermission>
        </div>
      ),
    },
  ];

  return <main className="flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-[var(--color-bg-1)] p-4">
    <WorkflowTablePanel
      filters={<Input.Search className="w-[220px]" allowClear enterButton placeholder={t('workflowOrchestration.workflow.searchPlaceholder', '搜索流程名称')} value={queryDraft} onChange={(event) => { const value = event.target.value; setQueryDraft(value); if (!value) { setPagination((item) => ({ ...item, current: 1 })); setQuery(''); } }} onSearch={(value) => { setPagination((item) => ({ ...item, current: 1 })); setQuery(value.trim()); }} />}
      actions={<><WorkflowPermission operation="Add"><Button type="primary" icon={<PlusOutlined />} onClick={create}>{t('workflowOrchestration.workflow.create', '新建流程')}</Button></WorkflowPermission><WorkflowPermission operation="View"><Button aria-label={t('workflowOrchestration.workflow.refresh', '刷新流程列表')} icon={<ReloadOutlined />} onClick={() => void load()} /></WorkflowPermission></>}
    >
      <CustomTable rowKey="id" loading={loading} columns={columns} dataSource={records} className="[&_.ant-table-cell]:whitespace-nowrap" locale={{ emptyText: <Empty description={t('workflowOrchestration.workflow.empty', '当前组织还没有流程')} /> }} pagination={{ current: pagination.current, pageSize: pagination.pageSize, total: count, showSizeChanger: true, pageSizeOptions: [10, 20, 50, 100], onChange: (current, pageSize) => setPagination({ current, pageSize }) }} onChange={(_, tableFilters, __, extra) => {
        if (extra.action !== 'filter') return;
        setStatus(tableFilters.status?.[0] as ListStatus | undefined);
        setEnabledFilter(tableFilters.enabled?.[0] as EnabledFilter | undefined);
        setTriggerType(tableFilters.trigger_type?.[0] as WorkflowTriggerType | undefined);
        setPagination((item) => ({ ...item, current: 1 }));
      }} />
    </WorkflowTablePanel>
    <OperateModal
      title={t('workflowOrchestration.workflow.duplicate', '复制流程')}
      open={Boolean(duplicateWorkflow)}
      okText={t('workflowOrchestration.action.confirmDuplicate', '确认复制')}
      cancelText={t('common.cancel', '取消')}
      confirmLoading={Boolean(duplicateWorkflow && busyId === duplicateWorkflow.id)}
      okButtonProps={{ disabled: !duplicateName.trim() }}
      styles={{ footer: { marginTop: 20 } }}
      onOk={() => void duplicate()}
      onCancel={() => { setDuplicateWorkflow(undefined); setDuplicateName(''); }}
    >
      <label className="mb-2 block text-sm" htmlFor="duplicate-workflow-name">{t('workflowOrchestration.workflow.name', '流程名称')}</label>
      <Input id="duplicate-workflow-name" autoFocus maxLength={120} value={duplicateName} onChange={(event) => setDuplicateName(event.target.value)} />
    </OperateModal>
    {runWorkflow && <WorkflowLaunchDialog open title={t('workflowOrchestration.workflow.runTitle', '运行流程 · {name}', { name: runWorkflow.name })} planUrl={`${API}/workflows/${runWorkflow.id}/launch-plan/`} submitUrl={`${API}/workflows/${runWorkflow.id}/run/`} instancePermissions={runWorkflow.permission} onClose={() => setRunWorkflow(undefined)} onSubmittingChange={() => undefined} onStarted={(execution: ExecutionRecord) => { setRunWorkflow(undefined); router.push(`/workflow-orchestration/executions/${execution.id}`); }} />}
  </main>;
}
