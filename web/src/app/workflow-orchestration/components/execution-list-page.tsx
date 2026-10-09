'use client';

import { ReloadOutlined } from '@ant-design/icons';
import { Button, Empty, Input, Tabs, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useRouter, useSearchParams } from 'next/navigation';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import CustomTable from '@/components/custom-table';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { useTranslation } from '@/utils/i18n';
import useApiClient from '@/utils/request';
import { executionStatusPresentation, formatDuration, formatStartedBy, formatTriggerTypeLabel } from '../lib/presentation';
import { useAutoRequest, useRequestCoordinator } from '../lib/use-request-coordinator';
import type { ExecutionRecord, ExecutionStatus, PaginatedResponse, WorkflowTriggerType } from '../lib/types';
import { ExecutionDetailDrawer } from './execution-detail-drawer';
import { WorkflowTablePanel } from './workflow-table-panel';
import { WorkflowPermission } from './workflow-permission';

const API = '/workflow_orchestration/api';

interface AppliedFilters {
  query?: string;
  status?: ExecutionStatus;
  triggerType?: WorkflowTriggerType;
  mode?: ExecutionRecord['mode'];
  mine?: boolean;
}

function filterQuery(filters: AppliedFilters) {
  const params = new URLSearchParams();
  if (filters.query) params.set('query', filters.query);
  if (filters.status) params.set('status', filters.status);
  if (filters.triggerType) params.set('trigger_type', filters.triggerType);
  if (filters.mode) params.set('mode', filters.mode);
  if (filters.mine) params.set('scope', 'mine');
  const query = params.toString();
  return query ? `?${query}` : '';
}

interface ExecutionListPageProps {
  initialExecutionId?: string;
  initialNodeReference?: string;
  initialInstanceId?: string;
}

export function ExecutionListPage({ initialExecutionId, initialNodeReference, initialInstanceId }: ExecutionListPageProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { get } = useApiClient();
  const { t } = useTranslation();
  const { convertToLocalizedTime } = useLocalizedTime();
  const initialQuery = searchParams.get('query')?.trim() || undefined;
  const rawStatus = searchParams.get('status');
  const initialStatus = rawStatus && Object.hasOwn(executionStatusPresentation, rawStatus) ? rawStatus as ExecutionStatus : undefined;
  const rawTriggerType = searchParams.get('trigger_type');
  const initialTriggerType = ['FORM', 'SCHEDULE', 'WEBHOOK', 'NATS'].includes(rawTriggerType || '') ? rawTriggerType as WorkflowTriggerType : undefined;
  const rawMode = searchParams.get('mode');
  const initialMode = rawMode === 'PRODUCTION' || rawMode === 'DEBUG' ? rawMode : undefined;
  const initialMine = searchParams.get('scope') === 'mine';
  const lastRouteMine = useRef(initialMine);
  const [filters, setFilters] = useState<AppliedFilters>({
    query: initialQuery,
    status: initialMine ? undefined : initialStatus,
    triggerType: initialTriggerType,
    mode: initialMine ? undefined : initialMode,
    mine: initialMine,
  });
  const [queryDraft, setQueryDraft] = useState(initialQuery || '');
  const [executions, setExecutions] = useState<ExecutionRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20 });
  const [selectedExecutionId, setSelectedExecutionId] = useState(initialExecutionId);
  const listRequestCoordinator = useRequestCoordinator(setLoading);
  const triggerLabels: Record<WorkflowTriggerType, string> = {
    FORM: formatTriggerTypeLabel('FORM', t),
    SCHEDULE: formatTriggerTypeLabel('SCHEDULE', t),
    WEBHOOK: formatTriggerTypeLabel('WEBHOOK', t),
    NATS: formatTriggerTypeLabel('NATS', t),
  };
  const modeLabels: Record<ExecutionRecord['mode'], string> = {
    PRODUCTION: t('workflowOrchestration.execution.production', '正式'),
    DEBUG: t('workflowOrchestration.execution.debug', '调试'),
  };

  const loadExecutions = useCallback(async (quiet = false) => {
    const ticket = listRequestCoordinator.begin({ visible: !quiet });
    if (!ticket) return;
    try {
      const params = new URLSearchParams({ page: String(pagination.current), page_size: String(pagination.pageSize) });
      if (filters.query) params.set('query', filters.query);
      if (filters.status) params.set('status', filters.status);
      if (filters.triggerType) params.set('trigger_type', filters.triggerType);
      if (filters.mode) params.set('mode', filters.mode);
      if (filters.mine) params.set('mine', '1');
      const executionResponse = await get<PaginatedResponse<ExecutionRecord>>(`${API}/executions/?${params.toString()}`, { signal: ticket.signal });
      if (!listRequestCoordinator.shouldApply(ticket)) return;
      setExecutions(executionResponse?.items || []);
      setTotal(executionResponse?.count || 0);
    } catch {
      if (!listRequestCoordinator.shouldApply(ticket)) return;
      setExecutions([]);
      setTotal(0);
    } finally {
      listRequestCoordinator.finish(ticket);
    }
  }, [filters, get, listRequestCoordinator, pagination.current, pagination.pageSize]);

  const listRequestKey = useMemo(() => JSON.stringify([pagination.current, pagination.pageSize, filters]), [filters, pagination.current, pagination.pageSize]);
  useAutoRequest(listRequestKey, loadExecutions);
  useEffect(() => {
    if (lastRouteMine.current === initialMine) return;
    lastRouteMine.current = initialMine;
    setSelectedExecutionId(undefined);
    setPagination((current) => ({ ...current, current: 1 }));
    setQueryDraft('');
    setFilters({ mine: initialMine });
  }, [initialMine]);
  useEffect(() => {
    if (!executions.some((execution) => ['QUEUED', 'RUNNING', 'WAITING_APPROVAL', 'TERMINATING'].includes(execution.status))) return;
    const poll = window.setInterval(() => {
      if (document.visibilityState === 'visible') void loadExecutions(true);
    }, 10_000);
    return () => window.clearInterval(poll);
  }, [executions, loadExecutions]);

  const switchScope = (scope: 'all' | 'mine') => {
    const mine = scope === 'mine';
    setSelectedExecutionId(undefined);
    setPagination((current) => ({ ...current, current: 1 }));
    setQueryDraft('');
    setFilters({ mine });
    router.replace(`/workflow-orchestration/executions${mine ? '?scope=mine' : ''}`);
  };

  const columns: ColumnsType<ExecutionRecord> = [
    {
      title: t('workflowOrchestration.workflow.name', '流程名称'),
      dataIndex: 'workflow_name',
      key: 'workflow_name',
      width: 260,
      render: (name: string, record) => {
        const value = name ? `${name}${record.workflow_deleted ? t('workflowOrchestration.workflow.deletedSuffix', '（已删除）') : ''}` : '--';
        return <EllipsisWithTooltip text={value} className="w-full overflow-hidden text-ellipsis whitespace-nowrap font-medium text-[var(--color-text-1)]" />;
      },
    },
    { title: t('common.status', '状态'), dataIndex: 'status', key: 'status', width: 120, filters: Object.entries(executionStatusPresentation).map(([value, item]) => ({ value, text: t(`workflowOrchestration.execution.status.${value}`, item.label) })), filterMultiple: false, filteredValue: filters.status ? [filters.status] : null, render: (value: ExecutionStatus) => {
      const presentation = executionStatusPresentation[value] || { color: 'default', label: '--' };
      return <Tag color={presentation.color}>{t(`workflowOrchestration.execution.status.${value}`, presentation.label)}</Tag>;
    } },
    { title: t('workflowOrchestration.trigger.title', '触发器'), dataIndex: 'trigger_type', key: 'trigger_type', width: 110, filters: Object.entries(triggerLabels).map(([value, text]) => ({ value, text })), filterMultiple: false, filteredValue: filters.triggerType ? [filters.triggerType] : null, render: (value: WorkflowTriggerType) => triggerLabels[value] || '--' },
    { title: t('workflowOrchestration.execution.mode', '模式'), dataIndex: 'mode', key: 'mode', width: 90, filters: Object.entries(modeLabels).map(([value, text]) => ({ value, text })), filterMultiple: false, filteredValue: filters.mode ? [filters.mode] : null, render: (value: ExecutionRecord['mode']) => modeLabels[value] || '--' },
    { title: t('workflowOrchestration.execution.startedBy', '发起人'), dataIndex: 'started_by', key: 'started_by', width: 120, render: (value: string) => <EllipsisWithTooltip text={formatStartedBy(value, t)} className="w-full overflow-hidden text-ellipsis whitespace-nowrap" /> },
    { title: t('workflowOrchestration.execution.startedAt', '开始时间'), dataIndex: 'created_at', key: 'created_at', width: 180, render: (value: string) => <span className="whitespace-nowrap tabular-nums">{value ? convertToLocalizedTime(value) : '--'}</span> },
    { title: t('workflowOrchestration.execution.duration', '耗时'), dataIndex: 'duration_ms', key: 'duration_ms', width: 100, render: (value: number | null) => <span className="tabular-nums">{formatDuration(value)}</span> },
    { title: t('common.actions', '操作'), key: 'actions', width: 80, fixed: 'right', render: (_, record) => {
      const actionable = record.actionable_approval_ids.length > 0;
      const actionLabel = actionable
        ? t('workflowOrchestration.approval.action', '审批')
        : t('common.view', '查看');
      return <WorkflowPermission operation={actionable ? 'Approve' : 'View'} area="executions" instancePermissions={record.permission}><Button type="link" size="small" className="px-0" onClick={() => setSelectedExecutionId(record.id)}>{actionLabel}</Button></WorkflowPermission>;
    } },
  ];

  return (
    <main className="flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-[var(--color-bg-1)] p-4">
      <Tabs
        className="shrink-0 [&_.ant-tabs-nav]:mb-3"
        activeKey={filters.mine ? 'mine' : 'all'}
        onChange={(key) => switchScope(key as 'all' | 'mine')}
        items={[
          { key: 'all', label: t('workflowOrchestration.execution.all', '全部执行') },
          { key: 'mine', label: t('workflowOrchestration.approval.mine', '待我审批') },
        ]}
      />
      <WorkflowTablePanel
        filters={(
          <>
            <Input.Search
              allowClear
              enterButton
              className="w-[220px]"
              placeholder={t('workflowOrchestration.workflow.searchPlaceholder', '搜索流程名称')}
              value={queryDraft}
              onChange={(event) => {
                const value = event.target.value;
                setQueryDraft(value);
                if (!value) {
                  setPagination((current) => ({ ...current, current: 1 }));
                  setFilters((current) => ({ ...current, query: undefined }));
                }
              }}
              onSearch={(value) => {
                setPagination((current) => ({ ...current, current: 1 }));
                setFilters((current) => ({ ...current, query: value.trim() || undefined }));
              }}
            />
          </>
        )}
        actions={<WorkflowPermission operation="View" area="executions"><Button aria-label={t('workflowOrchestration.execution.refresh', '刷新执行记录')} icon={<ReloadOutlined />} onClick={() => void loadExecutions()} /></WorkflowPermission>}
      >
        <CustomTable<ExecutionRecord>
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={executions}
          className="[&_.ant-table-cell]:whitespace-nowrap"
          locale={{ emptyText: <Empty description={t('workflowOrchestration.execution.empty', '暂无匹配的执行记录')} /> }}
          onChange={(_, tableFilters, __, extra) => {
            if (extra.action !== 'filter') return;
            setFilters((current) => ({
              ...current,
              status: tableFilters.status?.[0] as ExecutionStatus | undefined,
              triggerType: tableFilters.trigger_type?.[0] as WorkflowTriggerType | undefined,
              mode: tableFilters.mode?.[0] as ExecutionRecord['mode'] | undefined,
            }));
            setPagination((current) => ({ ...current, current: 1 }));
          }}
          pagination={{
            current: pagination.current,
            pageSize: pagination.pageSize,
            total,
            showSizeChanger: true,
            pageSizeOptions: [10, 20, 50, 100],
            onChange: (current, pageSize) => setPagination({ current, pageSize }),
          }}
        />
      </WorkflowTablePanel>
      <ExecutionDetailDrawer
        executionId={selectedExecutionId}
        initialNodeReference={selectedExecutionId === initialExecutionId ? initialNodeReference : undefined}
        initialInstanceId={selectedExecutionId === initialExecutionId ? initialInstanceId : undefined}
        open={Boolean(selectedExecutionId)}
        onClose={() => {
          setSelectedExecutionId(undefined);
          if (initialExecutionId) router.push(`/workflow-orchestration/executions${filterQuery(filters)}`);
        }}
        onExecutionChanged={() => {
          void loadExecutions(true);
        }}
        onRerunStarted={setSelectedExecutionId}
      />
    </main>
  );
}
