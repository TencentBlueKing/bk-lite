'use client';

import React, { useState, useEffect, useMemo, useRef } from 'react';
import { Tag, Button, Input, InputNumber, Select, Space, Modal, Form, Radio, Upload, Alert, message, Tooltip, Popconfirm } from 'antd';
import { PlusOutlined, LinkOutlined, EditOutlined, InboxOutlined, CloseOutlined } from '@ant-design/icons';
import PermissionWrapper from '@/components/permission';
import TimeSelector from '@/components/time-selector';
import Password from '@/components/password';
import GroupTreeSelect from '@/components/group-tree-select';
import useApiClient from '@/utils/request';
import usePatchManagerApi from '@/app/patch-manager/api';
import { createListRequestCoordinator } from '@/app/patch-manager/utils/list-request-coordinator';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { PatchTarget, OSType } from '@/app/patch-manager/types';
import ComplianceTag, { ComplianceStatus } from '@/app/patch-manager/components/compliance-tag';
import DualSelector from '@/app/patch-manager/components/dual-selector';
import CustomTable from '@/components/custom-table';
import OperateDrawer from '@/app/patch-manager/components/operate-drawer';
import { useRouter, useSearchParams } from 'next/navigation';
import { buildTargetFilterSearch, parseBaselineFilter } from './filter-state';
import { useTranslation } from '@/utils/i18n';
import {
  createPatchManagerPollFrequencyOptions,
  PATCH_MANAGER_MANUAL_POLL_INTERVAL_MS,
} from '@/app/patch-manager/constants/polling';
import {
  formatArchitecture,
  normalizeArchitecture,
} from '@/app/patch-manager/constants/architecture';

interface HostRow {
  key: string;
  name: string;
  ip: string;
  os: string;
  source_type?: 'manual' | 'node_mgmt';
  baseline: string | null;
  baseline_id?: number | null;
  compliance: ComplianceStatus;
  missing?: number;
  lastEval: string | null;
  connectivity: 'undetected' | 'detecting' | 'connected' | 'failed';
  lastDetected: string | null;
  hasActiveTask?: boolean;
  hasPendingReboot?: boolean;
  complianceFailureReason?: string;
  permission?: string[];
}

const CONN_TAG: Record<HostRow['connectivity'], { color: string }> = {
  undetected: { color: 'default' }, detecting: { color: 'processing' }, connected: { color: 'success' }, failed: { color: 'error' },
};

function ConnTag({ status }: { status: HostRow['connectivity'] }) {
  const { t } = useTranslation();
  return <Tag color={CONN_TAG[status].color}>{t(`patchManager.targetPage.connectivity.${status}`)}</Tag>;
}

type PatchTargetItem = PatchTarget & {
  key?: string | number;
  arch?: string;
  baseline_name?: string | null;
  baseline_id?: number | null;
  baseline?: string | null;
  compliance_status?: ComplianceStatus;
  compliance_failure_reason?: string;
  missing_count?: number;
  missing?: number;
  last_evaluated_at?: string | null;
  lastEval?: string | null;
  last_detected_at?: string | null;
  lastDetected?: string | null;
  has_active_task?: boolean;
  has_pending_reboot?: boolean;
};

function mapConnectivity(status?: string): HostRow['connectivity'] {
  if (status === 'connected') return 'connected';
  if (status === 'failed') return 'failed';
  if (status === 'detecting') return 'detecting';
  return 'undetected';
}

function mapNodeOsType(os?: string): OSType {
  if (!os) return 'linux';
  return /windows/i.test(os) ? 'windows' : 'linux';
}

function mapTargetToRow(item: PatchTargetItem): HostRow {
  return {
    key: String(item.id ?? item.key),
    name: item.name ?? '',
    ip: item.ip ?? '',
    os: item.os_type_display ?? item.os_type ?? '',
    source_type: item.source_type,
    baseline: item.baseline_name ?? item.baseline ?? null,
    baseline_id: item.baseline_id ?? null,
    compliance: item.compliance_status ?? 'unconfigured',
    missing: item.missing_count ?? item.missing,
    lastEval: item.last_evaluated_at ?? item.lastEval ?? null,
    connectivity: mapConnectivity(item.connectivity_status),
    lastDetected: item.last_detected_at ?? item.lastDetected ?? null,
    hasActiveTask: item.has_active_task ?? false,
    hasPendingReboot: item.has_pending_reboot ?? false,
    complianceFailureReason: item.compliance_failure_reason || '',
    permission: item.permission,
  };
}

const SAVED_SECRET = '********';

function targetConnectionSignature(
  values: Record<string, any>,
  os: 'win' | 'linux',
  credential: 'password' | 'key',
  keyName = '',
) {
  return JSON.stringify(os === 'linux' ? {
    os,
    ip: values.ip || '',
    cloudRegion: values.cloud_region_id ?? null,
    port: values.ssh_port ?? 22,
    user: values.ssh_user || '',
    credential,
    password: credential === 'password' ? values.ssh_password || '' : '',
    key: credential === 'key' ? keyName : '',
  } : {
    os,
    ip: values.ip || '',
    cloudRegion: values.cloud_region_id ?? null,
    port: values.winrm_port ?? 5986,
    scheme: values.winrm_scheme || 'https',
    user: values.winrm_user || '',
    password: values.winrm_password || '',
  });
}

export default function TargetPage() {
  const { t } = useTranslation();
  const router = useRouter();
  const searchParams = useSearchParams();
  const api = usePatchManagerApi();
  const { isLoading } = useApiClient();
  const { convertToLocalizedTime } = useLocalizedTime();
  const [data, setData] = useState<PatchTarget[]>([]);
  const [listLoading, setListLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const listRequestCoordinatorRef = useRef(createListRequestCoordinator(setListLoading));
  const [pollIntervalMs, setPollIntervalMs] = useState(PATCH_MANAGER_MANUAL_POLL_INTERVAL_MS);
  const [selectedKeys, setSelectedKeys] = useState<React.Key[]>([]);
  const [bindOpen, setBindOpen] = useState(false);
  const [, setScanOpen] = useState(false);
  const [scanMethod, setScanMethod] = useState<'now' | 'cycle'>('now');
  const [manualOpen, setManualOpen] = useState(false);
  const [editingTarget, setEditingTarget] = useState<PatchTarget | null>(null);
  const [nodeOpen, setNodeOpen] = useState(false);
  const [ipQuery, setIpQuery] = useState('');
  const [complianceFilter, setComplianceFilter] = useState<ComplianceStatus | undefined>(
    (searchParams.get('compliance_status') as ComplianceStatus | null) || undefined,
  );
  const [baselineFilter, setBaselineFilter] = useState<number | undefined>(() => (
    parseBaselineFilter(new URLSearchParams(searchParams.toString()))
  ));
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20, total: 0 });

  const [os, setOs] = useState<'win' | 'linux'>('linux');
  const [cred, setCred] = useState<'password' | 'key'>('password');
  const [selectedNodes, setSelectedNodes] = useState<React.Key[]>([]);
  const [nodeSearch, setNodeSearch] = useState('');
  const [baselines, setBaselines] = useState<any[]>([]);
  const [bindBaseline, setBindBaseline] = useState<number | undefined>();
  const [cloudRegions, setCloudRegions] = useState<Array<{ id: number; name: string; display_name?: string }>>([]);
  const [cloudRegionLoading, setCloudRegionLoading] = useState(false);
  const [nodes, setNodes] = useState<any[]>([]);
  const [nodePagination, setNodePagination] = useState({ current: 1, pageSize: 20, total: 0 });
  const nodeCacheRef = useRef<Map<string, any>>(new Map());
  const [importedNodes, setImportedNodes] = useState<Array<{ node_id: string; name: string }>>([]);
  const [nodeLoading, setNodeLoading] = useState(false);
  const nodeRequestCoordinatorRef = useRef(createListRequestCoordinator(setNodeLoading));
  const importedNodeRequestCoordinatorRef = useRef(createListRequestCoordinator(() => undefined));
  const [form] = Form.useForm();
  const [testingConnectivity, setTestingConnectivity] = useState(false);
  const [connectivityResult, setConnectivityResult] = useState<{
    status: 'connected' | 'failed';
    detail: string;
    checkedAt: string;
  }>();
  const [testedSignature, setTestedSignature] = useState('');
  const [initialConnectionSignature, setInitialConnectionSignature] = useState('');
  const [keepExistingKey, setKeepExistingKey] = useState(false);
  const pollFrequencyOptions = useMemo(
    () => createPatchManagerPollFrequencyOptions(t('common.timeSelector.off')),
    [t],
  );
  const editingCredential = editingTarget
    ? editingTarget.ssh_credential_type || (editingTarget.has_ssh_key ? 'key' : 'password')
    : undefined;

  const loadData = async (
    page = pagination.current,
    pageSize = pagination.pageSize,
    filters: {
      ip?: string | null;
      compliance_status?: ComplianceStatus | null;
      baseline_id?: number | null;
    } = {},
    silent = false,
  ) => {
    const coordinator = listRequestCoordinatorRef.current;
    const ticket = coordinator.begin({ visible: !silent });
    if (!ticket) return;
    try {
      const res = await api.getPatchTargetList(
        {
          page,
          page_size: pageSize,
          ip: filters.ip !== undefined ? filters.ip || undefined : ipQuery || undefined,
          compliance_status:
            filters.compliance_status !== undefined
              ? filters.compliance_status || undefined
              : complianceFilter || undefined,
          baseline_id:
            filters.baseline_id !== undefined
              ? filters.baseline_id || undefined
              : baselineFilter,
        },
        { signal: ticket.signal },
      );
      if (!coordinator.shouldApply(ticket)) return;
      setData(res.items || []);
      setPagination((p) => ({ ...p, current: page, pageSize, total: res.count || 0 }));
    } catch {
      if (!coordinator.shouldApply(ticket)) return;
      setData([]);
      setPagination((p) => ({ ...p, current: page, pageSize, total: 0 }));
    } finally {
      coordinator.finish(ticket);
    }
  };

  const loadBaselines = async () => {
    try {
      const res = await api.getBaselineList({ page: 1, page_size: -1 });
      setBaselines(Array.isArray(res) ? res : (res.items || []));
    } catch {
      setBaselines([]);
    }
  };

  const syncFilterQuery = (
    baselineId: number | undefined,
    complianceStatus: ComplianceStatus | undefined,
  ) => {
    const next = buildTargetFilterSearch(
      new URLSearchParams(searchParams.toString()),
      { baselineId, complianceStatus },
    );
    const query = next.toString();
    router.replace(query ? `/patch-manager/target?${query}` : '/patch-manager/target', { scroll: false });
  };

  const loadCloudRegions = async () => {
    setCloudRegionLoading(true);
    try {
      const res = await api.getCloudRegionList({ page: 1, page_size: -1 });
      setCloudRegions(Array.isArray(res) ? res : (res.items || []));
    } catch {
      setCloudRegions([]);
    } finally {
      setCloudRegionLoading(false);
    }
  };

  const loadNodeList = async (page = 1, pageSize = nodePagination.pageSize, search = nodeSearch) => {
    const coordinator = nodeRequestCoordinatorRef.current;
    const ticket = coordinator.begin({ visible: true });
    if (!ticket) return;
    try {
      const res = await api.queryNodes(
        { page, page_size: pageSize, name: search || undefined },
        { signal: ticket.signal },
      );
      if (!coordinator.shouldApply(ticket)) return;
      const mapped = (res.items || []).map((n: any) => ({
        ...n,
        key: n.id,
        os: n.operating_system ?? '',
        arch: n.cpu_architecture ?? '',
        cloud_region_id: n.cloud_region ?? n.cloud_region_id ?? null,
      }));
      setNodes(mapped);
      setNodePagination({ current: page, pageSize, total: res.count || 0 });
      mapped.forEach((n: any) => nodeCacheRef.current.set(String(n.id), n));
    } catch {
      if (!coordinator.shouldApply(ticket)) return;
      setNodes([]);
      setNodePagination({ current: page, pageSize, total: 0 });
    } finally {
      coordinator.finish(ticket);
    }
  };

  const loadImportedNodes = async () => {
    const coordinator = importedNodeRequestCoordinatorRef.current;
    const ticket = coordinator.begin({ visible: false });
    if (!ticket) return;
    try {
      const res = await api.getImportedNodeIds({ signal: ticket.signal });
      if (!coordinator.shouldApply(ticket)) return;
      setImportedNodes(res.items || []);
    } catch {
      if (!coordinator.shouldApply(ticket)) return;
      setImportedNodes([]);
    } finally {
      coordinator.finish(ticket);
    }
  };

  useEffect(() => {
    if (isLoading) return;
    loadData(1, pagination.pageSize);
    loadBaselines();
    loadCloudRegions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLoading]);

  useEffect(() => {
    if (manualOpen) {
      loadCloudRegions();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [manualOpen]);

  useEffect(() => {
    if (bindOpen) {
      loadBaselines();
    }
  }, [bindOpen]);

  useEffect(() => {
    if (nodeOpen) {
      setSelectedNodes([]);
      setNodeSearch('');
      nodeCacheRef.current = new Map();
      setNodePagination({ current: 1, pageSize: 20, total: 0 });
      loadNodeList(1, 20, '');
      loadImportedNodes();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodeOpen]);

  const targetPollRef = useRef<() => void>(() => {});
  targetPollRef.current = () => loadData(pagination.current, pagination.pageSize, {}, true);
  useEffect(() => {
    if (isLoading || pollIntervalMs <= 0) return undefined;
    const timer = setInterval(() => {
      if (!document.hidden) targetPollRef.current();
    }, pollIntervalMs);
    return () => clearInterval(timer);
  }, [isLoading, pollIntervalMs]);

  useEffect(() => () => {
    listRequestCoordinatorRef.current.invalidate();
    nodeRequestCoordinatorRef.current.invalidate();
    importedNodeRequestCoordinatorRef.current.invalidate();
  }, []);

  const rows = useMemo<HostRow[]>(() => data.map((item) => mapTargetToRow(item as PatchTargetItem)), [data]);

  const bulkBindDisabled = useMemo(() => {
    if (selectedKeys.length === 0) return true;
    return selectedKeys.some((key) => {
      const row = rows.find((r) => r.key === String(key));
      return !!row && (row.hasActiveTask || row.hasPendingReboot || !row.permission?.includes('Operate'));
    });
  }, [selectedKeys, rows]);

  const includedNodeIds = useMemo(
    () => new Set(importedNodes.map((n) => n.node_id)),
    [importedNodes],
  );

  const selectedNodeRecords = useMemo(() => {
    const recordMap = new Map<string, any>();
    nodeCacheRef.current.forEach((n, id) => recordMap.set(id, n));
    return selectedNodes
      .map((key) => recordMap.get(String(key)))
      .filter(Boolean);
  }, [selectedNodes, nodes]);

  const handleDelete = async (id: string) => {
    setActionLoading(true);
    try {
      await api.deletePatchTarget(Number(id));
      message.success(t('patchManager.targetPage.deleted'));
      await loadData();
    } catch {
    } finally {
      setActionLoading(false);
    }
  };

  const selectedKeyFile = (values: Record<string, any>): File | undefined => {
    const upload = values.ssh_key_file;
    return Array.isArray(upload)
      ? upload[0]?.originFileObj
      : upload?.fileList?.[0]?.originFileObj || upload?.file?.originFileObj || upload?.file;
  };

  const currentConnectionSignature = (values: Record<string, any>) => {
    const keyFile = selectedKeyFile(values);
    const keyName = keepExistingKey
      ? editingTarget?.ssh_key_file_name || ''
      : keyFile?.name || '';
    return targetConnectionSignature(values, os, cred, keyName);
  };

  const appendConnectionFields = (formData: FormData, values: Record<string, any>) => {
    formData.append('os_type', os === 'win' ? 'windows' : 'linux');
    if (os === 'linux') {
      formData.append('ssh_port', String(values.ssh_port ?? 22));
      formData.append('ssh_user', values.ssh_user || '');
      formData.append('ssh_credential_type', cred);
      if (cred === 'password' && values.ssh_password && values.ssh_password !== SAVED_SECRET) {
        formData.append('ssh_password', values.ssh_password);
      }
      if (cred === 'key') {
        const keyFile = selectedKeyFile(values);
        if (keyFile) formData.append('ssh_key_file', keyFile);
      }
    } else {
      formData.append('winrm_port', String(values.winrm_port ?? 5986));
      formData.append('winrm_scheme', values.winrm_scheme || 'https');
      formData.append('winrm_user', values.winrm_user || '');
      if (values.winrm_password && values.winrm_password !== SAVED_SECRET) {
        formData.append('winrm_password', values.winrm_password);
      }
    }
  };

  const handleFormConnectivityTest = async () => {
    let values: Record<string, any>;
    try {
      values = await form.validateFields();
    } catch {
      return;
    }
    const formData = new FormData();
    formData.append('ip', values.ip);
    formData.append('source_type', 'manual');
    formData.append('cloud_region_id', String(values.cloud_region_id ?? ''));
    appendConnectionFields(formData, values);
    setTestingConnectivity(true);
    try {
      const result = editingTarget
        ? await api.checkPatchTargetConnectivity(editingTarget.id, formData)
        : await api.testPatchTargetConnectivity(formData);
      const status = result.connectivity_status === 'connected' ? 'connected' : 'failed';
      setConnectivityResult({ status, detail: result.detail, checkedAt: new Date().toISOString() });
      setTestedSignature(currentConnectionSignature(values));
    } finally {
      setTestingConnectivity(false);
    }
  };

  const openManualTarget = (target?: PatchTarget) => {
    setConnectivityResult(undefined);
    setTestedSignature('');
    if (!target) {
      setEditingTarget(null);
      setOs('linux');
      setCred('password');
      setKeepExistingKey(false);
      setInitialConnectionSignature('');
      form.resetFields();
      setManualOpen(true);
      return;
    }
    const targetOs = target.os_type === 'windows' ? 'win' : 'linux';
    const targetCredential = target.ssh_credential_type || (target.has_ssh_key ? 'key' : 'password');
    const values = {
      name: target.name,
      ip: target.ip,
      team: target.team,
      cloud_region_id: target.cloud_region_id,
      ssh_port: target.ssh_port,
      ssh_user: target.ssh_user,
      ssh_password: target.has_ssh_password ? SAVED_SECRET : undefined,
      winrm_port: target.winrm_port,
      winrm_scheme: target.winrm_scheme,
      winrm_user: target.winrm_user,
      winrm_password: target.has_winrm_password ? SAVED_SECRET : undefined,
    };
    setEditingTarget(target);
    setOs(targetOs);
    setCred(targetCredential);
    setKeepExistingKey(targetCredential === 'key' && Boolean(target.has_ssh_key));
    form.setFieldsValue(values);
    setInitialConnectionSignature(targetConnectionSignature(
      values,
      targetOs,
      targetCredential,
      target.has_ssh_key ? target.ssh_key_file_name || '' : '',
    ));
    setManualOpen(true);
  };

  const handleCreate = async () => {
    setActionLoading(true);
    try {
      const values = await form.validateFields();
      const formData = new FormData();
      formData.append('name', values.name);
      formData.append('ip', values.ip);
      formData.append('source_type', 'manual');
      formData.append('cloud_region_id', String(values.cloud_region_id ?? ''));
      if (values.team) {
        formData.append('team', JSON.stringify(values.team));
      }
      if (!editingTarget) {
        formData.append('connectivity_status', 'unknown');
      }

      appendConnectionFields(formData, values);
      if (
        editingTarget
        && currentConnectionSignature(values) !== initialConnectionSignature
        && (
          connectivityResult?.status !== 'connected'
          || testedSignature !== currentConnectionSignature(values)
        )
      ) {
        message.error(t('patchManager.targetPage.connectivityRetestRequired'));
        return;
      }

      if (editingTarget) {
        await api.updatePatchTarget(editingTarget.id, formData);
        message.success(t('patchManager.targetPage.updated'));
      } else {
        await api.createPatchTarget(formData);
        message.success(t('patchManager.targetPage.saved'));
      }
      setManualOpen(false);
      setEditingTarget(null);
      form.resetFields();
      setCred('password');
      await loadData();
    } catch {
    } finally {
      setActionLoading(false);
    }
  };

  const handleBind = async () => {
    if (!bindBaseline) {
      message.error(t('patchManager.targetPage.selectBaseline'));
      return;
    }
    const targetIds = selectedKeys.map((k) => Number(k)).filter((id) => !isNaN(id));
    setActionLoading(true);
    try {
      await api.bindHostsToBaseline(bindBaseline, targetIds);
      message.success(t('patchManager.targetPage.baselineBound'));
      setScanOpen(false);
      setBindOpen(false);
      setBindBaseline(undefined);
      setSelectedKeys([]);
      await loadData();
    } catch {
    } finally {
      setActionLoading(false);
    }
  };

  const handleNodeSave = async () => {
    if (selectedNodes.length === 0) {
      message.warning(t('patchManager.targetPage.selectNodes'));
      return;
    }
    setActionLoading(true);
    try {
      const targets = selectedNodes
        .map((key) => {
          const node = nodeCacheRef.current.get(String(key));
          if (!node) return null;
          const osType = mapNodeOsType(node.os);
          return {
            name: node.name || node.ip,
            ip: node.ip,
            os_type: osType,
            source_type: 'node_mgmt',
            node_id: String(node.id),
            cloud_region_id: node.cloud_region_id ?? null,
            arch: normalizeArchitecture(node.arch),
            connectivity_status: 'unknown',
            ssh_port: 22,
            winrm_port: 5986,
            winrm_scheme: 'https',
            winrm_transport: 'basic',
          };
        })
        .filter(Boolean) as Partial<PatchTarget>[];
      await api.createPatchTargetBatch(targets);
      message.success(t('patchManager.targetPage.nodesImported', undefined, { count: targets.length }));
      setNodeOpen(false);
      setSelectedNodes([]);
      await loadData(1);
    } catch {
    } finally {
      setActionLoading(false);
    }
  };

  const columns = [
    { title: t('patchManager.targetPage.host'), dataIndex: 'name', width: 110 },
    { title: 'IP', dataIndex: 'ip', width: 120, render: (v: string) => <span style={{ color: 'var(--color-text-3, #8c8c8c)' }}>{v}</span> },
    { title: t('patchManager.osType'), dataIndex: 'os', width: 120 },
    {
      title: t('patchManager.targetPage.source'),
      dataIndex: 'source_type',
      width: 100,
      render: (v: HostRow['source_type']) => t(`patchManager.targetPage.sourceType.${v === 'node_mgmt' ? 'node' : 'manual'}`),
    },
    { title: t('patchManager.targetPage.currentBaseline'), dataIndex: 'baseline', render: (v: string | null) => (v ? v : <span style={{ color: '#d48806' }}>{t('patchManager.baseline.unbound')}</span>) },
    {
      title: t('patchManager.targetPage.complianceStatus'),
      dataIndex: 'compliance',
      width: 130,
      render: (_: unknown, r: HostRow) => {
        const tag = r.compliance === 'failed' && r.complianceFailureReason
          ? <Tooltip title={r.complianceFailureReason}><span><ComplianceTag status={r.compliance} missing={r.missing} /></span></Tooltip>
          : <ComplianceTag status={r.compliance} missing={r.missing} />;
        return r.compliance === 'non_compliant' ? (
          <PermissionWrapper requiredPermissions={['View']}>
            <span
              role="link"
              tabIndex={0}
              style={{ cursor: 'pointer' }}
              onClick={() => router.push(`/patch-manager/risk-pending?host_id=${r.key}&host_name=${encodeURIComponent(r.name)}`)}
              onKeyDown={(event) => event.key === 'Enter' && router.push(`/patch-manager/risk-pending?host_id=${r.key}&host_name=${encodeURIComponent(r.name)}`)}
            >{tag}</span>
          </PermissionWrapper>
        ) : tag;
      },
    },
    { title: t('patchManager.targetPage.lastAssessment'), dataIndex: 'lastEval', width: 170, render: (v: string | null) => convertToLocalizedTime(v) || '—' },
    { title: t('patchManager.connectivity'), dataIndex: 'connectivity', width: 90, render: (v: HostRow['connectivity']) => <ConnTag status={v} /> },
    { title: t('patchManager.targetPage.lastCheck'), dataIndex: 'lastDetected', width: 170, render: (v: string | null) => convertToLocalizedTime(v) || '—' },
    {
      title: t('patchManager.operation'),
      dataIndex: 'op',
      width: 300,
      fixed: 'right' as const,
      render: (_: unknown, r: HostRow) => {
        const blockChangeReason = r.hasActiveTask
          ? t('patchManager.targetPage.activeTaskBlocked')
          : r.hasPendingReboot
            ? t('patchManager.targetPage.pendingRebootBlocked')
            : null;
        const evalDisabledReason = !r.baseline
          ? t('patchManager.targetPage.bindFirst')
          : r.hasActiveTask
            ? t('patchManager.targetPage.activeTask')
            : null;
        const isManual = r.source_type === 'manual';
        return (
          <Space size={10}>
            {isManual ? (
              <PermissionWrapper requiredPermissions={['Edit']} instPermissions={r.permission}><a style={{ color: 'var(--color-primary, #1677ff)' }} onClick={() => {
                const target = data.find((t) => String(t.id) === r.key);
                if (!target) return;
                openManualTarget(target);
              }}><EditOutlined /> {t('patchManager.edit')}</a></PermissionWrapper>
            ) : (
              <Tooltip title={t('patchManager.targetPage.editInNodeManagement')}>
                <span style={{ color: 'var(--color-text-4, #bfbfbf)', cursor: 'not-allowed' }}><EditOutlined /> {t('patchManager.edit')}</span>
              </Tooltip>
            )}
            <PermissionWrapper requiredPermissions={['Edit']} instPermissions={r.permission}><a style={{ color: 'var(--color-primary, #1677ff)' }} onClick={async () => {
              setActionLoading(true);
              try {
                const result = await api.checkPatchTargetConnectivity(Number(r.key));
                if (result.connectivity_status === 'connected') {
                  message.success(result.detail || t('patchManager.targetPage.connectivityCompleted'));
                } else {
                  message.error(result.detail || t('patchManager.targetPage.connectivityCompleted'));
                }
                await loadData();
              } catch {
              } finally {
                setActionLoading(false);
              }
            }}>{t('patchManager.testConnection')}</a></PermissionWrapper>
            {blockChangeReason ? (
              <Tooltip title={blockChangeReason}>
                <span style={{ color: 'var(--color-text-4, #bfbfbf)', cursor: 'not-allowed' }}>{t('patchManager.targetPage.bindBaseline')}</span>
              </Tooltip>
            ) : (
              <PermissionWrapper requiredPermissions={['Edit']} permissionPath="/patch-manager/baseline" instPermissions={r.permission}><a style={{ color: 'var(--color-primary, #1677ff)' }} onClick={() => { setSelectedKeys([r.key]); setBindBaseline(r.baseline_id ?? undefined); setBindOpen(true); }}>
                {t('patchManager.targetPage.bindBaseline')}
              </a></PermissionWrapper>
            )}
            {evalDisabledReason ? (
              <Tooltip title={evalDisabledReason}>
                <span style={{ color: 'var(--color-text-4, #bfbfbf)', cursor: 'not-allowed' }}>{t('patchManager.dashboard.assessNow')}</span>
              </Tooltip>
            ) : (
              <PermissionWrapper requiredPermissions={['Add']} permissionPath="/patch-manager/risk-execution" instPermissions={r.permission}><a style={{ color: 'var(--color-primary, #1677ff)' }} onClick={async () => {
                setActionLoading(true);
                try {
                  await api.createGovernanceTask({
                    name: t('patchManager.targetPage.assessmentName', undefined, { name: r.name }),
                    task_type: 'assess',
                    target_list: [Number(r.key)],
                    execution_mode: 'now',
                  });
                  message.success(t('patchManager.targetPage.assessmentCreated'));
                  await loadData();
                } catch {
                } finally {
                  setActionLoading(false);
                }
              }}>{t('patchManager.dashboard.assessNow')}</a></PermissionWrapper>
            )}
            {blockChangeReason ? (
              <Tooltip title={blockChangeReason}>
                <span style={{ color: 'var(--color-text-4, #bfbfbf)', cursor: 'not-allowed' }}>{t('patchManager.delete')}</span>
              </Tooltip>
            ) : (
              <PermissionWrapper requiredPermissions={['Delete']} instPermissions={r.permission}><Popconfirm title={t('patchManager.targetPage.deleteConfirm')} onConfirm={() => handleDelete(r.key)} okText={t('patchManager.delete')} cancelText={t('patchManager.cancel')}>
                <a style={{ color: '#ff4d4f' }}>{t('patchManager.delete')}</a>
              </Popconfirm></PermissionWrapper>
            )}
          </Space>
        );
      },
    },
  ];

  return (
    <div style={{ background: 'var(--color-bg-1, #fff)', border: '1px solid var(--color-border-1, #e8e8e8)', borderRadius: 10, padding: '16px', flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10, marginBottom: 14 }}>
        <Space>
          <Input.Search
            placeholder="IP"
            style={{ width: 200 }}
            value={ipQuery}
            onChange={(e) => setIpQuery(e.target.value)}
            onSearch={(v) => loadData(1, pagination.pageSize, { ip: v || null })}
            allowClear
          />
          <Select
            placeholder={t('patchManager.targetPage.baseline')}
            style={{ width: 200 }}
            value={baselineFilter}
            onChange={(value) => {
              setBaselineFilter(value);
              syncFilterQuery(value, complianceFilter);
              loadData(1, pagination.pageSize, { baseline_id: value ?? null });
            }}
            allowClear
            showSearch
            virtual
            optionFilterProp="label"
            options={baselines.map((baseline) => ({ label: baseline.name, value: baseline.id }))}
          />
          <Select
            placeholder={t('patchManager.targetPage.complianceStatus')}
            style={{ width: 160 }}
            value={complianceFilter}
            onChange={(v) => {
              setComplianceFilter(v);
              syncFilterQuery(baselineFilter, v);
              loadData(1, pagination.pageSize, { compliance_status: v || null });
            }}
            allowClear
            options={[
              ...(['compliant', 'non_compliant', 'pending', 'evaluating', 'failed', 'unconfigured'] as const).map((value) => ({ label: t(`patchManager.complianceStatus.${value}`), value })),
            ]}
          />
        </Space>
        <Space size={0}>
          <Space size={8}>
            <Tooltip
              title={
                bulkBindDisabled && selectedKeys.length > 0
                  ? t('patchManager.targetPage.bulkBindBlocked')
                  : ''
              }
            >
              <PermissionWrapper requiredPermissions={['Edit']} permissionPath="/patch-manager/baseline"><Button icon={<LinkOutlined />} disabled={bulkBindDisabled} onClick={() => { setBindBaseline(undefined); setBindOpen(true); }}>
                {t('patchManager.targetPage.bulkBind')}{selectedKeys.length ? `(${selectedKeys.length})` : ''}
              </Button></PermissionWrapper>
            </Tooltip>
            <PermissionWrapper requiredPermissions={['Add']}><Button type="primary" icon={<PlusOutlined />} onClick={() => openManualTarget()}>{t('patchManager.targetPage.manualEntry')}</Button></PermissionWrapper>
            <PermissionWrapper requiredPermissions={['Add']}><Button icon={<PlusOutlined />} onClick={() => setNodeOpen(true)}>{t('patchManager.targetPage.nodeImport')}</Button></PermissionWrapper>
          </Space>
          <TimeSelector
            onlyRefresh
            customFrequencyList={pollFrequencyOptions}
            onFrequenceChange={setPollIntervalMs}
            onRefresh={() => loadData()}
          />
        </Space>
      </div>

      <div style={{ flex: 1, minHeight: 0 }}>
        <CustomTable<HostRow>
          columns={columns}
          dataSource={rows}
          rowKey="key"
          loading={listLoading || actionLoading}
          rowSelection={{
            type: 'checkbox',
            selectedRowKeys: selectedKeys,
            onChange: setSelectedKeys,
            getCheckboxProps: (record) => ({ disabled: !record.permission?.includes('Operate') }),
          }}
          scroll={{ x: 1280 }}
          pagination={{
            current: pagination.current,
            pageSize: pagination.pageSize,
            total: pagination.total,
            showSizeChanger: true,
            showTotal: (total) => t('patchManager.common.totalItems', undefined, { count: total }),
            style: { marginBottom: 0 },
            onChange: (page, pageSize) => loadData(page, pageSize),
          }}
        />
      </div>

      <Modal title={t('patchManager.targetPage.bulkBind')} open={bindOpen} onCancel={() => setBindOpen(false)} onOk={handleBind} okText={t('patchManager.confirm')} cancelText={t('patchManager.cancel')} confirmLoading={actionLoading} okButtonProps={{ disabled: !bindBaseline || !baselines.find((item) => item.id === bindBaseline)?.permission?.includes('Operate') }}>
        <p style={{ color: 'var(--color-text-2, #595959)' }}>{t('patchManager.targetPage.bindSelection', undefined, { count: selectedKeys.length })}</p>
        <Select
          style={{ width: '100%' }}
          placeholder={t('patchManager.targetPage.selectBaseline')}
          virtual
          options={baselines.map((b) => ({ label: b.name, value: b.id, disabled: !b.permission?.includes('Operate') }))}
          value={bindBaseline}
          onChange={setBindBaseline}
        />
        <Alert
          style={{ marginTop: 12 }}
          type="warning"
          showIcon
          message={t('patchManager.targetPage.bindHelp')}
        />
      </Modal>

      <Modal
        title={t('patchManager.targetPage.bindAssessmentTitle')}
        open={false}
        onCancel={() => setScanOpen(false)}
        onOk={handleBind}
        okText={t('patchManager.targetPage.bindAndAssess')}
        cancelText={t('patchManager.targetPage.back')}
      >
        <p style={{ color: 'var(--color-text-2, #595959)' }}>
          {t('patchManager.targetPage.assessmentModePrompt', undefined, { count: selectedKeys.length, name: baselines.find((b) => b.id === bindBaseline)?.name || t('patchManager.targetPage.selectedBaseline') })}
        </p>
        <Radio.Group value={scanMethod} onChange={(e) => setScanMethod(e.target.value)} style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 6 }}>
          <Radio value="now">
            <strong>{t('patchManager.targetPage.scanNow')}</strong>
            <div style={{ fontSize: 12, color: 'var(--color-text-3, #8c8c8c)' }}>{t('patchManager.targetPage.scanNowHelp')}</div>
          </Radio>
          <Radio value="cycle">
            <strong>{t('patchManager.targetPage.cycleScan')}</strong>
            <div style={{ fontSize: 12, color: 'var(--color-text-3, #8c8c8c)' }}>{t('patchManager.targetPage.cycleScanHelp')}</div>
          </Radio>
        </Radio.Group>
        <Alert
          style={{ marginTop: 12 }}
          type="warning"
          showIcon
          message={t('patchManager.targetPage.assessmentResetHelp')}
        />
      </Modal>

      <OperateDrawer
        title={editingTarget ? t('patchManager.targetPage.editTarget') : t('patchManager.targetPage.manualEntry')}
        open={manualOpen}
        onClose={() => {
          setManualOpen(false);
          setEditingTarget(null);
          form.resetFields();
          setCred('password');
        }}
        width={520}
        footer={
          <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
            <Button onClick={() => {
              setManualOpen(false);
              setEditingTarget(null);
              form.resetFields();
              setCred('password');
              setConnectivityResult(undefined);
            }}>{t('patchManager.cancel')}</Button>
            <PermissionWrapper requiredPermissions={[editingTarget ? 'Edit' : 'Add']} instPermissions={editingTarget?.permission}>
              <Button loading={testingConnectivity} onClick={handleFormConnectivityTest}>{t('patchManager.testConnection')}</Button>
            </PermissionWrapper>
            <PermissionWrapper requiredPermissions={[editingTarget ? 'Edit' : 'Add']} instPermissions={editingTarget?.permission}>
              <Button type="primary" loading={actionLoading} onClick={handleCreate}>{editingTarget ? t('patchManager.save') : t('patchManager.targetPage.create')}</Button>
            </PermissionWrapper>
          </Space>
        }
      >
        <Form layout="vertical" form={form} style={{ marginTop: 4 }}>
          <Form.Item label={t('patchManager.targetPage.hostName')} name="name" rules={[{ required: true, message: t('patchManager.targetPage.hostNameRequired') }]}><Input placeholder={t('patchManager.targetPage.hostNamePlaceholder')} /></Form.Item>
          <Form.Item label={t('patchManager.targetPage.ipAddress')} name="ip" rules={[{ required: true, message: t('patchManager.targetPage.ipRequired') }]}><Input placeholder={t('patchManager.targetPage.ipPlaceholder')} /></Form.Item>
          <Form.Item label={t('patchManager.osType')} required>
            <Radio.Group value={os} onChange={(e) => setOs(e.target.value)}>
              <Radio value="linux">Linux</Radio>
              <Radio value="win">Windows</Radio>
            </Radio.Group>
          </Form.Item>
          <Form.Item label={t('patchManager.organization')} name="team" rules={[{ required: true, message: t('patchManager.targetPage.organizationRequired') }]}>
            <GroupTreeSelect placeholder={t('patchManager.targetPage.selectOrganization')} />
          </Form.Item>
          <Form.Item label={t('patchManager.targetPage.cloudRegion')} name="cloud_region_id" rules={[{ required: true, message: t('patchManager.targetPage.cloudRegionRequired') }]}>
            <Select
              placeholder={t('patchManager.targetPage.selectCloudRegion')}
              loading={cloudRegionLoading}
              virtual
              options={cloudRegions.map((r) => ({ label: r.display_name || r.name, value: r.id }))}
            />
          </Form.Item>
          {os === 'linux' && (
            <>
              <Space style={{ display: 'flex' }} align="start">
                <Form.Item label={t('patchManager.targetPage.sshPort')} name="ssh_port" initialValue={22}><InputNumber style={{ width: 120 }} /></Form.Item>
                <Form.Item label={t('patchManager.targetPage.sshUser')} name="ssh_user" rules={[{ required: true, message: t('patchManager.targetPage.sshUserRequired') }]} style={{ flex: 1 }}><Input placeholder={t('patchManager.targetPage.sshUserPlaceholder')} style={{ width: 240 }} /></Form.Item>
              </Space>
              <Form.Item label={t('patchManager.targetPage.sshCredential')}>
                <Radio.Group value={cred} onChange={(e) => {
                  setCred(e.target.value);
                  setConnectivityResult(undefined);
                }}>
                  <Radio value="password">{t('patchManager.password')}</Radio>
                  <Radio value="key">{t('patchManager.credentialKey')}</Radio>
                </Radio.Group>
              </Form.Item>
              {cred === 'password' ? (
                <Form.Item
                  label={t('patchManager.targetPage.sshPassword')}
                  name="ssh_password"
                  rules={[{
                    required:
                      !editingTarget?.has_ssh_password
                      || editingTarget?.os_type !== 'linux'
                      || editingCredential !== 'password',
                    message: t('patchManager.targetPage.sshPasswordRequired'),
                  }]}
                >
                  <Password
                    placeholder={t('patchManager.targetPage.sshPasswordRequired')}
                    clickToEdit={Boolean(editingTarget?.has_ssh_password)}
                  />
                </Form.Item>
              ) : (
                <>
                  {keepExistingKey ? (
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16, padding: '8px 12px', border: '1px solid var(--color-border-1, #e8e8e8)', borderRadius: 6 }}>
                      <span>{t('patchManager.targetPage.uploadedKey', undefined, { name: editingTarget?.ssh_key_file_name || t('patchManager.targetPage.privateKeyFile') })}</span>
                      <Button
                        type="text"
                        size="small"
                        aria-label={t('patchManager.targetPage.replaceKey')}
                        icon={<CloseOutlined />}
                        onClick={() => {
                          setKeepExistingKey(false);
                          form.setFieldValue('ssh_key_file', undefined);
                          setConnectivityResult(undefined);
                        }}
                      />
                    </div>
                  ) : (
                    <Form.Item
                      label={t('patchManager.targetPage.sshKeyFile')}
                      name="ssh_key_file"
                      rules={[{ required: true, message: t('patchManager.targetPage.sshKeyRequired') }]}
                    >
                      <Upload.Dragger maxCount={1} beforeUpload={() => false} accept=".pem,.key">
                        <p><InboxOutlined /></p>
                        <p>{t('patchManager.targetPage.sshKeyDrop')}</p>
                      </Upload.Dragger>
                    </Form.Item>
                  )}
                </>
              )}
            </>
          )}

          {os === 'win' && (
            <>
              <Space style={{ display: 'flex' }} align="start">
                <Form.Item label={t('patchManager.winrmPort')} name="winrm_port" rules={[{ required: true, message: t('patchManager.targetPage.winrmPortRequired') }]}><InputNumber style={{ width: 120 }} placeholder="5986" /></Form.Item>
                <Form.Item label={t('patchManager.winrmScheme')} name="winrm_scheme" rules={[{ required: true, message: t('patchManager.targetPage.winrmSchemeRequired') }]}>
                  <Select style={{ width: 120 }} placeholder={t('patchManager.targetPage.select')} options={[{ label: 'https', value: 'https' }, { label: 'http', value: 'http' }]} />
                </Form.Item>
              </Space>
              <Form.Item label={t('patchManager.winrmUser')} name="winrm_user" rules={[{ required: true, message: t('patchManager.targetPage.winrmUserRequired') }]}><Input placeholder={t('patchManager.targetPage.winrmUserPlaceholder')} /></Form.Item>
              <Form.Item label={t('patchManager.targetPage.winrmPassword')} name="winrm_password" rules={[{
                required: !editingTarget?.has_winrm_password || editingTarget?.os_type !== 'windows',
                message: t('patchManager.targetPage.winrmPasswordRequired'),
              }]}>
                <Password
                  placeholder={t('patchManager.targetPage.winrmPasswordRequired')}
                  clickToEdit={Boolean(editingTarget?.has_winrm_password)}
                />
              </Form.Item>
            </>
          )}
          {connectivityResult && (
            <Alert
              key={connectivityResult.checkedAt}
              closable
              showIcon
              type={connectivityResult.status === 'connected' ? 'success' : 'error'}
              message={connectivityResult.status === 'connected' ? t('patchManager.settingsPage.connectivityPassed') : t('patchManager.settingsPage.connectivityFailed')}
              description={`${connectivityResult.detail} · ${convertToLocalizedTime(connectivityResult.checkedAt)}`}
            />
          )}
        </Form>
      </OperateDrawer>

      <OperateDrawer
        title={t('patchManager.targetPage.nodeImport')}
        open={nodeOpen}
        onClose={() => {
          setNodeOpen(false);
          nodeRequestCoordinatorRef.current.invalidate();
          importedNodeRequestCoordinatorRef.current.invalidate();
        }}
        width={720}
        footer={
          <Space>
            <Button onClick={() => {
              setNodeOpen(false);
              nodeRequestCoordinatorRef.current.invalidate();
              importedNodeRequestCoordinatorRef.current.invalidate();
            }}>{t('patchManager.cancel')}</Button>
            <PermissionWrapper requiredPermissions={['Add']}>
              <Button type="primary" loading={actionLoading} onClick={handleNodeSave}>{t('patchManager.save')}</Button>
            </PermissionWrapper>
          </Space>
        }
      >
        <div style={{ fontSize: 12, color: 'var(--color-text-3, #8c8c8c)', marginBottom: 12 }}>
          {t('patchManager.targetPage.nodeImportHelp')}
        </div>
        <Input.Search
          placeholder={t('patchManager.targetPage.searchHost')}
          value={nodeSearch}
          onSearch={(v) => { setNodePagination((p) => ({ ...p, current: 1 })); loadNodeList(1, nodePagination.pageSize, v); }}
          onChange={(e) => setNodeSearch(e.target.value)}
          style={{ marginBottom: 12 }}
          allowClear
        />
        <DualSelector
          rowKey="id"
          dataSource={nodes}
          loading={nodeLoading}
          pagination={{
            current: nodePagination.current,
            pageSize: nodePagination.pageSize,
            total: nodePagination.total,
            showSizeChanger: true,
            showTotal: (total) => t('patchManager.common.totalItems', undefined, { count: total }),
          }}
          onPageChange={(page, pageSize) => loadNodeList(page, pageSize)}
          getCheckboxProps={(record: any) => ({
            disabled: includedNodeIds.has(String(record.id)),
          })}
          columns={[
            { title: t('patchManager.targetPage.host'), dataIndex: 'name', width: 120 },
            { title: 'IP', dataIndex: 'ip', width: 120 },
            { title: 'OS', dataIndex: 'os', width: 100 },
            { title: t('patchManager.arch'), dataIndex: 'arch', width: 90, render: (value: string) => formatArchitecture(value) },
          ]}
          selectedKeys={selectedNodes}
          onChange={setSelectedNodes}
          selectedRecordsData={selectedNodeRecords}
          renderSelectedLabel={(record: any) => `${record.name} (${record.ip})`}
        />
      </OperateDrawer>
    </div>
  );
}
