'use client';

import React, { useState, useMemo, useEffect, useRef } from 'react';
import { Table, Tag, Button, Segmented, Space, Modal, DatePicker, Alert, message, Select, Row, Col, Dropdown, Drawer, Tooltip, Switch, Radio, Steps, Popconfirm, Input, Popover } from 'antd';
import PermissionWrapper from '@/components/permission';
import { ToolOutlined, ExportOutlined, ReloadOutlined, DownOutlined, CloseOutlined } from '@ant-design/icons';
import useApiClient from '@/utils/request';
import usePatchManagerApi from '@/app/patch-manager/api';
import RemediationTag from '@/app/patch-manager/components/remediation-tag';
import ExcelJS from 'exceljs';
import SeverityTag from '@/app/patch-manager/components/severity-tag';
import CustomTable from '@/components/custom-table';
import OperateDrawer from '@/app/patch-manager/components/operate-drawer';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { useSearchParams } from 'next/navigation';

const { RangePicker } = DatePicker;

type Compliance = 'missing' | 'satisfied' | 'invalidated';
type Remediation = 'unplanned' | 'scheduled' | 'remediating' | 'installing' | 'pending_reboot' | 'rebooting' | 'verifying' | 'failed' | 'fixed';

interface RiskItem {
  key: string;
  host_id: number;
  host_name: string;
  host: string;
  patch: string;
  patch_id: number;
  patch_title?: string;
  patch_severity?: string;
  kb_number?: string;
  pkg_name?: string;
  pkg_version?: string;
  os_type?: string;
  condition?: string;
  deps?: string;
  install_impact?: { upgrade?: string[]; install?: string[]; remove?: string[]; summary?: string; raw_output?: string; error?: string };
  evaluated_at?: string | null;
  compliance: Compliance;
  remediation: Remediation;
  inOtherTask: boolean;
}

interface RiskRow {
  key: string;
  patch: string;
  sub: string;
  sev: '严重' | '重要';
  hosts: number;
  dist: { label: string; color: string }[];
  items: RiskItem[];
}

interface SelectedRow {
  key: string;
  items?: RiskItem[];
}

const DIST_RENDER = (dist: { label: string; color: string }[]) => (
  <Space size={6} wrap>{dist.map((d) => <Tag key={d.label} color={d.color}>{d.label}</Tag>)}</Space>
);

export default function RiskPendingPage() {
  const searchParams = useSearchParams();
  const routeHostId = Number(searchParams.get('host_id')) || undefined;
  const routeHostName = searchParams.get('host_name') || undefined;
  const { convertToLocalizedTime } = useLocalizedTime();
  const [selected, setSelected] = useState<React.Key[]>([]);
  const [scopeOpen, setScopeOpen] = useState(false);
  const [rebootOpen, setRebootOpen] = useState(false);
  const [execMode, setExecMode] = useState<'now' | 'window'>('now');
  const [autoReboot, setAutoReboot] = useState(false);
  const [view, setView] = useState('主机视角');
  const [currentStep, setCurrentStep] = useState(0);
  const [scopeSelected, setScopeSelected] = useState<React.Key[]>([]);
  const [scopeRows, setScopeRows] = useState<SelectedRow[]>([]);
  const [rebootRows, setRebootRows] = useState<SelectedRow[]>([]);
  const [detailRecord, setDetailRecord] = useState<{ name: string; items: RiskItem[] } | null>(null);
  const [filters, setFilters] = useState<{
    host_name?: string;
    patch_name?: string;
    baseline_name?: string;
    remediation?: string;
    severity?: string;
    os_type?: string;
  }>({ host_name: routeHostName });
  const [searchInputs, setSearchInputs] = useState<{
    host_name?: string;
    patch_name?: string;
    baseline_name?: string;
  }>({ host_name: routeHostName });
  const [windowRange, setWindowRange] = useState<[any, any] | null>(null);
  const [rebootRange, setRebootRange] = useState<[any, any] | null>(null);

  const api = usePatchManagerApi();
  const { isLoading } = useApiClient();
  const [loading, setLoading] = useState(false);
  const [riskData, setRiskData] = useState<any[]>([]);
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20, total: 0 });
  const [hostIdFilter, setHostIdFilter] = useState<number | undefined>(routeHostId);

  const viewParam = useMemo(() => (view === '主机视角' ? 'host' : view === '基线视角' ? 'baseline' : 'patch'), [view]);

  const loadRisk = async (page = 1, pageSize = pagination.pageSize, silent = false) => {
    if (!silent) setLoading(true);
    try {
      const params: any = { view: viewParam, page, page_size: pageSize };
      if (view === '主机视角') {
        if (hostIdFilter) params.host_id = hostIdFilter;
        if (filters.host_name) params.host_name = filters.host_name;
        if (filters.os_type) params.os_type = filters.os_type === 'win' ? 'windows' : 'linux';
      } else if (view === '补丁视角') {
        if (filters.patch_name) params.patch_name = filters.patch_name;
        if (filters.severity) params.severity = filters.severity;
      } else {
        if (filters.baseline_name) params.baseline_name = filters.baseline_name;
      }
      if (filters.remediation) params.remediation = filters.remediation;
      const res = await api.getRiskList(params);
      setRiskData(res.results || []);
      setPagination({ current: page, pageSize, total: res.count || 0 });
    } catch {
      setRiskData([]);
      setPagination({ current: page, pageSize, total: 0 });
    } finally {
      if (!silent) setLoading(false);
    }
  };

  useEffect(() => {
    if (isLoading) return;
    loadRisk(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLoading, view, filters]);

  // 轮询：抽屉关闭时每 2 秒静默刷新
  const silentRefreshRef = useRef<() => void>(() => {});
  silentRefreshRef.current = () => {
    loadRisk(pagination.current, pagination.pageSize, true);
  };
  useEffect(() => {
    const interval = setInterval(() => {
      if (document.hidden || scopeOpen || rebootOpen || detailRecord) return;
      silentRefreshRef.current();
    }, 2000);
    return () => clearInterval(interval);
  }, [scopeOpen, rebootOpen, detailRecord, view]);

  const getRowName = (r: unknown) => {
    const row = r as { patch?: string; host?: string; baseline?: string };
    return row.patch || row.host || row.baseline || '';
  };

  const canRemediate = (items: RiskItem[]) => items.some((i) => (i.remediation === 'unplanned' || i.remediation === 'failed') && !i.inOtherTask && i.compliance !== 'invalidated');
  const canReboot = (items: RiskItem[]) => {
    const hostIds = new Set(items.map((i) => i.host_id));
    const pendingRebootHostIds = new Set(
      items.filter((i) => i.remediation === 'pending_reboot').map((i) => i.host_id),
    );
    return hostIds.size > 0 && Array.from(hostIds).every((hostId) => pendingRebootHostIds.has(hostId));
  };

  const openScope = (rows?: SelectedRow[]) => {
    setScopeRows(rows || selectedRows);
    setScopeSelected([]);
    setCurrentStep(0);
    setScopeOpen(true);
  };

  const opCell = (r: unknown) => {
    const row = r as { key: string; items?: RiskItem[] };
    const items = row.items || [];
    const remediable = canRemediate(items);
    const rebootable = canReboot(items);
    return (
      <Space size={4}>
        {remediable ? (
          <PermissionWrapper requiredPermissions={['Add']}><Button type="link" size="small" onClick={() => openScope([row])}>治理</Button></PermissionWrapper>
        ) : (
          <Tooltip title="该补丁无可治理的风险项"><Button type="link" size="small" disabled>治理</Button></Tooltip>
        )}
        {rebootable && (
          <PermissionWrapper requiredPermissions={['Add']}><Button type="link" size="small" onClick={() => { setRebootRows([row]); setRebootOpen(true); }}>重启</Button></PermissionWrapper>
        )}
        <Button type="link" size="small" onClick={() => setDetailRecord({ name: getRowName(r), items })}>详情</Button>
      </Space>
    );
  };

  const patchCols = [
    { title: '补丁', dataIndex: 'patch', width: 140 },
    { title: '描述', dataIndex: 'sub', ellipsis: true },
    { title: '严重级别', dataIndex: 'sev', width: 100, render: (v: string) => <SeverityTag severity={v} /> },
    { title: '影响主机', dataIndex: 'hosts', width: 90, render: (v: number) => `${v} 台` },
    { title: '治理状态', dataIndex: 'dist', render: (_: unknown, r: RiskRow) => DIST_RENDER(r.dist) },
    { title: '更新时间', dataIndex: 'evaluated_at', width: 180, render: (v: string | null) => convertToLocalizedTime(v) || '—' },
    { title: '操作', dataIndex: 'op', width: 240, fixed: 'right' as const, render: (_: unknown, r: RiskRow) => opCell(r) },
  ];
  const hostCols = [
    { title: '主机', dataIndex: 'host', width: 140 },
    { title: '操作系统', dataIndex: 'os_type', width: 100, render: (v: string) => v === 'windows' ? 'Windows' : v === 'linux' ? 'Linux' : v || '—' },
    { title: '当前基线', dataIndex: 'baseline', width: 180 },
    { title: '缺失要求', dataIndex: 'missing', width: 100, render: (v: number) => <Tag color="error">缺 {v}</Tag> },
    { title: '治理状态', dataIndex: 'dist', render: (_: unknown, r: { dist: { label: string; color: string }[] }) => DIST_RENDER(r.dist) },
    { title: '更新时间', dataIndex: 'evaluated_at', width: 180, render: (v: string | null) => convertToLocalizedTime(v) || '—' },
    { title: '操作', dataIndex: 'op', width: 240, fixed: 'right' as const, render: (_: unknown, r: any) => opCell(r) },
  ];
  const baselineCols = [
    { title: '基线', dataIndex: 'baseline', width: 200 },
    { title: '适用', dataIndex: 'apply', width: 200, render: (_: unknown, r: any) => r.apply || '-' },
    { title: '影响主机', width: 100, render: (_: unknown, r: any) => `${new Set((r.items || []).map((i: any) => i.host_id)).size} 台` },
    { title: '治理状态', dataIndex: 'dist', render: (_: unknown, r: { dist: { label: string; color: string }[] }) => DIST_RENDER(r.dist) },
    { title: '更新时间', dataIndex: 'evaluated_at', width: 180, render: (v: string | null) => convertToLocalizedTime(v) || '—' },
    { title: '操作', dataIndex: 'op', width: 240, fixed: 'right' as const, render: (_: unknown, r: any) => opCell(r) },
  ];

  const cfg = view === '主机视角'
    ? { columns: hostCols, data: riskData }
    : view === '基线视角'
      ? { columns: baselineCols, data: riskData }
      : { columns: patchCols, data: riskData };

  const remediationTag = (v: Remediation) => {
    return <RemediationTag status={v} />;
  };
  const renderInstallImpact = (v: RiskItem['install_impact'], osType?: string) => {
    if (osType === 'windows') return <span style={{ color: '#bfbfbf' }}>—</span>;
    if (!v || (!v.summary && !v.error)) return <span style={{ color: '#bfbfbf' }}>-</span>;
    if (v.error) return <Tooltip title={v.error}><Tag color="warning">评估失败</Tag></Tooltip>;
    const content = <div style={{ maxWidth: 440 }}>
      <div style={{ marginBottom: 6, color: 'var(--color-text-2, #595959)' }}>包管理器 dry-run 预估的整批变更：</div>
      <div>升级：{v.upgrade?.length ? v.upgrade.join('、') : '无'}</div>
      <div>连带安装：{v.install?.length ? v.install.join('、') : '无'}</div>
      <div>移除：{v.remove?.length ? v.remove.join('、') : '无'}</div>
    </div>;
    return (
      <Popover title="预计连带变更" content={content} trigger="hover">
        <Button
          type="link"
          size="small"
          className="install-impact-summary"
          style={{
            display: 'block',
            maxWidth: '100%',
            paddingInline: 0,
            overflow: 'hidden',
            textAlign: 'left',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {v.summary}
        </Button>
      </Popover>
    );
  };
  const detailCommonCols = [
    { title: '合规要求', dataIndex: 'condition', width: 160, ellipsis: true },
    { title: '预计连带变更', dataIndex: 'install_impact', width: 180, render: (_: unknown, r: RiskItem) => renderInstallImpact(r.install_impact, r.os_type) },
    { title: '治理状态', dataIndex: 'remediation', width: 100, render: (_: unknown, r: RiskItem) => remediationTag(r.remediation) },
  ];
  const detailColumns = view === '主机视角'
    ? [{ title: '补丁要求', width: 160, fixed: 'left' as const, render: (_: unknown, r: any) => r.kb_number || r.pkg_name || r.patch_title || r.patch }, ...detailCommonCols]
    : view === '基线视角'
      ? [{ title: '主机', width: 140, fixed: 'left' as const, render: (_: unknown, r: any) => r.host_name || r.host }, { title: '补丁要求', width: 160, render: (_: unknown, r: any) => r.kb_number || r.pkg_name || r.patch_title || r.patch }, ...detailCommonCols]
      : [{ title: '主机', width: 140, fixed: 'left' as const, render: (_: unknown, r: any) => r.host_name || r.host }, ...detailCommonCols];

  const rowSelection = useMemo(() => {
    if (view === '主机视角') {
      return {
        type: 'checkbox' as const,
        selectedRowKeys: selected,
        onChange: setSelected,
        getCheckboxProps: (record: any) => ({
          disabled: (record.items || []).every((i: any) => i.in_other_task || i.inOtherTask || i.compliance === 'invalidated'),
        }),
      };
    }
    return { type: 'checkbox' as const, selectedRowKeys: selected, onChange: setSelected };
  }, [view, selected]);

  const selectedRows = (cfg.data as SelectedRow[]).filter((r) => selected.includes(r.key));
  const batchCanRemediate = selectedRows.some((r) => canRemediate(r.items));
  const batchCanReboot = selectedRows.length > 0 && selectedRows.every((r) => canReboot(r.items || []));

  interface ScopeItem {
    key: string;
    host_id: number;
    patch_id: number;
    host: string;
    patch: string;
    sev: string;
    status: string;
    remark?: string;
    deps: string;
    install_impact?: { upgrade?: string[]; install?: string[]; remove?: string[]; summary?: string; raw_output?: string; error?: string };
    os_type?: string;
    disabled?: boolean;
  }

  const buildScopeCandidates = (rows: typeof selectedRows): ScopeItem[] => {
    const items: ScopeItem[] = [];
    rows.forEach((row) => {
      (row.items || []).forEach((it: RiskItem) => {
        const disabled = it.inOtherTask || it.compliance === 'invalidated' || (it.remediation !== 'unplanned' && it.remediation !== 'failed');
        const sevDisplay = it.patch_severity === 'critical' ? '严重' : it.patch_severity === 'important' ? '重要' : it.patch_severity === 'moderate' ? '中等' : it.patch_severity === 'low' ? '低' : '-';
        const status = it.remediation === 'failed' ? '修复失败' : it.inOtherTask ? '已计划' : '待修复';
        const patchLabel = it.kb_number || it.pkg_name || it.patch_title || it.patch || '未知补丁';
        items.push({
          key: `${it.host_id}-${it.patch_id}`,
          host_id: it.host_id,
          patch_id: it.patch_id,
          host: it.host_name || it.host,
          patch: patchLabel,
          sev: sevDisplay,
          status,
          remark: it.inOtherTask ? '已在其他任务' : it.compliance === 'invalidated' ? '基线已修改，风险失效' : '',
          deps: it.deps || '-',
          install_impact: it.install_impact,
          os_type: it.os_type,
          disabled,
        });
      });
    });
    return items;
  };

  const scopeCandidates = useMemo(() => buildScopeCandidates(scopeRows), [scopeRows]);
  const scopeSelectedObjs = useMemo(() => scopeCandidates.filter((r) => scopeSelected.includes(r.key)), [scopeCandidates, scopeSelected]);

  const handleScopeSubmit = async () => {
    if (scopeSelectedObjs.length === 0) return;
    if (execMode === 'window' && (!windowRange || !windowRange[0] || !windowRange[1])) {
      message.error('请选择执行窗口');
      return;
    }
    try {
      const items = scopeSelectedObjs.map((s) => ({ host_id: s.host_id, patch_id: s.patch_id }));
      const payload: any = { items, execution_mode: execMode, auto_reboot: autoReboot };
      if (execMode === 'window' && windowRange) {
        payload.execution_window_start = windowRange[0].toISOString();
        payload.execution_window_end = windowRange[1].toISOString();
      }
      await api.remediateRisk(payload);
      message.success(`已创建治理任务，包含 ${items.length} 项`);
      setScopeOpen(false);
      setSelected([]);
      loadRisk(pagination.current, pagination.pageSize);
    } catch {
    }
  };

  const handleRebootSubmit = async () => {
    const hosts = Array.from(new Set(
      rebootRows.flatMap((r) => (r.items || [])
        .filter((i: RiskItem) => i.remediation === 'pending_reboot')
        .map((i: RiskItem) => i.host_id)),
    ));
    if (hosts.length === 0) {
      message.error('没有可重启主机');
      return;
    }
    if (!rebootRange || !rebootRange[0] || !rebootRange[1]) {
      message.error('请选择重启窗口');
      return;
    }
    try {
      await api.rebootRisk({
        target_ids: hosts,
        execution_window_start: rebootRange[0].toISOString(),
        execution_window_end: rebootRange[1].toISOString(),
      });
      message.success(`已创建重启任务，包含 ${hosts.length} 台主机`);
      setRebootOpen(false);
      setSelected([]);
      loadRisk(pagination.current, pagination.pageSize);
    } catch {
    }
  };

  const rebootHosts = useMemo(() => {
    const sevRank: Record<string, number> = { critical: 4, important: 3, moderate: 2, low: 1 };
    const hostMap = new Map<number, { host: string; patches: string[]; maxSev: string }>();
    rebootRows.forEach((r) => {
      (r.items || [])
        .filter((i: RiskItem) => i.remediation === 'pending_reboot')
        .forEach((i: RiskItem) => {
          const patchLabel = i.kb_number || i.pkg_name || i.patch_title || i.patch || '未知补丁';
          const sev = i.patch_severity || 'moderate';
          const existing = hostMap.get(i.host_id);
          if (existing) {
            existing.patches.push(patchLabel);
            if ((sevRank[sev] || 0) > (sevRank[existing.maxSev] || 0)) {
              existing.maxSev = sev;
            }
          } else {
            hostMap.set(i.host_id, { host: i.host_name || i.host, patches: [patchLabel], maxSev: sev });
          }
        });
    });
    return Array.from(hostMap.entries()).map(([id, v]) => ({
      key: String(id),
      host: v.host,
      patches: v.patches.join('、'),
      sev: v.maxSev === 'critical' ? '严重' : v.maxSev === 'important' ? '重要' : '中',
    }));
  }, [rebootRows]);

  const formatDist = (dist: { label: string; color: string }[]) => (dist || []).map((d) => d.label).join('、');

  const buildWorkbook = (rows: any[], viewLabel: string) => {
    const workbook = new ExcelJS.Workbook();
    const summarySheet = workbook.addWorksheet(viewLabel);
    const detailSheet = workbook.addWorksheet('Detail');

    detailSheet.addRow(['聚合KEY', '主机', '补丁要求', '严重级别', '合规要求', '治理状态', '更新时间']);
    const keyToFirstRow: Record<string, number> = {};
    rows.forEach((row) => {
      const items: RiskItem[] = row.items || [];
      items.forEach((it, idx) => {
        const r = detailSheet.addRow([
          row.key,
          it.host_name || it.host,
          it.kb_number || it.pkg_name || it.patch_title || it.patch,
          it.patch_severity || '',
          it.condition || '',
          it.remediation,
          convertToLocalizedTime(it.evaluated_at) || '—',
        ]);
        if (idx === 0) {
          keyToFirstRow[row.key] = r.number;
        }
      });
    });

    let headers: string[] = [];
    let rowToArray: (r: any) => (string | number)[];
    let firstColumnName: (r: any) => string;
    if (view === '主机视角') {
      headers = ['主机', '操作系统', '当前基线', '缺失要求', '治理状态', '更新时间', '查看明细'];
      rowToArray = (r) => [
        r.host,
        r.os_type === 'windows' ? 'Windows' : r.os_type === 'linux' ? 'Linux' : r.os_type || '—',
        r.baseline,
        r.missing,
        formatDist(r.dist),
        convertToLocalizedTime(r.evaluated_at) || '—',
      ];
      firstColumnName = (r) => r.host;
    } else if (view === '补丁视角') {
      headers = ['补丁', '描述', '严重级别', '影响主机', '治理状态', '更新时间', '查看明细'];
      rowToArray = (r) => [r.patch, r.sub, r.sev, r.hosts, formatDist(r.dist), convertToLocalizedTime(r.evaluated_at) || '—'];
      firstColumnName = (r) => r.patch;
    } else {
      headers = ['基线', '适用', '治理状态', '更新时间', '查看明细'];
      rowToArray = (r) => [r.baseline, r.apply || '—', formatDist(r.dist), convertToLocalizedTime(r.evaluated_at) || '—'];
      firstColumnName = (r) => r.baseline;
    }

    summarySheet.addRow(headers);
    rows.forEach((row) => {
      const summaryRow = summarySheet.addRow(rowToArray(row));
      const detailRow = keyToFirstRow[row.key];
      if (detailRow) {
        const linkCell = summaryRow.getCell(headers.length);
        const linkText = String(firstColumnName(row)).replace(/"/g, '\'\'');
        linkCell.value = {
          formula: `HYPERLINK("#Detail!A${detailRow}", "${linkText}")`,
        };
      }
    });

    return workbook;
  };

  const downloadWorkbook = async (workbook: ExcelJS.Workbook, filename: string) => {
    const buffer = await workbook.xlsx.writeBuffer();
    const blob = new Blob([buffer], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handleExportAll = async () => {
    if (riskData.length === 0) {
      message.warning('暂无数据可导出');
      return;
    }
    try {
      const workbook = buildWorkbook(riskData, view);
      const timestamp = new Date().toISOString().slice(0, 19).replace(/[-:T]/g, '');
      await downloadWorkbook(workbook, `待治理风险-${view}-${timestamp}.xlsx`);
      message.success('导出成功');
    } catch {
    }
  };

  const handleExportSelected = async () => {
    if (selectedRows.length === 0) return;
    try {
      const workbook = buildWorkbook(selectedRows, view);
      const timestamp = new Date().toISOString().slice(0, 19).replace(/[-:T]/g, '');
      await downloadWorkbook(workbook, `待治理风险-${view}-选中-${timestamp}.xlsx`);
      message.success('导出选中成功');
    } catch {
    }
  };

  const SCOPE_RISKS = scopeCandidates;

  return (
    <div style={{ background: 'var(--color-bg-1, #fff)', border: '1px solid var(--color-border-1, #e8e8e8)', borderRadius: 10, padding: '16px', flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10, marginBottom: 14 }}>
        <Segmented options={['主机视角', '补丁视角', '基线视角']} value={view} onChange={(v) => { setView(v as string); setSelected([]); setFilters({}); setSearchInputs({}); }} />
        <Space>
          <Button icon={<ExportOutlined />} onClick={handleExportAll}>导出全部</Button>
          <PermissionWrapper requiredPermissions={['Add']}><Dropdown
            disabled={selected.length === 0}
            menu={{
              items: [
                { key: 'export', label: '导出选中', icon: <ExportOutlined />, onClick: handleExportSelected },
                { key: 'remediate', label: '一键治理', icon: <ToolOutlined />, disabled: !batchCanRemediate, onClick: () => openScope() },
                {
                  key: 'reboot',
                  label: (
                    <Tooltip
                      title={!batchCanReboot ? '所选范围包含非待重启主机' : undefined}
                      zIndex={10001}
                    >
                      <span style={{ display: 'block' }}>一键重启</span>
                    </Tooltip>
                  ),
                  icon: <ReloadOutlined />,
                  disabled: !batchCanReboot,
                  onClick: () => { setRebootRows(selectedRows); setRebootOpen(true); },
                },
              ],
            }}
          >
            <Button type="primary" icon={<ToolOutlined />}>
              批量操作{selected.length ? `(${selected.length})` : ''} <DownOutlined />
            </Button>
          </Dropdown></PermissionWrapper>
        </Space>
      </div>
      <Row gutter={[12, 12]} style={{ marginBottom: 12 }} align="middle">
        {view === '主机视角' && (
          <>
            <Col>
              <Input.Search
                placeholder="主机名称"
                allowClear
                value={searchInputs.host_name}
                onChange={(e) => {
                  const value = e.target.value;
                  setSearchInputs((s) => ({ ...s, host_name: value }));
                  if (value === '') {
                    setHostIdFilter(undefined);
                    setFilters((f) => ({ ...f, host_name: undefined }));
                  }
                }}
                onSearch={(v) => {
                  setHostIdFilter(undefined);
                  setFilters((f) => ({ ...f, host_name: v || undefined }));
                }}
                style={{ width: 180 }}
              />
            </Col>
            <Col>
              <Select
                placeholder="操作系统"
                style={{ width: 120 }}
                allowClear
                value={filters.os_type}
                onChange={(v) => setFilters((f) => ({ ...f, os_type: v }))}
                options={[{ label: 'Windows', value: 'win' }, { label: 'Linux', value: 'linux' }]}
              />
            </Col>
          </>
        )}
        {view === '补丁视角' && (
          <>
            <Col>
              <Input.Search
                placeholder="补丁名称/KB/包名"
                allowClear
                value={searchInputs.patch_name}
                onChange={(e) => {
                  const value = e.target.value;
                  setSearchInputs((s) => ({ ...s, patch_name: value }));
                  if (value === '') {
                    setFilters((f) => ({ ...f, patch_name: undefined }));
                  }
                }}
                onSearch={(v) => { setFilters((f) => ({ ...f, patch_name: v || undefined })); }}
                style={{ width: 200 }}
              />
            </Col>
            <Col>
              <Select
                placeholder="严重级别"
                style={{ width: 120 }}
                allowClear
                value={filters.severity}
                onChange={(v) => setFilters((f) => ({ ...f, severity: v }))}
                options={[{ label: '严重', value: 'critical' }, { label: '重要', value: 'important' }, { label: '中等', value: 'moderate' }, { label: '低', value: 'low' }]}
              />
            </Col>
          </>
        )}
        {view === '基线视角' && (
          <>
            <Col>
              <Input.Search
                placeholder="基线名称"
                allowClear
                value={searchInputs.baseline_name}
                onChange={(e) => {
                  const value = e.target.value;
                  setSearchInputs((s) => ({ ...s, baseline_name: value }));
                  if (value === '') {
                    setFilters((f) => ({ ...f, baseline_name: undefined }));
                  }
                }}
                onSearch={(v) => { setFilters((f) => ({ ...f, baseline_name: v || undefined })); }}
                style={{ width: 200 }}
              />
            </Col>
          </>
        )}
        <Col>
          <Select
            placeholder="治理状态"
            style={{ width: 130 }}
            allowClear
            value={filters.remediation}
            onChange={(v) => setFilters((f) => ({ ...f, remediation: v }))}
            options={[{ label: '待修复', value: 'unplanned' }, { label: '已计划', value: 'scheduled' }, { label: '安装中', value: 'installing' }, { label: '待重启', value: 'pending_reboot' }, { label: '重启中', value: 'rebooting' }, { label: '验证中', value: 'verifying' }, { label: '修复失败', value: 'failed' }, { label: '已失效', value: 'invalidated' }]}
          />
        </Col>
      </Row>
      <div style={{ flex: 1, minHeight: 0 }}>
        <CustomTable
          rowKey="key"
          loading={loading}
          columns={cfg.columns as never}
          dataSource={cfg.data as never}
          rowSelection={rowSelection as never}
          pagination={{
            current: pagination.current,
            pageSize: pagination.pageSize,
            total: pagination.total,
            showSizeChanger: true,
            showTotal: (t) => `共 ${t} 条`,
            style: { marginBottom: 0 },
            onChange: (page, pageSize) => loadRisk(page, pageSize),
          }}
        />
      </div>

      <Drawer
        title={`风险项明细 - ${detailRecord?.name || ''}`}
        open={!!detailRecord}
        onClose={() => setDetailRecord(null)}
        width={720}
      >
        <Table
          size="small"
          rowKey="key"
          pagination={false}
          dataSource={detailRecord?.items || []}
          columns={detailColumns as never}
          scroll={view === '基线视角' ? { x: 740 } : undefined}
        />
      </Drawer>

      <OperateDrawer
        title="一键治理"
        open={scopeOpen}
        onClose={() => setScopeOpen(false)}
        width={900}
        bodyStyle={{ padding: 0, overflow: 'hidden' }}
        footer={
          <Space>
            <Button onClick={() => setScopeOpen(false)}>取消</Button>
            {currentStep === 0 && (
              <Button type="primary" disabled={scopeSelected.length === 0} onClick={() => setCurrentStep(1)}>下一步</Button>
            )}
            {currentStep === 1 && (
              <>
                <Button onClick={() => setCurrentStep(0)}>上一步</Button>
                <Popconfirm
                  title="确认创建治理任务"
                  description={`将对 ${scopeSelected.length} 台主机执行补丁安装，${autoReboot ? '仅自动重启检测为需要重启的主机' : '安装完成后不自动重启'}。`}
                  onConfirm={handleScopeSubmit}
                  okText="确认"
                  cancelText="取消"
                >
                  <Button type="primary">确认创建治理任务</Button>
                </Popconfirm>
              </>
            )}
          </Space>
        }
      >
        <div style={{ display: 'flex', flexDirection: 'column', height: '100%', padding: 16, boxSizing: 'border-box' }}>
          <Steps
            current={currentStep}
            size="small"
            style={{ marginBottom: 16, flexShrink: 0 }}
            items={[{ title: '确认风险项' }, { title: '执行设置' }]}
          />

          {currentStep === 0 && (
            <div style={{ display: 'flex', gap: 16, flex: 1, minHeight: 0 }}>
              <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
                <Alert
                  type="info"
                  showIcon
                  style={{ marginBottom: 12 }}
                  message="预计连带变更来自 Linux 包管理器 dry-run"
                  description="除所选补丁外，依赖解析可能连带升级、安装或移除其他软件包；Windows 暂不提供该预估。"
                />
                <div style={{ flex: 1, minHeight: 0 }}>
                  <CustomTable
                    size="small"
                    rowKey="key"
                    rowSelection={{
                      type: 'checkbox',
                      selectedRowKeys: scopeSelected,
                      onChange: setScopeSelected,
                      getCheckboxProps: (r: typeof SCOPE_RISKS[number]) => ({ disabled: r.disabled }),
                      preserveSelectedRowKeys: true,
                    }}
                    dataSource={SCOPE_RISKS}
                    pagination={{ total: SCOPE_RISKS.length, pageSize: 10, showSizeChanger: true, showTotal: (t) => `共 ${t} 条` }}
                    columns={[
                      { title: '主机', dataIndex: 'host', width: 100 },
                      { title: '补丁要求', dataIndex: 'patch', width: 130 },
                      { title: '严重级别', dataIndex: 'sev', width: 80, render: (v: string) => <Tag color={v === '严重' ? 'error' : 'warning'}>{v}</Tag> },
                      { title: '状态', dataIndex: 'status', width: 80, render: (_: unknown, r: typeof SCOPE_RISKS[number]) => r.remark ? <Tooltip title={r.remark}><Tag color={r.status === '未纳入' ? 'error' : r.status === '待修复' ? 'warning' : 'processing'}>{r.status}</Tag></Tooltip> : <Tag color={r.status === '未纳入' ? 'error' : r.status === '待修复' ? 'warning' : 'processing'}>{r.status}</Tag> },
                      { title: '预计连带变更', dataIndex: 'install_impact', width: 180, render: (_: unknown, r: ScopeItem) => renderInstallImpact(r.install_impact, r.os_type) },
                    ]}
                  />
                </div>
              </div>
              <div style={{ width: 200, display: 'flex', flexDirection: 'column', borderLeft: '1px solid var(--color-border-1, #e8e8e8)', paddingLeft: 16 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                  <span style={{ fontWeight: 500 }}>已选 {scopeSelectedObjs.length} 项</span>
                  {scopeSelectedObjs.length > 0 && (
                    <Button type="link" size="small" danger style={{ paddingInline: 0 }} onClick={() => setScopeSelected([])}>全部清除</Button>
                  )}
                </div>
                <div style={{ flex: 1, overflowY: 'auto' }}>
                  {scopeSelectedObjs.map((r) => (
                    <div key={r.key} className="scope-item" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '6px 8px', borderRadius: 6, marginBottom: 4, background: 'var(--color-fill-1, #f4f6f9)', fontSize: 13 }}>
                      <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.host} - {r.patch}</span>
                      <CloseOutlined className="scope-remove-btn" style={{ color: '#bfbfbf', fontSize: 12, cursor: 'pointer', opacity: 0, transition: 'opacity 0.2s' }} onClick={() => setScopeSelected((prev) => prev.filter((k) => k !== r.key))} />
                    </div>
                  ))}
                  {scopeSelectedObjs.length === 0 && (
                    <div style={{ color: 'var(--color-text-3, #8c8c8c)', fontSize: 13, textAlign: 'center', marginTop: 40 }}>暂未选择</div>
                  )}
                </div>
              </div>
            </div>
          )}
          <style>{`.scope-item:hover .scope-remove-btn { opacity: 1 !important; }`}</style>

          {currentStep === 1 && (
          <div style={{ maxWidth: 500, flex: 1, overflowY: 'auto' }}>
            <div style={{ fontWeight: 500, marginBottom: 6 }}>执行方式</div>
            <Radio.Group value={execMode} onChange={(e) => setExecMode(e.target.value)} style={{ marginBottom: 10 }}>
              <Radio value="now">立即执行</Radio>
              <Radio value="window">执行窗口</Radio>
            </Radio.Group>
            {execMode === 'window' && (
              <div style={{ marginBottom: 12 }}>
                <RangePicker showTime style={{ width: '100%' }} placeholder={['窗口开始', '窗口结束']} value={windowRange} onChange={(v) => setWindowRange(v as any)} />
              </div>
            )}

            <div style={{ marginBottom: 4 }}>
              <span style={{ fontWeight: 500 }}>自动重启</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
              <Switch checked={autoReboot} onChange={setAutoReboot} />
            </div>
            {autoReboot && (
              <Alert
                style={{ marginBottom: 14 }}
                type="warning"
                showIcon
                message="仅自动重启明确需要重启的主机"
                description="补丁安装完成后检测重启需求；无需重启的主机将跳过重启，无法确认的主机将进入待重启并等待人工处理。重启可能导致业务短暂中断。"
              />
            )}
            {!autoReboot && <div style={{ marginBottom: 14 }} />}
          </div>
          )}
        </div>
      </OperateDrawer>

      <Modal
        title="提交前范围确认 · 重启"
        open={rebootOpen}
        width={620}
        onCancel={() => setRebootOpen(false)}
        footer={[
          <Button key="cancel" onClick={() => setRebootOpen(false)}>取消</Button>,
          <Popconfirm
            key="ok"
            title="确认创建重启任务"
            description={`将对 ${rebootHosts.length} 台主机执行重启，可能导致业务短暂中断。`}
            onConfirm={handleRebootSubmit}
            okText="确认"
            cancelText="取消"
          >
            <Button type="primary">确认创建重启任务</Button>
          </Popconfirm>,
        ]}
      >
        <div style={{ fontWeight: 500, marginBottom: 6 }}>待重启主机</div>
        <Table
          size="small"
          rowKey="key"
          pagination={false}
          style={{ marginBottom: 14 }}
          dataSource={rebootHosts}
          columns={[
            { title: '主机', dataIndex: 'host', width: 120 },
            { title: '补丁要求', dataIndex: 'patches', ellipsis: true },
            { title: '严重级别', dataIndex: 'sev', width: 80, render: (v: string) => <Tag color={v === '严重' ? 'error' : 'warning'}>{v}</Tag> },
          ]}
        />
        <Alert style={{ marginBottom: 12 }} type="info" showIcon message="重启任务必须设置执行窗口，重启策略固定为「窗口内自动重启」" />
        <div style={{ marginBottom: 12 }}>
          <RangePicker showTime style={{ width: '100%' }} placeholder={['窗口开始', '窗口结束']} value={rebootRange} onChange={(v) => setRebootRange(v as any)} />
        </div>
      </Modal>
    </div>
  );
}
