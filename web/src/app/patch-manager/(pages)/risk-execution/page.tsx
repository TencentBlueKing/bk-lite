'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Button,
  Dropdown,
  Empty,
  Input,
  message,
  Modal,
  Select,
  Space,
  Spin,
  Tag,
} from 'antd';
import { DownOutlined, ExportOutlined, ReloadOutlined } from '@ant-design/icons';
import ExcelJS from 'exceljs';

import CustomTable from '@/components/custom-table';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import PermissionWrapper from '@/components/permission';
import OperateDrawer from '@/app/patch-manager/components/operate-drawer';
import usePatchManagerApi from '@/app/patch-manager/api';
import { createListRequestCoordinator } from '@/app/patch-manager/utils/list-request-coordinator';
import { PATCH_MANAGER_POLL_INTERVAL_MS } from '@/app/patch-manager/constants/polling';
import useApiClient from '@/utils/request';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { useTranslation } from '@/utils/i18n';

import {
  createExecutionListPolling,
  type ExecutionListQuery,
} from './execution-list-polling';

interface TaskRow {
  key: string;
  id: number;
  name: string;
  type: string;
  taskType: 'install' | 'reboot';
  exec: string;
  status: string;
  statusColor: string;
  createdAt: string;
  canCancel: boolean;
  canRetry: boolean;
  raw: any;
}

interface RiskSummary {
  id: string;
  display_name: string;
  host_id: number;
  patch_id: number;
  status: string;
  status_display: string;
  status_color: string;
  host_name?: string;
  host_ip?: string;
  patch_name?: string;
  can_retry?: boolean;
}

const STATUS_COLOR: Record<string, string> = {
  waiting: 'default',
  pending: 'default',
  running: 'processing',
  pending_reboot: 'warning',
  completed: 'success',
  partial_success: 'warning',
  partial_cancelled: 'warning',
  failed: 'error',
  cancelled: 'default',
  skipped: 'default',
  unknown: 'warning',
};

const STEP_BORDER: Record<string, string> = {
  completed: '#52c41a',
  running: '#1677ff',
  failed: '#ff4d4f',
  pending_reboot: '#faad14',
  waiting: '#d9d9d9',
  skipped: '#bfbfbf',
  cancelled: '#bfbfbf',
  unknown: '#faad14',
};

const ACTIVE_RECORD_STATUSES = new Set(['waiting', 'running']);

function executionText(task: any, formatTime: (value: string) => string, translate: (key: string) => string) {
  if (task.execution_mode !== 'window') return translate('patchManager.risk.executeNow');
  const start = task.execution_window_start ? formatTime(task.execution_window_start) : '—';
  const end = task.execution_window_end ? formatTime(task.execution_window_end) : '—';
  return `${translate('patchManager.risk.executionWindow')} ${start}–${end}`;
}

async function exportTasks(
  rows: TaskRow[],
  filename: string,
  loadRiskRows: (taskId: number) => Promise<any[]>,
  formatTime: (value?: string | null) => string,
  translate: (key: string) => string,
) {
  const workbook = new ExcelJS.Workbook();
  const sheet = workbook.addWorksheet(translate('patchManager.execution.records'));
  sheet.columns = [
    ...translate('patchManager.execution.exportHeaders').split('|').map((header, index) => ({ header, key: ['name', 'type', 'exec', 'createdAt', 'host', 'patch', 'installStatus', 'installTime', 'rebootStatus', 'rebootTime', 'verifyStatus', 'verifyTime', 'status', 'reason', 'retryCount'][index], width: index === 0 ? 36 : [2, 7, 9, 11].includes(index) ? 36 : index === 13 ? 40 : 14 })),
  ];
  sheet.views = [{ state: 'frozen', ySplit: 1 }];
  for (const row of rows) {
    const riskRows = await loadRiskRows(row.id);
    riskRows.forEach((risk) => {
      const stepMap: Record<string, any> = Object.fromEntries(
        (risk.steps || []).map((step: any) => [step.key, step]),
      );
      const attemptTime = (step: any) => {
        const attempt = step?.attempts?.[step.attempts.length - 1];
        if (!attempt) return '—';
        return `${formatTime(attempt.started_at)}${attempt.finished_at ? ` ～ ${formatTime(attempt.finished_at)}` : ''}`;
      };
      const attempts = (risk.steps || []).flatMap((step: any) => step.attempts || []);
      sheet.addRow({
        ...row,
        host: risk.host_name || risk.host_id,
        patch: risk.patch_name || risk.patch_id,
        installStatus: stepMap.install ? translate(`patchManager.execution.statuses.${stepMap.install.status}`) : '—',
        installTime: attemptTime(stepMap.install),
        rebootStatus: stepMap.reboot ? translate(`patchManager.execution.statuses.${stepMap.reboot.status}`) : '—',
        rebootTime: attemptTime(stepMap.reboot),
        verifyStatus: stepMap.verify ? translate(`patchManager.execution.statuses.${stepMap.verify.status}`) : '—',
        verifyTime: attemptTime(stepMap.verify),
        status: translate(`patchManager.execution.statuses.${risk.status}`),
        reason: attempts.map((attempt: any) => attempt.reason).filter(Boolean).at(-1) || '',
        retryCount: Math.max(0, attempts.length - (risk.steps || []).filter((step: any) => step.attempts?.length).length),
      });
    });
  }
  const buffer = await workbook.xlsx.writeBuffer();
  const blob = new Blob([buffer], {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(link.href);
}

export default function RiskExecutionPage() {
  const { t } = useTranslation();
  const api = usePatchManagerApi();
  const { isLoading } = useApiClient();
  const { convertToLocalizedTime } = useLocalizedTime();
  const apiRef = useRef(api);
  apiRef.current = api;
  const localizedTimeRef = useRef(convertToLocalizedTime);
  localizedTimeRef.current = convertToLocalizedTime;
  const [tasks, setTasks] = useState<TaskRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedTasks, setSelectedTasks] = useState<React.Key[]>([]);
  const [taskSearch, setTaskSearch] = useState('');
  const [appliedTaskSearch, setAppliedTaskSearch] = useState('');
  const [taskType, setTaskType] = useState<ExecutionListQuery['taskType']>();
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20, total: 0 });
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [detailTask, setDetailTask] = useState<any>();
  const [taskDetailLoading, setTaskDetailLoading] = useState(false);
  const [riskDetailLoading, setRiskDetailLoading] = useState(false);
  const detailLoading = taskDetailLoading || riskDetailLoading;
  const [detailTransitionLoading, setDetailTransitionLoading] = useState(false);
  const [detailReloadVersion, setDetailReloadVersion] = useState(0);
  const [riskSearch, setRiskSearch] = useState('');
  const [selectedRiskId, setSelectedRiskId] = useState<string>();
  const [riskDetail, setRiskDetail] = useState<any>();
  const [cancelTask, setCancelTask] = useState<TaskRow>();
  const [cancelReason, setCancelReason] = useState('');
  const [cancelSubmitting, setCancelSubmitting] = useState(false);
  const [exporting, setExporting] = useState(false);
  const listRequestCoordinatorRef = useRef(createListRequestCoordinator(setLoading));
  const listPollingRef = useRef<ReturnType<typeof createExecutionListPolling> | undefined>(undefined);
  const listQueryRef = useRef<ExecutionListQuery>({
    page: pagination.current,
    pageSize: pagination.pageSize,
    search: appliedTaskSearch,
    taskType: taskType as ExecutionListQuery['taskType'],
  });
  listQueryRef.current = {
    page: pagination.current,
    pageSize: pagination.pageSize,
    search: appliedTaskSearch,
    taskType: taskType as ExecutionListQuery['taskType'],
  };
  const taskDetailRequestCoordinatorRef = useRef(createListRequestCoordinator(setTaskDetailLoading));
  const riskDetailRequestCoordinatorRef = useRef(createListRequestCoordinator(setRiskDetailLoading));
  const initialDetailSelectionRef = useRef(false);
  const detailLoadGenerationRef = useRef(0);
  const detailPollingGenerationRef = useRef(0);
  const detailPollingTimerRef = useRef<number | undefined>(undefined);

  const stopDetailPolling = useCallback(() => {
    detailPollingGenerationRef.current += 1;
    if (detailPollingTimerRef.current !== undefined) {
      window.clearInterval(detailPollingTimerRef.current);
      detailPollingTimerRef.current = undefined;
    }
  }, []);

  const formatDateTime = useCallback((value?: string | null) => (
    value ? localizedTimeRef.current(value) : '—'
  ), []);

  const mapTaskRows = useCallback((items: any[]): TaskRow[] => (
    (items || []).map((task: any): TaskRow => ({
      key: String(task.id),
      id: task.id,
      name: task.name,
      type: t(`patchManager.execution.taskTypes.${task.task_type}`, task.task_type),
      taskType: task.task_type,
      exec: executionText(task, formatDateTime, t),
      status: t(`patchManager.execution.statuses.${task.record_status || task.status}`, task.record_status_display || task.status_display || task.status),
      statusColor: task.record_status_color || STATUS_COLOR[task.record_status || task.status] || 'default',
      createdAt: formatDateTime(task.created_at),
      canCancel: Boolean(task.can_cancel),
      canRetry: Boolean(task.can_retry),
      raw: task,
    }))
  ), [formatDateTime, t]);

  const loadTasks = useCallback(async (
    query: ExecutionListQuery,
    silent = false,
  ) => {
    const coordinator = listRequestCoordinatorRef.current;
    if (!coordinator.canStart({ visible: !silent })) return;
    const ticket = coordinator.begin({ visible: !silent });
    if (!ticket) return;
    try {
      const response = await apiRef.current.getGovernanceTaskList(
        {
          page: query.page,
          page_size: query.pageSize,
          search: query.search || undefined,
          task_type: query.taskType,
        },
        { signal: ticket.signal },
      );
      if (!coordinator.shouldApply(ticket)) return;
      const rows = mapTaskRows(response.items || []);
      setTasks(rows);
      setPagination({
        current: query.page,
        pageSize: query.pageSize,
        total: response.count || 0,
      });
    } catch (error) {
      if (!ticket.signal.aborted) throw error;
    } finally {
      coordinator.finish(ticket);
    }
  }, [mapTaskRows]);

  useEffect(() => {
    if (isLoading) return undefined;
    const polling = createExecutionListPolling((query, silent) => {
      if (silent && document.hidden) return;
      return loadTasks(query, silent);
    });
    listPollingRef.current = polling;
    polling.restart(listQueryRef.current);
    return () => {
      polling.stop();
      if (listPollingRef.current === polling) listPollingRef.current = undefined;
    };
  }, [isLoading, loadTasks]);

  const loadTaskDetail = useCallback(async (taskId: number, silent = false, applyResult = true) => {
    const coordinator = taskDetailRequestCoordinatorRef.current;
    if (!coordinator.canStart({ visible: !silent })) return;
    const ticket = coordinator.begin({ visible: !silent });
    if (!ticket) return;
    try {
      const result = await apiRef.current.getGovernanceTaskDetail(taskId, { signal: ticket.signal });
      if (!coordinator.shouldApply(ticket)) return;
      if (applyResult) {
        setDetailTask(result);
        setSelectedRiskId((current) => current || result.risk_items?.[0]?.id);
      }
      return result;
    } catch (error) {
      if (!ticket.signal.aborted) throw error;
    } finally {
      coordinator.finish(ticket);
    }
  }, []);

  const loadSelectedRisk = useCallback(async (taskId: number, riskId: string, silent = false, applyResult = true) => {
    const coordinator = riskDetailRequestCoordinatorRef.current;
    if (!coordinator.canStart({ visible: !silent })) return;
    const ticket = coordinator.begin({ visible: !silent });
    if (!ticket) return;
    try {
      const result = await apiRef.current.getGovernanceRiskItemDetail(taskId, riskId, { signal: ticket.signal });
      if (!coordinator.shouldApply(ticket)) return;
      if (applyResult) setRiskDetail(result);
      return result;
    } catch (error: any) {
      if (!ticket.signal.aborted && error?.code !== 'ERR_CANCELED') throw error;
    } finally {
      coordinator.finish(ticket);
    }
  }, []);

  useEffect(() => {
    if (!drawerOpen || !detailTask?.id || !selectedRiskId) return;
    const taskId = detailTask.id;
    const riskId = selectedRiskId;
    const generation = ++detailLoadGenerationRef.current;
    const initialSelection = initialDetailSelectionRef.current;
    initialDetailSelectionRef.current = false;

    setDetailTransitionLoading(true);
    const refreshDetail = async () => {
      try {
        if (initialSelection) {
          const [riskResponse] = await Promise.allSettled([
            loadSelectedRisk(taskId, riskId, false, false),
          ]);
          if (
            generation === detailLoadGenerationRef.current
            && riskResponse.status === 'fulfilled'
            && riskResponse.value
          ) {
            setRiskDetail(riskResponse.value);
          }
          return;
        }

        const [taskResponse, riskResponse] = await Promise.allSettled([
          loadTaskDetail(taskId, false, false),
          loadSelectedRisk(taskId, riskId, false, false),
        ]);
        if (generation !== detailLoadGenerationRef.current) return;
        if (
          taskResponse.status === 'fulfilled'
          && taskResponse.value
          && riskResponse.status === 'fulfilled'
          && riskResponse.value
        ) {
          setDetailTask(taskResponse.value);
          setRiskDetail(riskResponse.value);
        }
      } finally {
        if (generation === detailLoadGenerationRef.current) {
          setDetailTransitionLoading(false);
        }
      }
    };
    void refreshDetail();

    return () => {
      if (generation === detailLoadGenerationRef.current) {
        detailLoadGenerationRef.current += 1;
      }
      taskDetailRequestCoordinatorRef.current.invalidate();
      riskDetailRequestCoordinatorRef.current.invalidate();
    };
  }, [detailReloadVersion, detailTask?.id, drawerOpen, loadSelectedRisk, loadTaskDetail, selectedRiskId]);

  useEffect(() => {
    stopDetailPolling();
    if (
      !drawerOpen
      || !detailTask?.id
      || !selectedRiskId
      || detailTransitionLoading
      || detailLoading
      || !riskDetail
      || String(riskDetail.id) !== String(selectedRiskId)
      || !ACTIVE_RECORD_STATUSES.has(detailTask.record_status)
    ) return;

    const generation = detailPollingGenerationRef.current;
    let polling = false;
    const poll = async () => {
      if (polling || generation !== detailPollingGenerationRef.current) return;
      polling = true;
      try {
        const [taskResponse, riskResponse] = await Promise.allSettled([
          loadTaskDetail(detailTask.id, true, false),
          loadSelectedRisk(detailTask.id, selectedRiskId, true, false),
        ]);
        if (generation !== detailPollingGenerationRef.current) return;
        if (
          taskResponse.status === 'fulfilled'
          && taskResponse.value
          && riskResponse.status === 'fulfilled'
          && riskResponse.value
        ) {
          setDetailTask(taskResponse.value);
          setRiskDetail(riskResponse.value);
        }
      } finally {
        polling = false;
      }
    };
    detailPollingTimerRef.current = window.setInterval(() => {
      void poll();
    }, PATCH_MANAGER_POLL_INTERVAL_MS);
    return stopDetailPolling;
  }, [detailLoading, detailTask?.id, detailTask?.record_status, detailTransitionLoading, drawerOpen, loadSelectedRisk, loadTaskDetail, riskDetail, selectedRiskId, stopDetailPolling]);

  useEffect(() => () => {
    stopDetailPolling();
    listRequestCoordinatorRef.current.invalidate();
    taskDetailRequestCoordinatorRef.current.invalidate();
    riskDetailRequestCoordinatorRef.current.invalidate();
  }, [stopDetailPolling]);

  const openDetail = async (taskId: number) => {
    const openingDrawer = !drawerOpen;
    stopDetailPolling();
    detailLoadGenerationRef.current += 1;
    taskDetailRequestCoordinatorRef.current.invalidate();
    riskDetailRequestCoordinatorRef.current.invalidate();
    setDrawerOpen(true);
    if (openingDrawer) {
      setDetailTask(undefined);
      setSelectedRiskId(undefined);
    }
    setRiskDetail(undefined);
    setDetailTransitionLoading(true);
    setRiskSearch('');
    initialDetailSelectionRef.current = true;
    const result = await loadTaskDetail(taskId, false, false);
    if (!result) {
      setDetailTransitionLoading(false);
      return;
    }
    setDetailTask(result);
    setSelectedRiskId(result.risk_items?.[0]?.id);
    if (!result.risk_items?.[0]?.id) setDetailTransitionLoading(false);
  };

  const handleSelectRisk = (riskId: string) => {
    if (riskId === selectedRiskId) return;
    stopDetailPolling();
    detailLoadGenerationRef.current += 1;
    taskDetailRequestCoordinatorRef.current.invalidate();
    riskDetailRequestCoordinatorRef.current.invalidate();
    setDetailTransitionLoading(true);
    setRiskDetail(undefined);
    setSelectedRiskId(riskId);
  };

  const handleRefreshDetail = () => {
    if (!detailTask?.id || !selectedRiskId) return;
    stopDetailPolling();
    detailLoadGenerationRef.current += 1;
    taskDetailRequestCoordinatorRef.current.invalidate();
    riskDetailRequestCoordinatorRef.current.invalidate();
    setDetailTransitionLoading(true);
    setRiskDetail(undefined);
    setDetailReloadVersion((current) => current + 1);
  };

  const filteredRiskItems = useMemo(() => {
    const keyword = riskSearch.trim().toLowerCase();
    const items: RiskSummary[] = detailTask?.risk_items || [];
    return keyword ? items.filter((item) => (
      [item.host_name, item.patch_name, item.host_ip]
        .filter(Boolean)
        .join(' ')
        .toLowerCase()
        .includes(keyword)
    )) : items;
  }, [detailTask?.risk_items, riskSearch]);

  const handleRetry = async () => {
    if (!detailTask?.id || !riskDetail?.id) return;
    await api.retryGovernanceTaskHost(detailTask.id, riskDetail.id);
    message.success(t('patchManager.execution.retryStarted'));
    await loadTaskDetail(detailTask.id);
  };

  const handleCancel = async () => {
    if (!cancelTask || !cancelReason.trim()) return;
    setCancelSubmitting(true);
    try {
      const result = await api.cancelGovernanceTask(cancelTask.id, cancelReason.trim());
      message.success(result?.detail || t('patchManager.execution.cancelHandled'));
      setCancelTask(undefined);
      setCancelReason('');
      await loadTasks({
        page: pagination.current,
        pageSize: pagination.pageSize,
        search: appliedTaskSearch,
        taskType: taskType as ExecutionListQuery['taskType'],
      });
    } finally {
      setCancelSubmitting(false);
    }
  };

  const loadExportRiskRows = async (taskId: number) => {
    const task = await api.getGovernanceTaskDetail(taskId);
    return Promise.all(
      (task.risk_items || []).map((risk: RiskSummary) => (
        api.getGovernanceRiskItemDetail(taskId, risk.id)
      )),
    );
  };

  const handleExport = async (selectedOnly: boolean) => {
    setExporting(true);
    try {
      let rows: TaskRow[];
      if (selectedOnly) {
        rows = tasks.filter((row) => selectedTasks.includes(row.key));
      } else {
        const response = await api.getGovernanceTaskList({
          page: 1,
          page_size: 10000,
          search: appliedTaskSearch || undefined,
          task_type: taskType as 'install' | 'reboot' | undefined,
        });
        rows = mapTaskRows(response.items || []);
      }
      await exportTasks(
        rows,
        selectedOnly
          ? `${t('patchManager.execution.records')}_${t('patchManager.risk.selected')}_${new Date().toISOString().slice(0, 10)}.xlsx`
          : `${t('patchManager.execution.records')}_${new Date().toISOString().slice(0, 10)}.xlsx`,
        loadExportRiskRows,
        formatDateTime,
        t,
      );
    } finally {
      setExporting(false);
    }
  };

  const columns = [
    { title: t('patchManager.execution.taskName'), dataIndex: 'name' },
    { title: t('patchManager.execution.type'), dataIndex: 'type', width: 90, render: (value: string) => <Tag>{value}</Tag> },
    { title: t('patchManager.risk.executionMode'), dataIndex: 'exec', width: 230 },
    { title: t('patchManager.execution.status'), dataIndex: 'status', width: 120, render: (_: unknown, row: TaskRow) => <Tag color={row.statusColor}>{row.status}</Tag> },
    { title: t('patchManager.createTime'), dataIndex: 'createdAt', width: 180 },
    {
      title: t('patchManager.operation'),
      width: 150,
      render: (_: unknown, row: TaskRow) => <Space size={12}>
        <Button type="link" size="small" onClick={() => openDetail(row.id)}>{t('patchManager.risk.details')}</Button>
        {row.canCancel && <PermissionWrapper requiredPermissions={['Edit']}><Button type="link" size="small" danger onClick={() => setCancelTask(row)}>{t('patchManager.cancel')}</Button></PermissionWrapper>}
      </Space>,
    },
  ];

  return <div style={{ background: 'var(--color-bg-1, #fff)', border: '1px solid var(--color-border-1, #e8e8e8)', borderRadius: 10, padding: 16, flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 14 }}>
      <Space>
        <Input.Search placeholder={t('patchManager.execution.taskName')} value={taskSearch} onChange={(event) => setTaskSearch(event.target.value)} onSearch={(value) => {
          setAppliedTaskSearch(value);
          setPagination((current) => ({ ...current, current: 1 }));
          listPollingRef.current?.restart({
            page: 1,
            pageSize: pagination.pageSize,
            search: value,
            taskType: taskType as ExecutionListQuery['taskType'],
          });
        }} style={{ width: 220 }} />
        <Select allowClear placeholder={t('patchManager.execution.taskType')} value={taskType} style={{ width: 130 }} options={[{ label: t('patchManager.risk.remediate'), value: 'install' }, { label: t('patchManager.risk.reboot'), value: 'reboot' }]} onChange={(value) => {
          setTaskType(value);
          setPagination((current) => ({ ...current, current: 1 }));
          listPollingRef.current?.restart({
            page: 1,
            pageSize: pagination.pageSize,
            search: appliedTaskSearch,
            taskType: value,
          });
        }} />
      </Space>
      <Space>
        <Button loading={exporting} icon={<ExportOutlined />} onClick={() => handleExport(false)}>{t('patchManager.risk.exportAll')}</Button>
        <Dropdown disabled={!selectedTasks.length || exporting} menu={{ items: [{ key: 'export', label: t('patchManager.risk.exportSelected'), icon: <ExportOutlined />, onClick: () => handleExport(true) }] }}>
          <Button type="primary">{t('patchManager.risk.batchActions')}{selectedTasks.length ? `(${selectedTasks.length})` : ''} <DownOutlined /></Button>
        </Dropdown>
      </Space>
    </div>
    <div style={{ flex: 1, minHeight: 0 }}>
      <CustomTable<TaskRow>
        loading={loading}
        rowKey="key"
        rowSelection={{ selectedRowKeys: selectedTasks, onChange: setSelectedTasks }}
        columns={columns}
        dataSource={tasks}
        pagination={{
          current: pagination.current,
          pageSize: pagination.pageSize,
          total: pagination.total,
          showSizeChanger: true,
          showTotal: (total) => t('patchManager.common.totalItems', undefined, { count: total }),
          onChange: (page, pageSize) => {
            setPagination((current) => ({
              ...current,
              current: page,
              pageSize,
            }));
            listPollingRef.current?.restart({
              page,
              pageSize,
              search: appliedTaskSearch,
              taskType: taskType as ExecutionListQuery['taskType'],
            });
          },
        }}
      />
    </div>

    <OperateDrawer
      title={detailTask?.name || t('patchManager.execution.details')}
      subTitle={detailTask ? <Tag color={detailTask.record_status_color || STATUS_COLOR[detailTask.record_status]}>{t(`patchManager.execution.statuses.${detailTask.record_status}`, detailTask.record_status_display)}</Tag> : null}
      extra={<Button type="link" icon={<ReloadOutlined />} onClick={handleRefreshDetail}>{t('patchManager.refresh')}</Button>}
      open={drawerOpen}
      onClose={() => {
        stopDetailPolling();
        detailLoadGenerationRef.current += 1;
        setDrawerOpen(false);
        setDetailTransitionLoading(false);
        taskDetailRequestCoordinatorRef.current.invalidate();
        riskDetailRequestCoordinatorRef.current.invalidate();
      }}
      width={980}
      bodyStyle={{ padding: 0, display: 'flex', overflow: 'hidden' }}
    >
      {detailLoading && !detailTask ? <Spin style={{ margin: 'auto' }} /> : <>
        <div style={{ width: 310, borderRight: '1px solid var(--color-border-1, #e8e8e8)', padding: 12, overflow: 'auto' }}>
          <Input.Search placeholder={t('patchManager.execution.riskSearch')} value={riskSearch} onChange={(event) => setRiskSearch(event.target.value)} style={{ marginBottom: 12 }} />
          {filteredRiskItems.length ? filteredRiskItems.map((item) => {
            const selected = item.id === selectedRiskId;
            return <div key={item.id} onClick={() => handleSelectRisk(item.id)} style={{ padding: '10px 12px', marginBottom: 8, cursor: 'pointer', borderRadius: 7, border: '1px solid var(--color-border-1, #e8e8e8)', borderLeft: `3px solid ${STEP_BORDER[item.status] || '#d9d9d9'}`, background: selected ? 'var(--color-fill-1, #f4f6f9)' : 'var(--color-bg-1, #fff)' }}>
              <EllipsisWithTooltip
                className="overflow-hidden text-ellipsis whitespace-nowrap font-medium"
                text={`${item.host_name || ''}-${item.patch_name || t('patchManager.risk.patch')}`}
              />
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 6, minWidth: 0 }}>
                <Tag color={item.status_color} style={{ marginInlineEnd: 0, flexShrink: 0 }}>{t(`patchManager.execution.statuses.${item.status}`, item.status_display)}</Tag>
                <EllipsisWithTooltip
                  className="min-w-0 flex-1 overflow-hidden text-ellipsis whitespace-nowrap text-(--color-text-3)"
                  text={item.host_ip || '—'}
                />
              </div>
            </div>;
          }) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={t('patchManager.execution.noMatchingRisk')} />}
        </div>
        <div style={{ flex: 1, padding: '16px 20px', overflow: 'auto' }}>
          {riskDetail?.id ? <>
            {detailTask?.cancelled_at && <Alert
              type="info"
              showIcon
              message={t('patchManager.execution.cancelInfo')}
              description={<Space direction="vertical" size={2}>
                <span>{t('patchManager.execution.cancelledBy')}：{detailTask.cancelled_by || '—'}</span>
                <span>{t('patchManager.execution.cancelledAt')}：{formatDateTime(detailTask.cancelled_at)}</span>
                <span>{t('patchManager.execution.cancelReason')}：{detailTask.cancel_reason || '—'}</span>
              </Space>}
              style={{ marginBottom: 16 }}
            />}
            {riskDetail.source_record && <Alert
              type="info"
              showIcon
              message={<Space>{t('patchManager.execution.sourceRecord')}：<Button type="link" size="small" style={{ paddingInline: 0 }} onClick={() => openDetail(riskDetail.source_record.id)}>{riskDetail.source_record.name} (#{riskDetail.source_record.id})</Button></Space>}
              style={{ marginBottom: 16 }}
            />}
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
              <div>
                <div style={{ fontSize: 16, fontWeight: 600 }}>{riskDetail.display_name}</div>
                <div style={{ color: 'var(--color-text-3, #8c8c8c)', marginTop: 4 }}>{riskDetail.host_ip || '—'} · {riskDetail.baseline_name || '—'}</div>
              </div>
              {riskDetail.can_retry && <PermissionWrapper requiredPermissions={['Edit']}><Button type="link" size="small" onClick={handleRetry}>{t('patchManager.execution.retry')}</Button></PermissionWrapper>}
            </div>
            {(riskDetail.steps || []).map((step: any, stepIndex: number) => <div key={step.key} style={{ position: 'relative', paddingLeft: 28, paddingBottom: stepIndex === riskDetail.steps.length - 1 ? 0 : 18 }}>
              {stepIndex < riskDetail.steps.length - 1 && <div style={{ position: 'absolute', left: 9, top: 20, bottom: -2, width: 2, background: STEP_BORDER[step.status] || '#d9d9d9' }} />}
              <div style={{ position: 'absolute', left: 0, top: 2, width: 20, height: 20, borderRadius: '50%', background: STEP_BORDER[step.status] || '#d9d9d9', color: '#fff', textAlign: 'center', lineHeight: '20px', fontSize: 12 }}>{stepIndex + 1}</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}><strong>{t(`patchManager.execution.steps.${step.key}`, step.name)}</strong><Tag color={step.status_color}>{t(`patchManager.execution.statuses.${step.status}`, step.status_display)}</Tag></div>
              <div style={{ display: 'grid', gap: 8 }}>
                {(step.attempts?.length ? step.attempts : [{ id: `${step.key}-empty`, status: step.status, status_display: step.status_display, status_color: step.status_color, reason: step.reason, log: '' }]).map((attempt: any, attemptIndex: number) => {
                  return <div key={attempt.id} style={{ borderLeft: `3px solid ${STEP_BORDER[attempt.status] || '#d9d9d9'}`, background: 'var(--color-fill-1, #f4f6f9)', borderRadius: 6, padding: '10px 12px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                      <span>{step.attempts?.length > 1 ? t('patchManager.execution.attempt', undefined, { count: attemptIndex + 1 }) : t(`patchManager.execution.steps.${step.key}`, step.name)}</span>
                      <span style={{ color: 'var(--color-text-3, #8c8c8c)' }}>{formatDateTime(attempt.started_at)}{attempt.finished_at ? ` ～ ${formatDateTime(attempt.finished_at)}` : ''}</span>
                    </div>
                    {attempt.reason && <Alert
                      type={attempt.status === 'failed' ? 'error' : 'info'}
                      showIcon={false}
                      message={<span style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{attempt.reason}</span>}
                      style={{ marginTop: 8 }}
                    />}
                  </div>;
                })}
              </div>
            </div>)}
          </> : <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Spin spinning={detailTransitionLoading || detailLoading}>
              <Empty description={t('patchManager.noData')} />
            </Spin>
          </div>}
        </div>
      </>}
    </OperateDrawer>

    <Modal title={t('patchManager.execution.cancelTask', undefined, { name: cancelTask ? `：${cancelTask.name}` : '' })} open={Boolean(cancelTask)} okText={t('patchManager.confirm')} cancelText={t('patchManager.cancel')} okButtonProps={{ danger: true, disabled: !cancelReason.trim() }} confirmLoading={cancelSubmitting} onOk={handleCancel} onCancel={() => { if (!cancelSubmitting) { setCancelTask(undefined); setCancelReason(''); } }} destroyOnClose>
      <Alert type="warning" showIcon message={t('patchManager.execution.cancelWaitingOnly')} description={t('patchManager.execution.cancelHelp')} style={{ marginBottom: 16 }} />
      <div style={{ marginBottom: 8 }}>{t('patchManager.execution.cancelReason')}</div>
      <Input.TextArea value={cancelReason} onChange={(event) => setCancelReason(event.target.value)} placeholder={t('patchManager.execution.cancelReasonPlaceholder')} maxLength={500} autoSize={{ minRows: 3, maxRows: 6 }} />
    </Modal>
  </div>;
}
