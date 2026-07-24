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
  Tooltip,
} from 'antd';
import { DownOutlined, ExportOutlined, ReloadOutlined } from '@ant-design/icons';
import ExcelJS from 'exceljs';

import CustomTable from '@/components/custom-table';
import PermissionWrapper from '@/components/permission';
import OperateDrawer from '@/app/patch-manager/components/operate-drawer';
import usePatchManagerApi from '@/app/patch-manager/api';
import useApiClient from '@/utils/request';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';

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

function executionText(task: any, formatTime: (value: string) => string) {
  if (task.execution_mode !== 'window') return '立即执行';
  const start = task.execution_window_start ? formatTime(task.execution_window_start) : '—';
  const end = task.execution_window_end ? formatTime(task.execution_window_end) : '—';
  return `执行窗口 ${start}–${end}`;
}

async function exportTasks(
  rows: TaskRow[],
  filename: string,
  loadRiskRows: (taskId: number) => Promise<any[]>,
  formatTime: (value?: string | null) => string,
) {
  const workbook = new ExcelJS.Workbook();
  const sheet = workbook.addWorksheet('执行记录');
  sheet.columns = [
    { header: '任务名称', key: 'name', width: 36 },
    { header: '类型', key: 'type', width: 12 },
    { header: '执行方式', key: 'exec', width: 28 },
    { header: '创建时间', key: 'createdAt', width: 24 },
    { header: '主机', key: 'host', width: 22 },
    { header: '补丁', key: 'patch', width: 28 },
    { header: '安装状态', key: 'installStatus', width: 14 },
    { header: '安装时间', key: 'installTime', width: 36 },
    { header: '重启状态', key: 'rebootStatus', width: 14 },
    { header: '重启时间', key: 'rebootTime', width: 36 },
    { header: '验证状态', key: 'verifyStatus', width: 14 },
    { header: '验证时间', key: 'verifyTime', width: 36 },
    { header: '最终结果', key: 'status', width: 14 },
    { header: '原因', key: 'reason', width: 40 },
    { header: '重试次数', key: 'retryCount', width: 12 },
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
        installStatus: stepMap.install?.status_display || '—',
        installTime: attemptTime(stepMap.install),
        rebootStatus: stepMap.reboot?.status_display || '—',
        rebootTime: attemptTime(stepMap.reboot),
        verifyStatus: stepMap.verify?.status_display || '—',
        verifyTime: attemptTime(stepMap.verify),
        status: risk.status_display,
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
  const [taskType, setTaskType] = useState<string>();
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20, total: 0 });
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [detailTask, setDetailTask] = useState<any>();
  const [detailLoading, setDetailLoading] = useState(false);
  const [riskSearch, setRiskSearch] = useState('');
  const [selectedRiskId, setSelectedRiskId] = useState<string>();
  const [riskDetail, setRiskDetail] = useState<any>();
  const [cancelTask, setCancelTask] = useState<TaskRow>();
  const [cancelReason, setCancelReason] = useState('');
  const [cancelSubmitting, setCancelSubmitting] = useState(false);
  const [exporting, setExporting] = useState(false);
  const listRequestSeq = useRef(0);
  const detailRequestSeq = useRef(0);
  const selectedRequestSeq = useRef(0);
  const selectedAbortRef = useRef<AbortController | null>(null);

  const formatDateTime = useCallback((value?: string | null) => (
    value ? localizedTimeRef.current(value) : '—'
  ), []);

  const mapTaskRows = useCallback((items: any[]): TaskRow[] => (
    (items || []).map((task: any): TaskRow => ({
      key: String(task.id),
      id: task.id,
      name: task.name,
      type: task.task_type_display || task.task_type,
      taskType: task.task_type,
      exec: executionText(task, formatDateTime),
      status: task.record_status_display || task.status_display || task.status,
      statusColor: task.record_status_color || STATUS_COLOR[task.record_status || task.status] || 'default',
      createdAt: formatDateTime(task.created_at),
      canCancel: Boolean(task.can_cancel),
      canRetry: Boolean(task.can_retry),
      raw: task,
    }))
  ), [formatDateTime]);

  const loadTasks = useCallback(async (
    page = pagination.current,
    pageSize = pagination.pageSize,
    search = taskSearch,
    type = taskType,
    silent = false,
  ) => {
    const seq = ++listRequestSeq.current;
    if (!silent) setLoading(true);
    try {
      const response = await apiRef.current.getGovernanceTaskList({
        page,
        page_size: pageSize,
        search: search || undefined,
        task_type: type as 'install' | 'reboot' | undefined,
      });
      if (seq !== listRequestSeq.current) return;
      const rows = mapTaskRows(response.items || []);
      setTasks(rows);
      setPagination({ current: page, pageSize, total: response.count || 0 });
    } finally {
      if (!silent && seq === listRequestSeq.current) setLoading(false);
    }
  }, [mapTaskRows, pagination.current, pagination.pageSize, taskSearch, taskType]);

  useEffect(() => {
    if (!isLoading) loadTasks(1, pagination.pageSize);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLoading]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      if (!document.hidden) loadTasks(undefined, undefined, undefined, undefined, true);
    }, 2000);
    return () => window.clearInterval(timer);
  }, [loadTasks]);

  const loadTaskDetail = useCallback(async (taskId: number, silent = false) => {
    const seq = ++detailRequestSeq.current;
    if (!silent) setDetailLoading(true);
    try {
      const result = await apiRef.current.getGovernanceTaskDetail(taskId);
      if (seq !== detailRequestSeq.current) return;
      setDetailTask(result);
      setSelectedRiskId((current) => current || result.risk_items?.[0]?.id);
    } finally {
      if (!silent && seq === detailRequestSeq.current) setDetailLoading(false);
    }
  }, []);

  const loadSelectedRisk = useCallback(async (taskId: number, riskId: string, silent = false) => {
    selectedAbortRef.current?.abort();
    const controller = new AbortController();
    selectedAbortRef.current = controller;
    const seq = ++selectedRequestSeq.current;
    if (!silent) setDetailLoading(true);
    try {
      const result = await apiRef.current.getGovernanceRiskItemDetail(taskId, riskId, { signal: controller.signal });
      if (seq === selectedRequestSeq.current) setRiskDetail(result);
    } catch (error: any) {
      if (error?.code !== 'ERR_CANCELED') throw error;
    } finally {
      if (!silent && seq === selectedRequestSeq.current) setDetailLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!drawerOpen || !detailTask?.id || !selectedRiskId) return;
    let polling = false;
    const poll = async (includeTask: boolean) => {
      if (polling) return;
      polling = true;
      const requests = [loadSelectedRisk(detailTask.id, selectedRiskId, includeTask)];
      if (includeTask) requests.unshift(loadTaskDetail(detailTask.id, true));
      await Promise.allSettled(requests);
      polling = false;
    };
    void poll(false);
    const timer = window.setInterval(() => {
      void poll(true);
    }, 2000);
    return () => {
      window.clearInterval(timer);
      selectedAbortRef.current?.abort();
      selectedRequestSeq.current += 1;
    };
  }, [detailTask?.id, drawerOpen, loadSelectedRisk, loadTaskDetail, selectedRiskId]);

  const openDetail = async (taskId: number) => {
    setDrawerOpen(true);
    setDetailTask(undefined);
    setRiskDetail(undefined);
    setSelectedRiskId(undefined);
    setRiskSearch('');
    await loadTaskDetail(taskId);
  };

  const filteredRiskItems = useMemo(() => {
    const keyword = riskSearch.trim().toLowerCase();
    const items: RiskSummary[] = detailTask?.risk_items || [];
    return keyword ? items.filter((item) => item.display_name.toLowerCase().includes(keyword)) : items;
  }, [detailTask?.risk_items, riskSearch]);

  const handleRetry = async () => {
    if (!detailTask?.id || !riskDetail?.host_id) return;
    await api.retryGovernanceTaskHost(detailTask.id, riskDetail.host_id);
    message.success('已在当前执行记录中开始重试');
    await loadTaskDetail(detailTask.id);
  };

  const handleCancel = async () => {
    if (!cancelTask || !cancelReason.trim()) return;
    setCancelSubmitting(true);
    try {
      const result = await api.cancelGovernanceTask(cancelTask.id, cancelReason.trim());
      message.success(result?.detail || '取消请求已处理');
      setCancelTask(undefined);
      setCancelReason('');
      await loadTasks();
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
          search: taskSearch || undefined,
          task_type: taskType as 'install' | 'reboot' | undefined,
        });
        rows = mapTaskRows(response.items || []);
      }
      await exportTasks(
        rows,
        selectedOnly
          ? `执行记录_选中_${new Date().toISOString().slice(0, 10)}.xlsx`
          : `执行记录_${new Date().toISOString().slice(0, 10)}.xlsx`,
        loadExportRiskRows,
        formatDateTime,
      );
    } finally {
      setExporting(false);
    }
  };

  const columns = [
    { title: '任务名称', dataIndex: 'name' },
    { title: '类型', dataIndex: 'type', width: 90, render: (value: string) => <Tag>{value}</Tag> },
    { title: '执行方式', dataIndex: 'exec', width: 230 },
    { title: '执行状态', dataIndex: 'status', width: 120, render: (_: unknown, row: TaskRow) => <Tag color={row.statusColor}>{row.status}</Tag> },
    { title: '创建时间', dataIndex: 'createdAt', width: 180 },
    {
      title: '操作',
      width: 150,
      render: (_: unknown, row: TaskRow) => <Space size={12}>
        <Button type="link" size="small" onClick={() => openDetail(row.id)}>详情</Button>
        {row.canCancel && <PermissionWrapper requiredPermissions={['Edit']}><Button type="link" size="small" danger onClick={() => setCancelTask(row)}>取消</Button></PermissionWrapper>}
      </Space>,
    },
  ];

  return <div style={{ background: 'var(--color-bg-1, #fff)', border: '1px solid var(--color-border-1, #e8e8e8)', borderRadius: 10, padding: 16, flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 14 }}>
      <Space>
        <Input.Search placeholder="任务名称" value={taskSearch} onChange={(event) => setTaskSearch(event.target.value)} onSearch={(value) => loadTasks(1, pagination.pageSize, value)} style={{ width: 220 }} />
        <Select allowClear placeholder="任务类型" value={taskType} style={{ width: 130 }} options={[{ label: '治理', value: 'install' }, { label: '重启', value: 'reboot' }]} onChange={(value) => { setTaskType(value); loadTasks(1, pagination.pageSize, taskSearch, value); }} />
      </Space>
      <Space>
        <Button loading={exporting} icon={<ExportOutlined />} onClick={() => handleExport(false)}>导出全部</Button>
        <Dropdown disabled={!selectedTasks.length || exporting} menu={{ items: [{ key: 'export', label: '导出选中', icon: <ExportOutlined />, onClick: () => handleExport(true) }] }}>
          <Button type="primary">批量操作{selectedTasks.length ? `(${selectedTasks.length})` : ''} <DownOutlined /></Button>
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
          showTotal: (total) => `共 ${total} 条`,
          onChange: (page, pageSize) => loadTasks(page, pageSize),
        }}
      />
    </div>

    <OperateDrawer
      title={detailTask?.name || '执行详情'}
      subTitle={detailTask ? <Tag color={detailTask.record_status_color || STATUS_COLOR[detailTask.record_status]}>{detailTask.record_status_display}</Tag> : null}
      extra={<Button type="link" icon={<ReloadOutlined />} onClick={() => detailTask?.id && loadTaskDetail(detailTask.id)}>刷新</Button>}
      open={drawerOpen}
      onClose={() => { setDrawerOpen(false); selectedAbortRef.current?.abort(); }}
      width={980}
      bodyStyle={{ padding: 0, display: 'flex', overflow: 'hidden' }}
    >
      {detailLoading && !detailTask ? <Spin style={{ margin: 'auto' }} /> : <>
        <div style={{ width: 310, borderRight: '1px solid var(--color-border-1, #e8e8e8)', padding: 12, overflow: 'auto' }}>
          <Input.Search placeholder="主机名-补丁名" value={riskSearch} onChange={(event) => setRiskSearch(event.target.value)} style={{ marginBottom: 12 }} />
          {filteredRiskItems.length ? filteredRiskItems.map((item) => {
            const selected = item.id === selectedRiskId;
            return <div key={item.id} onClick={() => setSelectedRiskId(item.id)} style={{ padding: '10px 12px', marginBottom: 8, cursor: 'pointer', borderRadius: 7, border: '1px solid var(--color-border-1, #e8e8e8)', borderLeft: `3px solid ${STEP_BORDER[item.status] || '#d9d9d9'}`, background: selected ? 'var(--color-fill-1, #f4f6f9)' : 'var(--color-bg-1, #fff)' }}>
              <Tooltip title={item.display_name}><div style={{ fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.display_name}</div></Tooltip>
              <Tag color={item.status_color} style={{ marginTop: 6 }}>{item.status_display}</Tag>
            </div>;
          }) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有匹配的风险项" />}
        </div>
        <div style={{ flex: 1, padding: '16px 20px', overflow: 'auto' }}>
          {detailLoading && !riskDetail ? <Spin /> : riskDetail ? <>
            {detailTask?.cancelled_at && <Alert
              type="info"
              showIcon
              message="取消信息"
              description={<Space direction="vertical" size={2}>
                <span>取消人：{detailTask.cancelled_by || '—'}</span>
                <span>取消时间：{formatDateTime(detailTask.cancelled_at)}</span>
                <span>取消原因：{detailTask.cancel_reason || '—'}</span>
              </Space>}
              style={{ marginBottom: 16 }}
            />}
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
              <div>
                <div style={{ fontSize: 16, fontWeight: 600 }}>{riskDetail.display_name}</div>
                <div style={{ color: 'var(--color-text-3, #8c8c8c)', marginTop: 4 }}>{riskDetail.host_ip || '—'} · {riskDetail.baseline_name || '—'}</div>
              </div>
              {detailTask?.can_retry && ['failed', 'unknown', 'unmet'].includes(riskDetail.status) && <PermissionWrapper requiredPermissions={['Edit']}><Button type="link" size="small" onClick={handleRetry}>重试</Button></PermissionWrapper>}
            </div>
            {(riskDetail.steps || []).map((step: any, stepIndex: number) => <div key={step.key} style={{ position: 'relative', paddingLeft: 28, paddingBottom: stepIndex === riskDetail.steps.length - 1 ? 0 : 18 }}>
              {stepIndex < riskDetail.steps.length - 1 && <div style={{ position: 'absolute', left: 9, top: 20, bottom: -2, width: 2, background: STEP_BORDER[step.status] || '#d9d9d9' }} />}
              <div style={{ position: 'absolute', left: 0, top: 2, width: 20, height: 20, borderRadius: '50%', background: STEP_BORDER[step.status] || '#d9d9d9', color: '#fff', textAlign: 'center', lineHeight: '20px', fontSize: 12 }}>{stepIndex + 1}</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}><strong>{step.name}</strong><Tag color={step.status_color}>{step.status_display}</Tag></div>
              <div style={{ display: 'grid', gap: 8 }}>
                {(step.attempts?.length ? step.attempts : [{ id: `${step.key}-empty`, status: step.status, status_display: step.status_display, status_color: step.status_color, log: '' }]).map((attempt: any, attemptIndex: number) => {
                  return <div key={attempt.id} style={{ borderLeft: `3px solid ${STEP_BORDER[attempt.status] || '#d9d9d9'}`, background: 'var(--color-fill-1, #f4f6f9)', borderRadius: 6, padding: '10px 12px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                      <span>{step.attempts?.length > 1 ? `第 ${attemptIndex + 1} 次尝试` : step.name}</span>
                      <span style={{ color: 'var(--color-text-3, #8c8c8c)' }}>{formatDateTime(attempt.started_at)}{attempt.finished_at ? ` ～ ${formatDateTime(attempt.finished_at)}` : ''}</span>
                    </div>
                    {attempt.reason && <Alert type={attempt.status === 'failed' ? 'error' : 'info'} showIcon={false} message={attempt.reason} style={{ marginTop: 8 }} />}
                  </div>;
                })}
              </div>
            </div>)}
          </> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="请选择风险项" />}
        </div>
      </>}
    </OperateDrawer>

    <Modal title={`取消任务${cancelTask ? `：${cancelTask.name}` : ''}`} open={Boolean(cancelTask)} okText="确认" cancelText="取消" okButtonProps={{ danger: true, disabled: !cancelReason.trim() }} confirmLoading={cancelSubmitting} onOk={handleCancel} onCancel={() => { if (!cancelSubmitting) { setCancelTask(undefined); setCancelReason(''); } }} destroyOnClose>
      <Alert type="warning" showIcon message="仅取消尚未执行的主机" description="已开始执行的主机不会被中断；已安装待重启的主机不会撤销安装。" style={{ marginBottom: 16 }} />
      <div style={{ marginBottom: 8 }}>取消原因</div>
      <Input.TextArea value={cancelReason} onChange={(event) => setCancelReason(event.target.value)} placeholder="请输入取消原因" maxLength={500} autoSize={{ minRows: 3, maxRows: 6 }} />
    </Modal>
  </div>;
}
