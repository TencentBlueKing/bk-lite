'use client';

import {
  ApartmentOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  FileSearchOutlined,
  HistoryOutlined,
  PlayCircleOutlined,
  RightOutlined,
  SyncOutlined,
  TeamOutlined,
  UnorderedListOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import { Badge, Button, Card, Empty, Skeleton, Tag, theme } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import ReactECharts from 'echarts-for-react';
import { useRouter } from 'next/navigation';
import { useCallback, useMemo, useState } from 'react';

import CustomTable from '@/components/custom-table';
import SummaryMetricCard from '@/components/summary-metric-card';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { useTranslation } from '@/utils/i18n';
import useApiClient from '@/utils/request';
import { executionStatusPresentation, formatDuration } from '../lib/presentation';
import { useAutoRequest, useRequestCoordinator } from '../lib/use-request-coordinator';
import type {
  ExecutionRecord,
  ExecutionStatus,
  WorkflowDashboard,
  WorkflowDashboardApproval,
  WorkflowTriggerType,
} from '../lib/types';
import { WorkflowPermission } from './workflow-permission';

const API = '/workflow_orchestration/api';
const DASHBOARD_RECENT_TABLE_SCROLL_Y = 201;
const MY_APPROVALS_HREF = '/workflow-orchestration/executions?scope=mine';
type Translate = (id: string, defaultMessage?: string, values?: Record<string, string | number>) => string;

function deadlineText(dueAt: string | null, t: Translate) {
  if (!dueAt) return t('workflowOrchestration.dashboard.noDeadline', '未设置截止时间');
  const remainingMinutes = dayjs(dueAt).diff(dayjs(), 'minute');
  if (remainingMinutes <= 0) return t('workflowOrchestration.dashboard.expired', '已到期');
  if (remainingMinutes < 60) return t('workflowOrchestration.dashboard.minutesLeft', '剩余 {count} 分钟', { count: remainingMinutes });
  if (remainingMinutes < 24 * 60) return t('workflowOrchestration.dashboard.hoursLeft', '剩余 {count} 小时', { count: Math.ceil(remainingMinutes / 60) });
  return t('workflowOrchestration.dashboard.daysLeft', '剩余 {count} 天', { count: Math.ceil(remainingMinutes / (24 * 60)) });
}

function executionsByWorkflowHref(workflowName: string) {
  const query = workflowName.trim();
  if (!query) return '/workflow-orchestration/executions';
  return `/workflow-orchestration/executions?${new URLSearchParams({ query }).toString()}`;
}

function ApprovalItem({ approval }: { approval: WorkflowDashboardApproval }) {
  const router = useRouter();
  const { t } = useTranslation();
  return (
    <div className="py-3 first:pt-0 last:pb-0">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate font-medium text-[var(--color-text-1)]">{approval.workflow_name}</div>
          <div className="mt-1 truncate text-xs text-[var(--color-text-3)]">{approval.title}</div>
          <div className="mt-1 text-xs text-[var(--color-text-3)]">
            {t('workflowOrchestration.execution.startedByWithColon', '发起人：')}{approval.execution_started_by || '--'} · {deadlineText(approval.due_at, t)}
          </div>
        </div>
        <WorkflowPermission operation="Approve" area="executions"><Button
          type="link"
          size="small"
          className="shrink-0 px-0"
          aria-label={t('workflowOrchestration.dashboard.review', '查看并处理')}
          onClick={() => router.push(MY_APPROVALS_HREF)}
        >
          {t('workflowOrchestration.dashboard.review', '查看并处理')}
        </Button></WorkflowPermission>
      </div>
    </div>
  );
}

export function WorkflowDashboardPage() {
  const router = useRouter();
  const { token } = theme.useToken();
  const { get } = useApiClient();
  const { t } = useTranslation();
  const { convertToLocalizedTime } = useLocalizedTime();
  const [data, setData] = useState<WorkflowDashboard>();
  const [loading, setLoading] = useState(true);
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
      const response = await get<WorkflowDashboard>(`${API}/executions/dashboard/`, { signal: ticket.signal });
      if (requestCoordinator.shouldApply(ticket)) setData(response);
    } catch {
      if (requestCoordinator.shouldApply(ticket)) setData(undefined);
    } finally {
      requestCoordinator.finish(ticket);
    }
  }, [get, requestCoordinator]);

  useAutoRequest('workflow-dashboard', load);

  const statusColor = useCallback((status: ExecutionStatus) => ({
    QUEUED: token.colorTextSecondary,
    RUNNING: token.colorPrimary,
    WAITING_APPROVAL: token.colorWarning,
    TERMINATING: token.colorWarning,
    SUCCEEDED: token.colorSuccess,
    FAILED: token.colorError,
    TIMED_OUT: token.colorError,
    TERMINATED: token.colorTextTertiary,
  })[status], [token]);

  const trendOption = useMemo(() => {
    const trend = data?.trend || [];
    return {
      animationDuration: 320,
      color: [token.colorSuccess, token.colorError, token.colorTextQuaternary, token.colorPrimary],
      grid: { left: 40, right: 18, top: 28, bottom: 34 },
      legend: {
        top: 0,
        right: 0,
        itemWidth: 10,
        itemHeight: 6,
        textStyle: { color: token.colorTextSecondary, fontSize: 11 },
      },
      tooltip: { trigger: 'axis' },
      xAxis: {
        type: 'category',
        data: trend.map((item) => convertToLocalizedTime(item.date.includes('T') ? item.date : `${item.date}T00:00:00`, 'MM-DD')),
        axisLine: { lineStyle: { color: token.colorBorderSecondary } },
        axisTick: { show: false },
        axisLabel: { color: token.colorTextSecondary },
      },
      yAxis: {
        type: 'value',
        minInterval: 1,
        axisLabel: { color: token.colorTextSecondary },
        splitLine: { lineStyle: { color: token.colorBorderSecondary, type: 'dashed' } },
      },
      series: [
        { name: t('workflowOrchestration.dashboard.succeeded', '成功'), type: 'bar', stack: 'outcome', barMaxWidth: 24, data: trend.map((item) => item.succeeded) },
        { name: t('workflowOrchestration.dashboard.failedOrTimedOut', '失败/超时'), type: 'bar', stack: 'outcome', barMaxWidth: 24, data: trend.map((item) => item.failed + item.timed_out) },
        { name: t('workflowOrchestration.dashboard.inProgressOrOther', '进行中/其他'), type: 'bar', stack: 'outcome', barMaxWidth: 24, data: trend.map((item) => item.other) },
        {
          name: t('workflowOrchestration.dashboard.totalExecutions', '总执行'),
          type: 'line',
          smooth: 0.25,
          symbolSize: 6,
          lineStyle: { width: 2 },
          data: trend.map((item) => item.total),
        },
      ],
    };
  }, [convertToLocalizedTime, data?.trend, t, token]);

  const metrics = [
    { label: t('workflowOrchestration.dashboard.publishedWorkflows', '已发布流程'), value: data?.kpis.published_workflows ?? '--', subtitle: t('workflowOrchestration.dashboard.currentOrganization', '当前组织'), icon: <ApartmentOutlined aria-hidden="true" />, href: '/workflow-orchestration/workflows?status=PUBLISHED' },
    { label: t('workflowOrchestration.dashboard.todayExecutions', '今日执行'), value: data?.kpis.today_executions ?? '--', subtitle: t('workflowOrchestration.dashboard.productionExecutions', '正式执行'), icon: <PlayCircleOutlined aria-hidden="true" />, href: '/workflow-orchestration/executions' },
    { label: t('workflowOrchestration.dashboard.successRate7d', '近 7 天成功率'), value: data?.kpis.success_rate == null ? '--' : `${data.kpis.success_rate}%`, subtitle: t('workflowOrchestration.dashboard.excludesIncomplete', '不含取消与未结束'), icon: <CheckCircleOutlined aria-hidden="true" />, valueColor: token.colorSuccess, href: '/workflow-orchestration/executions?status=SUCCEEDED' },
    { label: t('workflowOrchestration.dashboard.currentlyRunning', '当前运行中'), value: data?.kpis.running_executions ?? '--', subtitle: t('workflowOrchestration.dashboard.queuedCount', '排队中 {count}', { count: data?.kpis.queued_executions ?? '--' }), icon: <SyncOutlined aria-hidden="true" />, valueColor: token.colorPrimary, href: '/workflow-orchestration/executions?status=RUNNING' },
    { label: t('workflowOrchestration.dashboard.failed7d', '近 7 天失败'), value: data?.kpis.failed_executions ?? '--', subtitle: t('workflowOrchestration.dashboard.includesTimeout', '包含超时'), icon: <WarningOutlined aria-hidden="true" />, valueColor: token.colorError, href: '/workflow-orchestration/executions?status=FAILED' },
    { label: t('workflowOrchestration.dashboard.myApprovals', '待我审批'), value: data?.kpis.pending_approvals ?? '--', subtitle: t('workflowOrchestration.dashboard.currentUser', '当前用户'), icon: <TeamOutlined aria-hidden="true" />, valueColor: token.colorWarning, href: MY_APPROVALS_HREF },
  ];

  const visibleStatuses = (data?.status_distribution || []).filter((item) => item.count > 0);
  const statusTotal = visibleStatuses.reduce((total, item) => total + item.count, 0);
  const hasTrend = (data?.trend || []).some((item) => item.total > 0);

  const recentColumns: ColumnsType<ExecutionRecord> = [
    {
      title: t('workflowOrchestration.workflow.shortName', '流程'),
      dataIndex: 'workflow_name',
      key: 'workflow_name',
      width: 210,
      ellipsis: true,
      render: (value: string, record) => (
        <div className="flex items-center gap-1 font-medium text-[var(--color-text-1)]">
          <span className="truncate">{value || '--'}</span>
          {record.workflow_deleted ? <Tag className="shrink-0">{t('workflowOrchestration.workflow.deleted', '流程已删除')}</Tag> : null}
        </div>
      ),
    },
    { title: t('common.version', '版本'), dataIndex: 'workflow_version', key: 'workflow_version', width: 72, render: (value: number) => value ? `v${value}` : '--' },
    { title: t('workflowOrchestration.trigger.method', '触发方式'), dataIndex: 'trigger_type', key: 'trigger_type', width: 100, render: (value: WorkflowTriggerType) => triggerLabels[value] || '--' },
    { title: t('workflowOrchestration.execution.startedBy', '发起人'), dataIndex: 'started_by', key: 'started_by', width: 100, render: (value: string) => value || '--' },
    {
      title: t('common.status', '状态'),
      dataIndex: 'status',
      key: 'status',
      width: 125,
      render: (value: ExecutionStatus) => {
        const status = executionStatusPresentation[value];
        return status ? <Tag color={status.color}>{t(`workflowOrchestration.execution.status.${value}`, status.label)}</Tag> : '--';
      },
    },
    { title: t('workflowOrchestration.execution.startedAt', '启动时间'), dataIndex: 'created_at', key: 'created_at', width: 145, render: (value: string) => <span className="text-[var(--color-text-3)]">{value ? convertToLocalizedTime(value, 'MM-DD HH:mm:ss') : '--'}</span> },
    { title: t('workflowOrchestration.execution.duration', '耗时'), dataIndex: 'duration_ms', key: 'duration_ms', width: 90, render: (value: number | null) => <span className="tabular-nums">{formatDuration(value)}</span> },
    { title: t('common.actions', '操作'), key: 'actions', width: 72, fixed: 'right', render: (_, record) => <WorkflowPermission operation="View" area="executions" instancePermissions={record.permission}><Button type="link" size="small" onClick={() => router.push(executionsByWorkflowHref(record.workflow_name))}>{t('common.details', '详情')}</Button></WorkflowPermission> },
  ];

  const quickActions = [
    { title: t('workflowOrchestration.dashboard.runWorkflow', '执行流程'), description: t('workflowOrchestration.dashboard.runWorkflowHint', '选择已发布流程并填写运行输入'), icon: <PlayCircleOutlined aria-hidden="true" />, href: '/workflow-orchestration/workflows?status=PUBLISHED' },
    { title: t('workflowOrchestration.dashboard.viewWorkflows', '查看流程'), description: t('workflowOrchestration.dashboard.viewWorkflowsHint', '查看草稿和已发布的流程'), icon: <FileSearchOutlined aria-hidden="true" />, href: '/workflow-orchestration/workflows' },
    { title: t('workflowOrchestration.dashboard.allExecutions', '全部执行记录'), description: t('workflowOrchestration.dashboard.allExecutionsHint', '查询运行历史与节点详情'), icon: <UnorderedListOutlined aria-hidden="true" />, href: '/workflow-orchestration/executions' },
  ];

  return (
    <main className="h-full space-y-4 overflow-y-auto bg-[var(--color-bg)] p-4">
      <section aria-label={t('workflowOrchestration.dashboard.metrics', '编排运行指标')} className="grid grid-cols-6 gap-3">
        {loading && !data
          ? Array.from({ length: 6 }, (_, index) => (
            <div
              key={`metric-skeleton-${index}`}
              data-testid="dashboard-metric-skeleton"
              className="min-w-0 rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4"
            >
              <Skeleton active avatar={{ shape: 'square', size: 36 }} paragraph={{ rows: 2, width: ['55%', '40%'] }} title={false} />
            </div>
          ))
          : metrics.map((item) => (
            <WorkflowPermission key={item.label} operation="View" area="home" className="block"><button
              type="button"
              className="h-full w-full min-w-0 rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-1)] p-4 text-left transition-colors hover:border-[var(--color-primary)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-primary)]"
              onClick={() => router.push(item.href)}
            >
              <SummaryMetricCard
                framed={false}
                layout="vertical"
                headerSpacing="compact"
                icon={item.icon}
                iconBackground={token.colorFillSecondary}
                iconColor={item.valueColor || token.colorPrimary}
                iconClassName="h-9 w-9"
                label={item.label}
                value={item.value}
                valueColor={item.valueColor}
                subtitle={item.subtitle}
                maxFontSize={28}
              />
            </button></WorkflowPermission>
          ))}
      </section>

      <section data-testid="dashboard-quick-actions-row" aria-label={t('workflowOrchestration.dashboard.quickActions', '快捷操作')}>
        <Card data-testid="dashboard-quick-actions-card" title={<span><PlayCircleOutlined className="mr-2" />{t('workflowOrchestration.dashboard.quickActions', '快捷操作')}</span>} styles={{ body: { padding: 12 } }}>
          <div data-testid="dashboard-quick-actions-grid" className="grid grid-cols-3 divide-x divide-[var(--color-border-1)]">
            {quickActions.map((item) => (
              <WorkflowPermission key={item.title} operation="View" area="home" className="block min-w-0"><button
                type="button"
                className="group flex h-full w-full items-center gap-3 rounded-lg px-3 py-2 text-left hover:bg-[var(--color-fill-1)] focus-visible:outline-2 focus-visible:outline-[var(--color-primary)]"
                onClick={() => router.push(item.href)}
              >
                <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-[var(--color-primary-bg)] text-[var(--color-primary)]">{item.icon}</span>
                <span className="min-w-0 flex-1">
                  <span className="block font-medium text-[var(--color-text-1)]">{item.title}</span>
                  <span className="mt-1 block truncate text-xs leading-5 text-[var(--color-text-3)]">{item.description}</span>
                </span>
                <RightOutlined aria-hidden="true" className="text-xs text-[var(--color-text-4)] group-hover:text-[var(--color-primary)]" />
              </button></WorkflowPermission>
            ))}
          </div>
        </Card>
      </section>

      <section data-testid="dashboard-overview-row" className="grid grid-cols-3 gap-4">
        <Card data-testid="dashboard-trend-card" title={<span><HistoryOutlined className="mr-2" />{t('workflowOrchestration.dashboard.trend7d', '近 7 天执行趋势')}</span>} className="col-span-2 min-w-0" styles={{ body: { padding: 16 } }}>
          {loading && !data ? <Skeleton active paragraph={{ rows: 7 }} /> : hasTrend ? (
            <ReactECharts option={trendOption} className="h-56 w-full" opts={{ renderer: 'svg' }} />
          ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('workflowOrchestration.dashboard.noExecutions7d', '近 7 天暂无正式执行')} />}
        </Card>

        <Card className="min-w-0" title={<span><ClockCircleOutlined className="mr-2" />{t('workflowOrchestration.dashboard.statusDistribution', '执行状态分布')}</span>} extra={<span className="text-xs text-[var(--color-text-3)]">{t('workflowOrchestration.dashboard.last7d', '近 7 天')}</span>} styles={{ body: { padding: 16 } }}>
          {loading && !data ? <Skeleton active paragraph={{ rows: 7 }} /> : visibleStatuses.length ? (
            <div className="space-y-2">
              {visibleStatuses.map((item) => (
                <WorkflowPermission key={item.status} operation="View" area="home" className="block"><button
                  type="button"
                  className="group flex w-full items-center gap-3 rounded-lg px-2 py-2 text-left hover:bg-[var(--color-fill-1)] focus-visible:outline-2 focus-visible:outline-[var(--color-primary)]"
                  onClick={() => router.push(`/workflow-orchestration/executions?status=${item.status}`)}
                >
                  <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: statusColor(item.status) }} />
                  <span className="min-w-0 flex-1 text-sm text-[var(--color-text-2)]">{t(`workflowOrchestration.execution.status.${item.status}`, item.label)}</span>
                  <span className="w-20 overflow-hidden rounded-full bg-[var(--color-fill-2)]">
                    <span className="block h-1.5 rounded-full" style={{ width: `${Math.max(6, item.count * 100 / statusTotal)}%`, background: statusColor(item.status) }} />
                  </span>
                  <span className="w-8 text-right text-sm font-semibold tabular-nums text-[var(--color-text-1)]">{item.count}</span>
                  <RightOutlined aria-hidden="true" className="text-xs text-[var(--color-text-4)] group-hover:text-[var(--color-primary)]" />
                </button></WorkflowPermission>
              ))}
            </div>
          ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('workflowOrchestration.dashboard.noStatus7d', '近 7 天暂无状态数据')} />}
        </Card>
      </section>

      <section data-testid="dashboard-detail-row" className="grid h-[328px] grid-cols-3 items-stretch gap-4">
        <Card data-testid="dashboard-recent-card" title={<span><UnorderedListOutlined className="mr-2" />{t('workflowOrchestration.dashboard.recentExecutions', '最近执行')}</span>} extra={<WorkflowPermission operation="View" area="home"><Button type="link" size="small" onClick={() => router.push('/workflow-orchestration/executions')}>{t('common.viewAll', '查看全部')}</Button></WorkflowPermission>} className="col-span-2 flex h-full min-w-0 flex-col" styles={{ body: { flex: 1, minHeight: 0, overflow: 'hidden', padding: 12 } }}>
          <CustomTable<ExecutionRecord>
            rowKey="id"
            size="small"
            loading={loading && !data}
            columns={recentColumns}
            dataSource={data?.recent_executions || []}
            pagination={false}
            scroll={{ x: 940, y: DASHBOARD_RECENT_TABLE_SCROLL_Y }}
            locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('workflowOrchestration.dashboard.noOrganizationExecutions', '当前组织暂无正式执行')} /> }}
          />
        </Card>

        <Card data-testid="dashboard-pending-card" title={<span><TeamOutlined className="mr-2" />{t('workflowOrchestration.dashboard.myPendingApprovals', '我的待审批')}</span>} extra={<Badge count={data?.kpis.pending_approvals || 0} showZero />} className="flex h-full min-w-0 flex-col" styles={{ body: { flex: 1, minHeight: 0, overflow: 'hidden', padding: 16 } }}>
          {loading && !data ? <Skeleton active /> : data?.pending_approvals.length ? (
            <div data-testid="dashboard-pending-list" className="h-full overflow-y-auto pr-1 divide-y divide-[var(--color-border-1)]">
              {data.pending_approvals.map((approval) => <ApprovalItem key={approval.id} approval={approval} />)}
            </div>
          ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('workflowOrchestration.dashboard.noPendingApprovals', '暂无待处理审批')} />}
        </Card>
      </section>

    </main>
  );
}
