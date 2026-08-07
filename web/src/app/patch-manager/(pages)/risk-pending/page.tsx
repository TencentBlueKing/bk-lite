'use client';

import React, { useState, useMemo, useEffect, useRef } from 'react';
import { Table, Tag, Button, Segmented, Space, Modal, DatePicker, Alert, message, Select, Row, Col, Dropdown, Drawer, Tooltip, Switch, Radio, Steps, Popconfirm, Input, Popover, Form } from 'antd';
import PermissionWrapper from '@/components/permission';
import { ToolOutlined, ExportOutlined, ReloadOutlined, DownOutlined, CloseOutlined } from '@ant-design/icons';
import useApiClient from '@/utils/request';
import usePatchManagerApi from '@/app/patch-manager/api';
import { createListRequestCoordinator } from '@/app/patch-manager/utils/list-request-coordinator';
import { PATCH_MANAGER_POLL_INTERVAL_MS } from '@/app/patch-manager/constants/polling';
import RemediationTag from '@/app/patch-manager/components/remediation-tag';
import ExcelJS from 'exceljs';
import SeverityTag from '@/app/patch-manager/components/severity-tag';
import CustomTable from '@/components/custom-table';
import OperateDrawer from '@/app/patch-manager/components/operate-drawer';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { useSearchParams } from 'next/navigation';
import { useTranslation } from '@/utils/i18n';
import usePermissions from '@/hooks/usePermissions';

const { RangePicker } = DatePicker;

type Compliance = 'missing' | 'satisfied' | 'invalidated';
type Remediation = 'unplanned' | 'scheduled' | 'remediating' | 'installing' | 'pending_reboot' | 'rebooting' | 'verifying' | 'failed' | 'fixed';

interface RiskItem {
  host_id: number;
  host_name: string;
  host_ip?: string;
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
  can_remediate?: boolean;
  can_reboot?: boolean;
}

interface RiskRow {
  key: string;
  patch: string;
  sub: string;
  sev: string;
  hosts: number;
  dist: { status: string; count: number; color: string }[];
  items: RiskItem[];
}

interface SelectedRow {
  key: string;
  items?: RiskItem[];
}

const DistRender = ({ dist }: { dist: { status: string; count: number; color: string }[] }) => {
  const { t } = useTranslation();
  return <Space size={6} wrap>{dist.map((d) => <Tag key={d.status} color={d.color}>{t(`patchManager.remediationStatus.${d.status}`, d.status)} {d.count}</Tag>)}</Space>;
};

const InstallImpactColumnTitle = () => {
  const { t } = useTranslation();
  return <Tooltip
    title={(
      <div>
        <div style={{ fontWeight: 500, marginBottom: 4 }}>{t('patchManager.risk.installImpactSource')}</div>
        <div>{t('patchManager.risk.installImpactHelp')}</div>
      </div>
    )}
  >
    <span
      tabIndex={0}
      style={{ borderBottom: '1px dashed currentColor', cursor: 'help' }}
    >
      {t('patchManager.risk.installImpact')}
    </span>
  </Tooltip>;
};

export default function RiskPendingPage() {
  const { t } = useTranslation();
  const { hasPermission } = usePermissions();
  const searchParams = useSearchParams();
  const routeHostId = Number(searchParams.get('host_id')) || undefined;
  const routeHostName = searchParams.get('host_name') || undefined;
  const { convertToLocalizedTime } = useLocalizedTime();
  const [selected, setSelected] = useState<React.Key[]>([]);
  const [scopeOpen, setScopeOpen] = useState(false);
  const [rebootOpen, setRebootOpen] = useState(false);
  const [execMode, setExecMode] = useState<'now' | 'window'>('now');
  const [autoReboot, setAutoReboot] = useState(false);
  const [view, setView] = useState<'host' | 'patch' | 'baseline'>('host');
  const [currentStep, setCurrentStep] = useState(0);
  const [scopeSelected, setScopeSelected] = useState<React.Key[]>([]);
  const [scopeRows, setScopeRows] = useState<SelectedRow[]>([]);
  const [rebootRows, setRebootRows] = useState<SelectedRow[]>([]);
  const [rebootScope, setRebootScope] = useState<{
    target_ids: number[];
    scope_token: string;
    items: Array<Record<string, any>>;
  }>();
  const [rebootScopeLoading, setRebootScopeLoading] = useState(false);
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
  const [taskName, setTaskName] = useState('');
  const [rebootTaskName, setRebootTaskName] = useState('');
  const [remediationTaskPrefix, setRemediationTaskPrefix] = useState<'治理' | '一键治理'>('一键治理');
  const [rebootTaskPrefix, setRebootTaskPrefix] = useState<'重启' | '一键重启'>('一键重启');
  const [rebootConfirmOpen, setRebootConfirmOpen] = useState(false);
  const [rebootValidation, setRebootValidation] = useState<{ taskName?: string; window?: string }>({});

  const api = usePatchManagerApi();
  const { isLoading } = useApiClient();
  const [loading, setLoading] = useState(false);
  const listRequestCoordinatorRef = useRef(createListRequestCoordinator(setLoading));
  const [riskData, setRiskData] = useState<any[]>([]);
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20, total: 0 });
  const [hostIdFilter, setHostIdFilter] = useState<number | undefined>(routeHostId);

  const viewParam = view;

  const loadRisk = async (page = 1, pageSize = pagination.pageSize, silent = false) => {
    const coordinator = listRequestCoordinatorRef.current;
    const ticket = coordinator.begin({ visible: !silent });
    if (!ticket) return;
    try {
      const params: any = { view: viewParam, page, page_size: pageSize };
      if (view === 'host') {
        if (hostIdFilter) params.host_id = hostIdFilter;
        if (filters.host_name) params.host_name = filters.host_name;
        if (filters.os_type) params.os_type = filters.os_type === 'win' ? 'windows' : 'linux';
      } else if (view === 'patch') {
        if (filters.patch_name) params.patch_name = filters.patch_name;
        if (filters.severity) params.severity = filters.severity;
      } else {
        if (filters.baseline_name) params.baseline_name = filters.baseline_name;
      }
      if (filters.remediation) params.remediation = filters.remediation;
      const res = await api.getRiskList(params, { signal: ticket.signal });
      if (!coordinator.shouldApply(ticket)) return;
      setRiskData(res.results || []);
      setPagination({ current: page, pageSize, total: res.count || 0 });
    } catch {
      if (!coordinator.shouldApply(ticket)) return;
      setRiskData([]);
      setPagination({ current: page, pageSize, total: 0 });
    } finally {
      coordinator.finish(ticket);
    }
  };

  useEffect(() => {
    if (isLoading) return;
    loadRisk(1);
  }, [isLoading, view, filters]);

  // 外层列表持续静默轮询；抽屉打开不会停止轮询。
  const silentRefreshRef = useRef<() => void>(() => {});
  silentRefreshRef.current = () => {
    loadRisk(pagination.current, pagination.pageSize, true);
  };
  useEffect(() => {
    const interval = setInterval(() => {
      if (document.hidden) return;
      silentRefreshRef.current();
    }, PATCH_MANAGER_POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [view]);

  useEffect(() => () => {
    listRequestCoordinatorRef.current.invalidate();
  }, []);

  const getRowName = (r: unknown) => {
    const row = r as { patch?: string; host?: string; baseline?: string };
    return row.patch || row.host || row.baseline || '';
  };

  const buildDefaultTaskName = (
    prefix: '治理' | '一键治理' | '重启' | '一键重启',
    hosts: Array<{ id: number; name: string }>,
  ) => {
    const uniqueHosts = Array.from(
      new Map(hosts.filter((host) => host.id).map((host) => [host.id, host])).values(),
    );
    const firstHostName = uniqueHosts[0]?.name || t('patchManager.risk.unknownHost', '未知主机');
    const hostSummary = uniqueHosts.length > 1
      ? `${firstHostName}等${uniqueHosts.length}台`
      : firstHostName;
    const now = new Date();
    const date = [now.getFullYear(), now.getMonth() + 1, now.getDate()]
      .map((value, index) => index === 0 ? String(value) : String(value).padStart(2, '0'))
      .join('');
    const reservedLength = prefix.length + date.length + 2;
    return `${prefix}-${hostSummary.slice(0, Math.max(1, 128 - reservedLength))}-${date}`;
  };

  const hasRemediableState = (items: RiskItem[]) => items.some((i) => (i.remediation === 'unplanned' || i.remediation === 'failed') && !i.inOtherTask && i.compliance !== 'invalidated');
  const canRemediate = (items: RiskItem[]) => items.some((i) => i.can_remediate && (i.remediation === 'unplanned' || i.remediation === 'failed') && !i.inOtherTask && i.compliance !== 'invalidated');
  const canReboot = (items: RiskItem[]) => {
    const hostIds = new Set(items.map((i) => i.host_id));
    const pendingRebootHostIds = new Set(
      items.filter((i) => i.remediation === 'pending_reboot').map((i) => i.host_id),
    );
    const operableHostIds = new Set(items.filter((i) => i.can_reboot).map((i) => i.host_id));
    return hostIds.size > 0 && Array.from(hostIds).every((hostId) => pendingRebootHostIds.has(hostId) && operableHostIds.has(hostId));
  };

  const openScope = (rows?: SelectedRow[], prefix: '治理' | '一键治理' = '一键治理') => {
    setScopeRows(rows || selectedRows);
    setScopeSelected([]);
    setCurrentStep(0);
    setTaskName('');
    setRemediationTaskPrefix(prefix);
    setScopeOpen(true);
  };

  const loadRebootScope = async (
    rows: SelectedRow[],
    prefix: '重启' | '一键重启',
  ) => {
    const targetIds = Array.from(new Set(
      rows.flatMap((row) => (row.items || []))
        .filter((item) => item.remediation === 'pending_reboot')
        .map((item) => item.host_id),
    ));
    if (!targetIds.length) return;
    setRebootScopeLoading(true);
    try {
      const scope = await api.previewRebootRisk(targetIds);
      setRebootScope(scope);
      setRebootTaskName(buildDefaultTaskName(
        prefix,
        scope.items.map((item) => ({
          id: Number(item.host_id),
          name: String(item.host_name || item.host_ip || item.host_id),
        })),
      ));
    } finally {
      setRebootScopeLoading(false);
    }
  };

  const openReboot = (rows: SelectedRow[], prefix: '重启' | '一键重启') => {
    setRebootRows(rows);
    setRebootScope(undefined);
    setRebootTaskName('');
    setRebootRange(null);
    setRebootTaskPrefix(prefix);
    setRebootConfirmOpen(false);
    setRebootValidation({});
    setRebootOpen(true);
    void loadRebootScope(rows, prefix);
  };

  const opCell = (r: unknown) => {
    const row = r as { key: string; items?: RiskItem[] };
    const items = row.items || [];
    const hasRemediable = hasRemediableState(items);
    const remediable = canRemediate(items);
    const rebootable = canReboot(items);
    return (
      <Space size={4}>
        {hasRemediable ? (
          <PermissionWrapper requiredPermissions={['Add']} instPermissions={remediable ? ['Operate'] : []}><Button type="link" size="small" onClick={() => openScope([row], '治理')}>{t('patchManager.risk.remediate')}</Button></PermissionWrapper>
        ) : (
          <Tooltip title={t('patchManager.risk.noRemediableItems')}><Button type="link" size="small" disabled>{t('patchManager.risk.remediate')}</Button></Tooltip>
        )}
        {rebootable && (
          <PermissionWrapper requiredPermissions={['Add']} instPermissions={rebootable ? ['Operate'] : []}><Button type="link" size="small" onClick={() => openReboot([row], '重启')}>{t('patchManager.risk.reboot')}</Button></PermissionWrapper>
        )}
        <Button type="link" size="small" onClick={() => setDetailRecord({ name: getRowName(r), items })}>{t('patchManager.risk.details')}</Button>
      </Space>
    );
  };

  const patchCols = [
    { title: t('patchManager.risk.patch'), dataIndex: 'patch', width: 140 },
    { title: t('patchManager.risk.description'), dataIndex: 'sub', ellipsis: true },
    { title: t('patchManager.severity'), dataIndex: 'sev', width: 100, render: (v: string) => <SeverityTag severity={v} /> },
    { title: t('patchManager.risk.affectedHosts'), dataIndex: 'hosts', width: 90, render: (v: number) => t('patchManager.dashboard.targetCount', undefined, { count: v }) },
    { title: t('patchManager.risk.remediationStatus'), dataIndex: 'dist', render: (_: unknown, r: RiskRow) => <DistRender dist={r.dist} /> },
    { title: t('patchManager.updateTime'), dataIndex: 'evaluated_at', width: 180, render: (v: string | null) => convertToLocalizedTime(v) || '—' },
    { title: t('patchManager.operation'), dataIndex: 'op', width: 240, fixed: 'right' as const, render: (_: unknown, r: RiskRow) => opCell(r) },
  ];
  const hostCols = [
    { title: t('patchManager.risk.host'), dataIndex: 'host', width: 140 },
    { title: t('patchManager.risk.ipAddress'), dataIndex: 'host_ip', width: 140, render: (v: string) => v || '—' },
    { title: t('patchManager.osType'), dataIndex: 'os_type', width: 100, render: (v: string) => v === 'windows' ? 'Windows' : v === 'linux' ? 'Linux' : v || '—' },
    { title: t('patchManager.risk.currentBaseline'), dataIndex: 'baseline', width: 180 },
    {
      title: t('patchManager.risk.missingPatchCount'),
      dataIndex: 'missing',
      width: 110,
      render: (v: number, r: any) => (
        <Button
          type="link"
          size="small"
          aria-label={`${t('patchManager.risk.missingPatchCount')} ${v}`}
          style={{ height: 'auto', paddingInline: 0, fontVariantNumeric: 'tabular-nums' }}
          onClick={() => setDetailRecord({ name: getRowName(r), items: r.items || [] })}
        >
          {v}
        </Button>
      ),
    },
    { title: t('patchManager.risk.remediationStatus'), dataIndex: 'dist', render: (_: unknown, r: { dist: RiskRow['dist'] }) => <DistRender dist={r.dist} /> },
    { title: t('patchManager.updateTime'), dataIndex: 'evaluated_at', width: 180, render: (v: string | null) => convertToLocalizedTime(v) || '—' },
    { title: t('patchManager.operation'), dataIndex: 'op', width: 240, fixed: 'right' as const, render: (_: unknown, r: any) => opCell(r) },
  ];
  const baselineCols = [
    { title: t('patchManager.risk.baseline'), dataIndex: 'baseline', width: 200 },
    { title: t('patchManager.risk.applicable'), dataIndex: 'apply', width: 200, render: (_: unknown, r: any) => r.apply || '-' },
    { title: t('patchManager.risk.affectedHosts'), width: 100, render: (_: unknown, r: any) => t('patchManager.dashboard.targetCount', undefined, { count: new Set((r.items || []).map((i: any) => i.host_id)).size }) },
    { title: t('patchManager.risk.remediationStatus'), dataIndex: 'dist', render: (_: unknown, r: { dist: RiskRow['dist'] }) => <DistRender dist={r.dist} /> },
    { title: t('patchManager.updateTime'), dataIndex: 'evaluated_at', width: 180, render: (v: string | null) => convertToLocalizedTime(v) || '—' },
    { title: t('patchManager.operation'), dataIndex: 'op', width: 240, fixed: 'right' as const, render: (_: unknown, r: any) => opCell(r) },
  ];

  const cfg = view === 'host'
    ? { columns: hostCols, data: riskData }
    : view === 'baseline'
      ? { columns: baselineCols, data: riskData }
      : { columns: patchCols, data: riskData };

  const remediationTag = (v: Remediation) => {
    return <RemediationTag status={v} />;
  };
  const renderInstallImpact = (v: RiskItem['install_impact'], osType?: string) => {
    if (osType === 'windows') return <span style={{ color: '#bfbfbf' }}>--</span>;
    if (!v || (!v.summary && !v.error)) return <span style={{ color: '#bfbfbf' }}>--</span>;
    if (v.error) return <Tooltip title={v.error}><Tag color="error">{t('patchManager.risk.previewFailed')}</Tag></Tooltip>;
    const content = <div>
      <div style={{ marginBottom: 6, color: 'var(--color-text-2, #595959)' }}>{t('patchManager.risk.installImpactBatch')}</div>
      <div>{t('patchManager.risk.upgrade')}：{v.upgrade?.length ? v.upgrade.join('、') : t('patchManager.risk.none')}</div>
      <div>{t('patchManager.risk.additionalInstall')}：{v.install?.length ? v.install.join('、') : t('patchManager.risk.none')}</div>
      <div>{t('patchManager.risk.remove')}：{v.remove?.length ? v.remove.join('、') : t('patchManager.risk.none')}</div>
    </div>;
    return (
      <Popover title={t('patchManager.risk.installImpact')} content={content} trigger="hover">
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
    { title: t('patchManager.risk.complianceRequirement'), dataIndex: 'condition', width: 160, ellipsis: true },
    { title: <InstallImpactColumnTitle />, dataIndex: 'install_impact', width: 180, render: (_: unknown, r: RiskItem) => renderInstallImpact(r.install_impact, r.os_type) },
    { title: t('patchManager.risk.remediationStatus'), dataIndex: 'remediation', width: 100, render: (_: unknown, r: RiskItem) => remediationTag(r.remediation) },
  ];
  const detailColumns = view === 'host'
    ? [{ title: t('patchManager.risk.patchRequirement'), width: 160, fixed: 'left' as const, render: (_: unknown, r: any) => r.kb_number || r.pkg_name || r.patch_title || r.patch }, ...detailCommonCols]
    : view === 'baseline'
      ? [{ title: t('patchManager.risk.host'), width: 140, fixed: 'left' as const, render: (_: unknown, r: any) => r.host_name || r.host }, { title: t('patchManager.risk.patchRequirement'), width: 160, render: (_: unknown, r: any) => r.kb_number || r.pkg_name || r.patch_title || r.patch }, ...detailCommonCols]
      : [{ title: t('patchManager.risk.host'), width: 140, fixed: 'left' as const, render: (_: unknown, r: any) => r.host_name || r.host }, ...detailCommonCols];

  const rowSelection = useMemo(() => {
    if (view === 'host') {
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
        const disabled = !it.can_remediate || it.inOtherTask || it.compliance === 'invalidated' || (it.remediation !== 'unplanned' && it.remediation !== 'failed');
        const sevDisplay = it.patch_severity || 'unspecified';
        const status = it.remediation === 'failed' ? 'failed' : it.inOtherTask ? 'scheduled' : 'unplanned';
        const patchLabel = it.kb_number || it.pkg_name || it.patch_title || it.patch || t('patchManager.risk.unknownPatch');
        items.push({
          key: `${it.host_id}-${it.patch_id}`,
          host_id: it.host_id,
          patch_id: it.patch_id,
          host: it.host_name || it.host,
          patch: patchLabel,
          sev: sevDisplay,
          status,
          remark: it.inOtherTask ? t('patchManager.risk.inOtherTask') : it.compliance === 'invalidated' ? t('patchManager.risk.riskInvalidated') : '',
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
  const previewFailedItems = useMemo(
    () => scopeSelectedObjs.filter((item) => !!item.install_impact?.error),
    [scopeSelectedObjs],
  );
  const previewFailedLabels = useMemo(() => {
    const labels = previewFailedItems.slice(0, 5).map((item) => `${item.host} - ${item.patch}`);
    if (previewFailedItems.length > labels.length) {
      labels.push(t('patchManager.risk.andMoreItems', undefined, { count: previewFailedItems.length - labels.length }));
    }
    return labels.join(', ');
  }, [previewFailedItems, t]);

  const handleScopeSubmit = async () => {
    if (scopeSelectedObjs.length === 0) return;
    if (!taskName.trim()) {
      message.error(t('patchManager.risk.taskNameRequired'));
      return;
    }
    if (execMode === 'window' && (!windowRange || !windowRange[0] || !windowRange[1])) {
      message.error(t('patchManager.risk.selectExecutionWindow'));
      return;
    }
    try {
      const items = scopeSelectedObjs.map((s) => ({ host_id: s.host_id, patch_id: s.patch_id }));
      const payload: Parameters<typeof api.remediateRisk>[0] = {
        items,
        name: taskName.trim(),
        execution_mode: execMode,
        auto_reboot: autoReboot,
      };
      if (execMode === 'window' && windowRange) {
        payload.execution_window_start = windowRange[0].toISOString();
        payload.execution_window_end = windowRange[1].toISOString();
      }
      await api.remediateRisk(payload);
      message.success(t('patchManager.risk.remediationCreated', undefined, { count: items.length }));
      setScopeOpen(false);
      setSelected([]);
      loadRisk(pagination.current, pagination.pageSize);
    } catch {
    }
  };

  const validateRebootForm = () => {
    const validation: { taskName?: string; window?: string } = {};
    if (!rebootTaskName.trim()) {
      validation.taskName = t('patchManager.risk.taskNameRequired');
    }
    if (!rebootRange || !rebootRange[0] || !rebootRange[1]) {
      validation.window = t('patchManager.risk.selectRebootWindow');
    }
    setRebootValidation(validation);
    return Object.keys(validation).length === 0;
  };

  const handleRebootConfirmRequest = () => {
    if (validateRebootForm()) {
      setRebootConfirmOpen(true);
    }
  };

  const handleRebootSubmit = async () => {
    const hosts = rebootScope?.target_ids || [];
    if (hosts.length === 0) {
      message.error(t('patchManager.risk.noRebootHosts'));
      return;
    }
    if (!validateRebootForm()) {
      setRebootConfirmOpen(false);
      return;
    }
    try {
      await api.rebootRisk({
        target_ids: hosts,
        name: rebootTaskName.trim(),
        execution_window_start: rebootRange[0].toISOString(),
        execution_window_end: rebootRange[1].toISOString(),
        scope_token: rebootScope?.scope_token || '',
      });
      message.success(t('patchManager.risk.rebootCreated', undefined, { count: hosts.length }));
      setRebootConfirmOpen(false);
      setRebootOpen(false);
      setSelected([]);
      loadRisk(pagination.current, pagination.pageSize);
    } catch (error: any) {
      const code = error?.response?.data?.code || error?.code;
      if (code === 'reboot_scope_changed') {
        message.warning(t('patchManager.risk.rebootScopeChanged'));
        setRebootScope(undefined);
        await loadRebootScope(rebootRows, rebootTaskPrefix);
      }
    }
  };

  const rebootHosts = useMemo(() => {
    const sevRank: Record<string, number> = { critical: 4, important: 3, moderate: 2, low: 1 };
    const hostMap = new Map<number, { host: string; patches: string[]; maxSev: string }>();
    (rebootScope?.items || []).forEach((i: any) => {
      const patchLabel = i.patch_name || t('patchManager.risk.unknownPatch');
      const sev = i.patch_severity || 'moderate';
      const existing = hostMap.get(i.host_id);
      if (existing) {
        existing.patches.push(patchLabel);
        if ((sevRank[sev] || 0) > (sevRank[existing.maxSev] || 0)) {
          existing.maxSev = sev;
        }
      } else {
        hostMap.set(i.host_id, { host: i.host_name, patches: [patchLabel], maxSev: sev });
      }
    });
    return Array.from(hostMap.entries()).map(([id, v]) => ({
      key: String(id),
      host: v.host,
      patches: v.patches.join('、'),
      sev: v.maxSev,
    }));
  }, [rebootScope?.items, t]);

  const formatDist = (dist: RiskRow['dist']) => (dist || []).map((d) => `${t(`patchManager.remediationStatus.${d.status}`, d.status)} ${d.count}`).join('、');

  const buildWorkbook = (rows: any[], viewLabel: string) => {
    const workbook = new ExcelJS.Workbook();
    const summarySheet = workbook.addWorksheet(viewLabel);
    const detailSheet = workbook.addWorksheet(t('patchManager.risk.detailSheet'));

    detailSheet.addRow(t('patchManager.risk.exportDetailHeaders').split('|'));
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
    if (view === 'host') {
      headers = t('patchManager.risk.exportHostHeaders').split('|');
      rowToArray = (r) => [
        r.host,
        r.host_ip || '—',
        r.os_type === 'windows' ? 'Windows' : r.os_type === 'linux' ? 'Linux' : r.os_type || '—',
        r.baseline,
        r.missing,
        formatDist(r.dist),
        convertToLocalizedTime(r.evaluated_at) || '—',
      ];
      firstColumnName = (r) => r.host;
    } else if (view === 'patch') {
      headers = t('patchManager.risk.exportPatchHeaders').split('|');
      rowToArray = (r) => [r.patch, r.sub, r.sev, r.hosts, formatDist(r.dist), convertToLocalizedTime(r.evaluated_at) || '—'];
      firstColumnName = (r) => r.patch;
    } else {
      headers = t('patchManager.risk.exportBaselineHeaders').split('|');
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
      message.warning(t('patchManager.risk.noExportData'));
      return;
    }
    try {
      const workbook = buildWorkbook(riskData, view);
      const timestamp = new Date().toISOString().slice(0, 19).replace(/[-:T]/g, '');
      await downloadWorkbook(workbook, `${t('patchManager.risk.exportFilePrefix')}-${t(`patchManager.risk.view.${view}`)}-${timestamp}.xlsx`);
      message.success(t('patchManager.risk.exportSucceeded'));
    } catch {
    }
  };

  const handleExportSelected = async () => {
    if (selectedRows.length === 0) return;
    try {
      const workbook = buildWorkbook(selectedRows, view);
      const timestamp = new Date().toISOString().slice(0, 19).replace(/[-:T]/g, '');
      await downloadWorkbook(workbook, `${t('patchManager.risk.exportFilePrefix')}-${t(`patchManager.risk.view.${view}`)}-${t('patchManager.risk.selected')}-${timestamp}.xlsx`);
      message.success(t('patchManager.risk.exportSelectedSucceeded'));
    } catch {
    }
  };

  const SCOPE_RISKS = scopeCandidates;

  return (
    <div style={{ background: 'var(--color-bg-1, #fff)', border: '1px solid var(--color-border-1, #e8e8e8)', borderRadius: 10, padding: '16px', flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10, marginBottom: 14 }}>
        <Segmented options={(['host', 'patch', 'baseline'] as const).map((value) => ({ label: t(`patchManager.risk.view.${value}`), value }))} value={view} onChange={(v) => { setView(v as typeof view); setSelected([]); setFilters({}); setSearchInputs({}); }} />
        <Space>
          <Button icon={<ExportOutlined />} onClick={handleExportAll}>{t('patchManager.risk.exportAll')}</Button>
          <Dropdown
            disabled={selected.length === 0}
            menu={{
              items: [
                { key: 'export', label: t('patchManager.risk.exportSelected'), icon: <ExportOutlined />, onClick: handleExportSelected },
                {
                  key: 'remediate',
                  label: <PermissionWrapper requiredPermissions={['Add']} instPermissions={batchCanRemediate ? ['Operate'] : []}>{t('patchManager.risk.oneClickRemediation')}</PermissionWrapper>,
                  icon: <ToolOutlined />,
                  disabled: !batchCanRemediate || !hasPermission(['Add']),
                  onClick: () => openScope(undefined, '一键治理'),
                },
                {
                  key: 'reboot',
                  label: (
                    <Tooltip
                      title={!batchCanReboot ? t('patchManager.risk.rebootSelectionBlocked') : undefined}
                      zIndex={10001}
                    >
                      <PermissionWrapper requiredPermissions={['Add']} instPermissions={batchCanReboot ? ['Operate'] : []}><span style={{ display: 'block' }}>{t('patchManager.risk.oneClickReboot')}</span></PermissionWrapper>
                    </Tooltip>
                  ),
                  icon: <ReloadOutlined />,
                  disabled: !batchCanReboot || !hasPermission(['Add']),
                  onClick: () => openReboot(selectedRows, '一键重启'),
                },
              ],
            }}
          >
            <Button type="primary" icon={<ToolOutlined />}>
              {t('patchManager.risk.batchActions')}{selected.length ? `(${selected.length})` : ''} <DownOutlined />
            </Button>
          </Dropdown>
        </Space>
      </div>
      <Row gutter={[12, 12]} style={{ marginBottom: 12 }} align="middle">
        {view === 'host' && (
          <>
            <Col>
              <Input.Search
                placeholder={t('patchManager.risk.hostName')}
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
                placeholder={t('patchManager.osType')}
                style={{ width: 120 }}
                allowClear
                value={filters.os_type}
                onChange={(v) => setFilters((f) => ({ ...f, os_type: v }))}
                options={[{ label: 'Windows', value: 'win' }, { label: 'Linux', value: 'linux' }]}
              />
            </Col>
          </>
        )}
        {view === 'patch' && (
          <>
            <Col>
              <Input.Search
                placeholder={t('patchManager.risk.patchSearch')}
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
                placeholder={t('patchManager.severity')}
                style={{ width: 120 }}
                allowClear
                value={filters.severity}
                onChange={(v) => setFilters((f) => ({ ...f, severity: v }))}
                options={(['critical', 'important', 'moderate', 'low'] as const).map((value) => ({ label: t(`patchManager.severityValues.${value}`), value }))}
              />
            </Col>
          </>
        )}
        {view === 'baseline' && (
          <>
            <Col>
              <Input.Search
                placeholder={t('patchManager.baseline.name')}
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
            placeholder={t('patchManager.risk.remediationStatus')}
            style={{ width: 130 }}
            allowClear
            value={filters.remediation}
            onChange={(v) => setFilters((f) => ({ ...f, remediation: v }))}
            options={(['unplanned', 'scheduled', 'installing', 'pending_reboot', 'rebooting', 'verifying', 'failed', 'invalidated'] as const).map((value) => ({ label: t(`patchManager.remediationStatus.${value}`), value }))}
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
            showTotal: (total) => t('patchManager.common.totalItems', undefined, { count: total }),
            style: { marginBottom: 0 },
            onChange: (page, pageSize) => loadRisk(page, pageSize),
          }}
        />
      </div>

      <Drawer
        title={t('patchManager.risk.detailTitle', undefined, { name: detailRecord?.name || '' })}
        open={!!detailRecord}
        onClose={() => setDetailRecord(null)}
        width={720}
      >
        <Table
          size="small"
          rowKey={(item: RiskItem) => `${item.host_id}-${item.patch_id}`}
          pagination={false}
          dataSource={detailRecord?.items || []}
          columns={detailColumns as never}
          scroll={view === 'baseline' ? { x: 740 } : undefined}
        />
      </Drawer>

      <OperateDrawer
        title={t('patchManager.risk.oneClickRemediation')}
        open={scopeOpen}
        onClose={() => setScopeOpen(false)}
        width={900}
        bodyStyle={{ padding: 0, overflow: 'hidden' }}
        footer={
          <Space>
            <Button onClick={() => setScopeOpen(false)}>{t('patchManager.cancel')}</Button>
            {currentStep === 0 && (
              <Button
                type="primary"
                disabled={scopeSelected.length === 0}
                onClick={() => {
                  setTaskName(buildDefaultTaskName(
                    remediationTaskPrefix,
                    scopeSelectedObjs.map((item) => ({ id: item.host_id, name: item.host })),
                  ));
                  setCurrentStep(1);
                }}
              >
                {t('patchManager.risk.next')}
              </Button>
            )}
            {currentStep === 1 && (
              <>
                <Button onClick={() => setCurrentStep(0)}>{t('patchManager.risk.previous')}</Button>
                <Popconfirm
                  title={t('patchManager.risk.confirmCreateRemediation')}
                  description={<div>
                    <div>{t('patchManager.risk.createRemediationConfirm', undefined, { count: scopeSelected.length, reboot: autoReboot ? t('patchManager.risk.onlyRequiredReboot') : t('patchManager.risk.noAutomaticReboot') })}</div>
                    {previewFailedItems.length > 0 && (
                      <div style={{ color: 'var(--color-error, #ff4d4f)', marginTop: 6, maxWidth: 500, whiteSpace: 'normal' }}>
                        {t('patchManager.risk.previewFailureConfirm', undefined, { items: previewFailedLabels })}
                      </div>
                    )}
                  </div>}
                  onConfirm={handleScopeSubmit}
                  okText={t('patchManager.confirm')}
                  cancelText={t('patchManager.cancel')}
                >
                  <Button type="primary" disabled={!taskName.trim()}>{t('patchManager.risk.confirmCreateRemediation')}</Button>
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
            items={[{ title: t('patchManager.risk.confirmRiskItems') }, { title: t('patchManager.risk.executionSettings') }]}
          />

          {currentStep === 0 && (
            <div style={{ display: 'flex', gap: 16, flex: 1, minHeight: 0 }}>
              <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
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
                    pagination={{ total: SCOPE_RISKS.length, pageSize: 10, showSizeChanger: true, showTotal: (total) => t('patchManager.common.totalItems', undefined, { count: total }) }}
                    columns={[
                      { title: t('patchManager.risk.host'), dataIndex: 'host', width: 100 },
                      { title: t('patchManager.risk.patchRequirement'), dataIndex: 'patch', width: 130 },
                      { title: t('patchManager.severity'), dataIndex: 'sev', width: 80, render: (v: string) => <SeverityTag severity={v} /> },
                      { title: t('patchManager.taskStatus'), dataIndex: 'status', width: 80, render: (_: unknown, r: typeof SCOPE_RISKS[number]) => r.remark ? <Tooltip title={r.remark}><span><RemediationTag status={r.status} /></span></Tooltip> : <RemediationTag status={r.status} /> },
                      { title: <InstallImpactColumnTitle />, dataIndex: 'install_impact', width: 180, render: (_: unknown, r: ScopeItem) => renderInstallImpact(r.install_impact, r.os_type) },
                    ]}
                  />
                </div>
              </div>
              <div style={{ width: 200, display: 'flex', flexDirection: 'column', borderLeft: '1px solid var(--color-border-1, #e8e8e8)', paddingLeft: 16 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                  <span style={{ fontWeight: 500 }}>{t('patchManager.common.selectedItems', undefined, { count: scopeSelectedObjs.length })}</span>
                  {scopeSelectedObjs.length > 0 && (
                    <Button type="link" size="small" danger style={{ paddingInline: 0 }} onClick={() => setScopeSelected([])}>{t('patchManager.common.clearAll')}</Button>
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
                    <div style={{ color: 'var(--color-text-3, #8c8c8c)', fontSize: 13, textAlign: 'center', marginTop: 40 }}>{t('patchManager.common.noSelection')}</div>
                  )}
                </div>
              </div>
            </div>
          )}
          <style>{`.scope-item:hover .scope-remove-btn { opacity: 1 !important; }`}</style>

          {currentStep === 1 && (
          <div style={{ width: '100%', flex: 1, overflowY: 'auto' }}>
            <Form layout="vertical" component={false}>
              <Form.Item
                label={t('patchManager.risk.taskName')}
                required
                colon={false}
                style={{ marginBottom: 14 }}
              >
                <Input
                  value={taskName}
                  onChange={(event) => setTaskName(event.target.value)}
                  maxLength={128}
                  showCount
                  placeholder={t('patchManager.risk.taskNamePlaceholder')}
                  status={taskName.length > 0 && !taskName.trim() ? 'error' : undefined}
                />
              </Form.Item>
            </Form>
            <div style={{ fontWeight: 500, marginBottom: 6 }}>{t('patchManager.risk.executionMode')}</div>
            <Radio.Group value={execMode} onChange={(e) => setExecMode(e.target.value)} style={{ marginBottom: 10 }}>
              <Radio value="now">{t('patchManager.risk.executeNow')}</Radio>
              <Radio value="window">{t('patchManager.risk.executionWindow')}</Radio>
            </Radio.Group>
            {execMode === 'window' && (
              <div style={{ marginBottom: 12 }}>
                <RangePicker showTime style={{ width: '100%' }} placeholder={[t('patchManager.risk.windowStart'), t('patchManager.risk.windowEnd')]} value={windowRange} onChange={(v) => setWindowRange(v as any)} />
              </div>
            )}

            <div style={{ fontWeight: 500, marginBottom: 6 }}>
              {t('patchManager.risk.autoReboot')}
            </div>
            <Alert
              style={{ width: '100%', marginBottom: 12 }}
              type="warning"
              showIcon
              message={t('patchManager.risk.autoRebootTitle')}
              description={t('patchManager.risk.autoRebootHelp')}
            />
            <div style={{ marginBottom: 14 }}>
              <Switch
                aria-label={t('patchManager.risk.autoReboot')}
                checked={autoReboot}
                onChange={(checked: boolean) => setAutoReboot(checked)}
              />
            </div>
          </div>
          )}
        </div>
      </OperateDrawer>

      <Modal
        title={t('patchManager.risk.rebootScopeTitle')}
        open={rebootOpen}
        width={620}
        onCancel={() => setRebootOpen(false)}
        footer={[
          <Button key="cancel" onClick={() => setRebootOpen(false)}>{t('patchManager.cancel')}</Button>,
          <Popconfirm
            key="ok"
            open={rebootConfirmOpen}
            title={t('patchManager.risk.confirmCreateReboot')}
            description={t('patchManager.risk.rebootConfirm', undefined, { count: rebootHosts.length })}
            onConfirm={handleRebootSubmit}
            onOpenChange={(open) => {
              if (!open) setRebootConfirmOpen(false);
            }}
            okText={t('patchManager.confirm')}
            cancelText={t('patchManager.cancel')}
          >
            <Button
              type="primary"
              disabled={rebootScopeLoading || !rebootScope}
              onClick={handleRebootConfirmRequest}
            >
              {t('patchManager.risk.confirmCreateReboot')}
            </Button>
          </Popconfirm>,
        ]}
      >
        <Form layout="vertical" component={false}>
          <Form.Item
            label={t('patchManager.risk.taskName')}
            required
            colon={false}
            validateStatus={rebootValidation.taskName ? 'error' : undefined}
            help={rebootValidation.taskName}
            style={{ marginBottom: 14 }}
          >
            <Input
              value={rebootTaskName}
              onChange={(event) => {
                const value = event.target.value;
                setRebootTaskName(value);
                if (value.trim()) {
                  setRebootValidation((current) => ({ ...current, taskName: undefined }));
                }
              }}
              maxLength={128}
              showCount
              placeholder={t('patchManager.risk.taskNamePlaceholder')}
            />
          </Form.Item>
          <div style={{ fontWeight: 500, marginBottom: 6 }}>{t('patchManager.risk.pendingRebootHosts')}</div>
          <Table
            loading={rebootScopeLoading}
            size="small"
            rowKey="key"
            pagination={false}
            style={{ marginBottom: 14 }}
            dataSource={rebootHosts}
            columns={[
              { title: t('patchManager.risk.host'), dataIndex: 'host', width: 120 },
              { title: t('patchManager.risk.patchRequirement'), dataIndex: 'patches', ellipsis: true },
              { title: t('patchManager.severity'), dataIndex: 'sev', width: 80, render: (v: string) => <SeverityTag severity={v} /> },
            ]}
          />
          <Alert style={{ marginBottom: 12 }} type="info" showIcon message={t('patchManager.risk.rebootWindowHelp')} />
          <Form.Item
            label={t('patchManager.risk.executionWindow')}
            required
            colon={false}
            validateStatus={rebootValidation.window ? 'error' : undefined}
            help={rebootValidation.window}
            style={{ marginBottom: 12 }}
          >
            <RangePicker
              showTime
              style={{ width: '100%' }}
              placeholder={[t('patchManager.risk.windowStart'), t('patchManager.risk.windowEnd')]}
              value={rebootRange}
              onChange={(value) => {
                setRebootRange(value as any);
                if (value?.[0] && value?.[1]) {
                  setRebootValidation((current) => ({ ...current, window: undefined }));
                }
              }}
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
