'use client';

import React, { useState, useEffect, useMemo, useRef } from 'react';
import { Tag, Button, Input, InputNumber, Select, Space, Modal, Form, Radio, Upload, Alert, message, Tooltip, Popconfirm } from 'antd';
import { PlusOutlined, LinkOutlined, EditOutlined, InboxOutlined, CloseOutlined } from '@ant-design/icons';
import PermissionWrapper from '@/components/permission';
import Password from '@/components/password';
import GroupTreeSelect from '@/components/group-tree-select';
import useApiClient from '@/utils/request';
import usePatchManagerApi from '@/app/patch-manager/api';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { PatchTarget, OSType } from '@/app/patch-manager/types';
import ComplianceTag, { ComplianceStatus } from '@/app/patch-manager/components/compliance-tag';
import DualSelector from '@/app/patch-manager/components/dual-selector';
import CustomTable from '@/components/custom-table';
import OperateDrawer from '@/app/patch-manager/components/operate-drawer';
import { useRouter, useSearchParams } from 'next/navigation';
import { buildTargetFilterSearch, parseBaselineFilter } from './filter-state';

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
}

const CONN_TAG: Record<HostRow['connectivity'], { text: string; color: string }> = {
  undetected: { text: '未检测', color: 'default' },
  detecting: { text: '检测中', color: 'processing' },
  connected: { text: '连通', color: 'success' },
  failed: { text: '失败', color: 'error' },
};

function ConnTag({ status }: { status: HostRow['connectivity'] }) {
  const t = CONN_TAG[status];
  return <Tag color={t.color}>{t.text}</Tag>;
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

function mapNodeArch(arch?: string): string {
  if (!arch) return '';
  if (/x86_64|amd64/i.test(arch)) return 'x64';
  if (/aarch64|arm64/i.test(arch)) return 'aarch64';
  return arch;
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
    port: values.ssh_port ?? 22,
    user: values.ssh_user || '',
    credential,
    password: credential === 'password' ? values.ssh_password || '' : '',
    key: credential === 'key' ? keyName : '',
  } : {
    os,
    ip: values.ip || '',
    port: values.winrm_port ?? 5986,
    scheme: values.winrm_scheme || 'https',
    user: values.winrm_user || '',
    password: values.winrm_password || '',
  });
}

export default function TargetPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const api = usePatchManagerApi();
  const { isLoading } = useApiClient();
  const { convertToLocalizedTime } = useLocalizedTime();
  const [data, setData] = useState<PatchTarget[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedKeys, setSelectedKeys] = useState<React.Key[]>([]);
  const [bindOpen, setBindOpen] = useState(false);
  const [scanOpen, setScanOpen] = useState(false);
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
    if (!silent) setLoading(true);
    try {
      const res = await api.getPatchTargetList({
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
      });
      setData(res.items || []);
      setPagination((p) => ({ ...p, current: page, pageSize, total: res.count || 0 }));
    } catch {
      setData([]);
      setPagination((p) => ({ ...p, current: page, pageSize, total: 0 }));
    } finally {
      if (!silent) setLoading(false);
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
    setNodeLoading(true);
    try {
      const res = await api.queryNodes({ page, page_size: pageSize, name: search || undefined });
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
      setNodes([]);
      setNodePagination({ current: page, pageSize, total: 0 });
    } finally {
      setNodeLoading(false);
    }
  };

  const loadImportedNodes = async () => {
    try {
      const res = await api.getImportedNodeIds();
      setImportedNodes(res.items || []);
    } catch {
      setImportedNodes([]);
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

  // 2 秒轮询：弹窗打开时暂停，避免列表刷新影响选择
  const pollingEnabled = !manualOpen && !nodeOpen && !bindOpen && !scanOpen;
  useEffect(() => {
    if (!pollingEnabled) return undefined;
    const timer = setInterval(() => {
      loadData(pagination.current, pagination.pageSize, {}, true);
    }, 2000);
    return () => clearInterval(timer);
  }, [pollingEnabled, pagination.current, pagination.pageSize, ipQuery, baselineFilter, complianceFilter]);

  const rows = useMemo<HostRow[]>(() => data.map((item) => mapTargetToRow(item as PatchTargetItem)), [data]);

  const bulkBindDisabled = useMemo(() => {
    if (selectedKeys.length === 0) return true;
    return selectedKeys.some((key) => {
      const row = rows.find((r) => r.key === String(key));
      return !!row && (row.hasActiveTask || row.hasPendingReboot);
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
    setLoading(true);
    try {
      await api.deletePatchTarget(Number(id));
      message.success('已删除');
      await loadData();
    } catch {
    } finally {
      setLoading(false);
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
    setLoading(true);
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
        message.error('连接参数或凭据已修改，请先完成连通性测试');
        return;
      }

      if (editingTarget) {
        await api.updatePatchTarget(editingTarget.id, formData);
        message.success('目标已更新');
      } else {
        await api.createPatchTarget(formData);
        message.success('目标已保存');
      }
      setManualOpen(false);
      setEditingTarget(null);
      form.resetFields();
      setCred('password');
      await loadData();
    } catch {
    } finally {
      setLoading(false);
    }
  };

  const handleBind = async () => {
    if (!bindBaseline) {
      message.error('请选择基线');
      return;
    }
    const targetIds = selectedKeys.map((k) => Number(k)).filter((id) => !isNaN(id));
    setLoading(true);
    try {
      await api.bindHostsToBaseline(bindBaseline, targetIds);
      message.success('已绑定基线');
      setScanOpen(false);
      setBindOpen(false);
      setBindBaseline(undefined);
      setSelectedKeys([]);
      await loadData();
    } catch {
    } finally {
      setLoading(false);
    }
  };

  const handleNodeSave = async () => {
    if (selectedNodes.length === 0) {
      message.warning('请选择节点');
      return;
    }
    setLoading(true);
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
            arch: mapNodeArch(node.arch),
            connectivity_status: 'unknown',
            ssh_port: 22,
            winrm_port: 5986,
            winrm_scheme: 'https',
            winrm_transport: 'basic',
          };
        })
        .filter(Boolean) as Partial<PatchTarget>[];
      await api.createPatchTargetBatch(targets);
      message.success(`已纳入 ${targets.length} 台节点`);
      setNodeOpen(false);
      setSelectedNodes([]);
      await loadData(1);
    } catch {
    } finally {
      setLoading(false);
    }
  };

  const columns = [
    { title: '主机', dataIndex: 'name', width: 110 },
    { title: 'IP', dataIndex: 'ip', width: 120, render: (v: string) => <span style={{ color: 'var(--color-text-3, #8c8c8c)' }}>{v}</span> },
    { title: '操作系统', dataIndex: 'os', width: 120 },
    {
      title: '来源',
      dataIndex: 'source_type',
      width: 100,
      render: (v: HostRow['source_type']) => (v === 'node_mgmt' ? '节点纳入' : '手动录入'),
    },
    { title: '当前基线', dataIndex: 'baseline', render: (v: string | null) => (v ? v : <span style={{ color: '#d48806' }}>未绑定</span>) },
    {
      title: '合规状态',
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
    { title: '最后评估', dataIndex: 'lastEval', width: 170, render: (v: string | null) => convertToLocalizedTime(v) || '—' },
    { title: '连通性', dataIndex: 'connectivity', width: 90, render: (v: HostRow['connectivity']) => <ConnTag status={v} /> },
    { title: '最后检测', dataIndex: 'lastDetected', width: 170, render: (v: string | null) => convertToLocalizedTime(v) || '—' },
    {
      title: '操作',
      dataIndex: 'op',
      width: 300,
      fixed: 'right' as const,
      render: (_: unknown, r: HostRow) => {
        const blockChangeReason = r.hasActiveTask
          ? '该主机有正在执行的任务，请等待完成或取消后再操作'
          : r.hasPendingReboot
            ? '该主机有待重启补丁，请先完成重启治理后再操作'
            : null;
        const evalDisabledReason = !r.baseline
          ? '请先绑定基线'
          : r.hasActiveTask
            ? '该主机有正在执行的任务'
            : null;
        const isManual = r.source_type === 'manual';
        return (
          <Space size={10}>
            {isManual ? (
              <PermissionWrapper requiredPermissions={['Edit']}><a style={{ color: 'var(--color-primary, #1677ff)' }} onClick={() => {
                const target = data.find((t) => String(t.id) === r.key);
                if (!target) return;
                openManualTarget(target);
              }}><EditOutlined /> 编辑</a></PermissionWrapper>
            ) : (
              <Tooltip title="节点纳入目标请在节点管理编辑">
                <span style={{ color: 'var(--color-text-4, #bfbfbf)', cursor: 'not-allowed' }}><EditOutlined /> 编辑</span>
              </Tooltip>
            )}
            <PermissionWrapper requiredPermissions={['Edit']}><a style={{ color: 'var(--color-primary, #1677ff)' }} onClick={async () => {
              setLoading(true);
              try {
                await api.checkPatchTargetConnectivity(Number(r.key));
                message.success('连通性检测完成');
                await loadData();
              } catch {
              } finally {
                setLoading(false);
              }
            }}>测试连通性</a></PermissionWrapper>
            {blockChangeReason ? (
              <Tooltip title={blockChangeReason}>
                <span style={{ color: 'var(--color-text-4, #bfbfbf)', cursor: 'not-allowed' }}>绑基线</span>
              </Tooltip>
            ) : (
              <PermissionWrapper requiredPermissions={['Edit']}><a style={{ color: 'var(--color-primary, #1677ff)' }} onClick={() => { setSelectedKeys([r.key]); setBindBaseline(r.baseline_id ?? undefined); setBindOpen(true); }}>
                绑基线
              </a></PermissionWrapper>
            )}
            {evalDisabledReason ? (
              <Tooltip title={evalDisabledReason}>
                <span style={{ color: 'var(--color-text-4, #bfbfbf)', cursor: 'not-allowed' }}>立即评估</span>
              </Tooltip>
            ) : (
              <PermissionWrapper requiredPermissions={['Add']}><a style={{ color: 'var(--color-primary, #1677ff)' }} onClick={async () => {
                setLoading(true);
                try {
                  await api.createGovernanceTask({
                    name: `评估 - ${r.name}`,
                    task_type: 'assess',
                    target_list: [Number(r.key)],
                    execution_mode: 'now',
                  });
                  message.success('已创建评估任务');
                  await loadData();
                } catch {
                } finally {
                  setLoading(false);
                }
              }}>立即评估</a></PermissionWrapper>
            )}
            {blockChangeReason ? (
              <Tooltip title={blockChangeReason}>
                <span style={{ color: 'var(--color-text-4, #bfbfbf)', cursor: 'not-allowed' }}>删除</span>
              </Tooltip>
            ) : (
              <PermissionWrapper requiredPermissions={['Delete']}><Popconfirm title="确定删除该目标主机？" onConfirm={() => handleDelete(r.key)} okText="删除" cancelText="取消">
                <a style={{ color: '#ff4d4f' }}>删除</a>
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
            placeholder="基线"
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
            placeholder="合规状态"
            style={{ width: 160 }}
            value={complianceFilter}
            onChange={(v) => {
              setComplianceFilter(v);
              syncFilterQuery(baselineFilter, v);
              loadData(1, pagination.pageSize, { compliance_status: v || null });
            }}
            allowClear
            options={[
              { label: '合规', value: 'compliant' },
              { label: '不合规', value: 'non_compliant' },
              { label: '待评估', value: 'pending' },
              { label: '评估中', value: 'evaluating' },
              { label: '评估失败', value: 'failed' },
              { label: '未配置', value: 'unconfigured' },
            ]}
          />
        </Space>
        <Space>
          <Tooltip
            title={
              bulkBindDisabled && selectedKeys.length > 0
                ? '选中主机存在正在执行的任务或待重启状态，请先处理后再绑定基线'
                : ''
            }
          >
            <PermissionWrapper requiredPermissions={['Edit']}><Button icon={<LinkOutlined />} disabled={bulkBindDisabled} onClick={() => { setBindBaseline(undefined); setBindOpen(true); }}>
              批量绑定基线{selectedKeys.length ? `(${selectedKeys.length})` : ''}
            </Button></PermissionWrapper>
          </Tooltip>
          <PermissionWrapper requiredPermissions={['Add']}><Button type="primary" icon={<PlusOutlined />} onClick={() => openManualTarget()}>手动录入</Button></PermissionWrapper>
          <PermissionWrapper requiredPermissions={['Add']}><Button icon={<PlusOutlined />} onClick={() => setNodeOpen(true)}>节点纳入</Button></PermissionWrapper>
        </Space>
      </div>

      <div style={{ flex: 1, minHeight: 0 }}>
        <CustomTable<HostRow>
          columns={columns}
          dataSource={rows}
          rowKey="key"
          loading={loading}
          rowSelection={{ type: 'checkbox', selectedRowKeys: selectedKeys, onChange: setSelectedKeys }}
          scroll={{ x: 1280 }}
          pagination={{
            current: pagination.current,
            pageSize: pagination.pageSize,
            total: pagination.total,
            showSizeChanger: true,
            showTotal: (t) => `共 ${t} 条`,
            style: { marginBottom: 0 },
            onChange: (page, pageSize) => loadData(page, pageSize),
          }}
        />
      </div>

      <Modal title="批量绑定基线" open={bindOpen} onCancel={() => setBindOpen(false)} onOk={handleBind} okText="确认" cancelText="取消" confirmLoading={loading}>
        <p style={{ color: 'var(--color-text-2, #595959)' }}>已选 {selectedKeys.length} 台主机,选择要绑定的<strong>唯一基线</strong>:</p>
        <Select
          style={{ width: '100%' }}
          placeholder="选择基线"
          virtual
          options={baselines.map((b) => ({ label: b.name, value: b.id }))}
          value={bindBaseline}
          onChange={setBindBaseline}
        />
        <Alert
          style={{ marginTop: 12 }}
          type="warning"
          showIcon
          message="每台主机仅能绑定一个基线;已绑定的将被替换。绑定后主机进入「待评估」,可在首页点击「立即评估」或在全局周期自动评估。"
        />
      </Modal>

      <Modal
        title="绑定确认 · 评估方式"
        open={false}
        onCancel={() => setScanOpen(false)}
        onOk={handleBind}
        okText="确认绑定并评估"
        cancelText="返回"
      >
        <p style={{ color: 'var(--color-text-2, #595959)' }}>
          将把 <strong>{selectedKeys.length}</strong> 台主机绑定到 <strong>{baselines.find((b) => b.id === bindBaseline)?.name || '所选基线'}</strong>,这些主机将进入「待评估」。选择评估方式:
        </p>
        <Radio.Group value={scanMethod} onChange={(e) => setScanMethod(e.target.value)} style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 6 }}>
          <Radio value="now">
            <strong>立即扫描</strong>
            <div style={{ fontSize: 12, color: 'var(--color-text-3, #8c8c8c)' }}>立即创建评估任务,马上看到合规变化</div>
          </Radio>
          <Radio value="cycle">
            <strong>按周期扫描</strong>
            <div style={{ fontSize: 12, color: 'var(--color-text-3, #8c8c8c)' }}>按「设置·扫描设置」的全局周期评估,无需在此设时间</div>
          </Radio>
        </Radio.Group>
        <Alert
          style={{ marginTop: 12 }}
          type="warning"
          showIcon
          message="无论哪种方式,这些主机立即进入「待评估」,旧评估结果过期、不再计入合规率。"
        />
      </Modal>

      <OperateDrawer
        title={editingTarget ? '编辑目标' : '手动录入'}
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
            }}>取消</Button>
            <PermissionWrapper requiredPermissions={[editingTarget ? 'Edit' : 'Add']}>
              <Button loading={testingConnectivity} onClick={handleFormConnectivityTest}>测试连通性</Button>
            </PermissionWrapper>
            <PermissionWrapper requiredPermissions={[editingTarget ? 'Edit' : 'Add']}>
              <Button type="primary" loading={loading} onClick={handleCreate}>{editingTarget ? '保存' : '创建'}</Button>
            </PermissionWrapper>
          </Space>
        }
      >
        <Form layout="vertical" form={form} style={{ marginTop: 4 }}>
          <Form.Item label="主机名" name="name" rules={[{ required: true, message: '请输入主机名' }]}><Input placeholder="如 web-03" /></Form.Item>
          <Form.Item label="IP 地址" name="ip" rules={[{ required: true, message: '请输入 IP 地址' }]}><Input placeholder="如 10.0.1.30" /></Form.Item>
          <Form.Item label="操作系统" required>
            <Radio.Group value={os} onChange={(e) => setOs(e.target.value)}>
              <Radio value="linux">Linux</Radio>
              <Radio value="win">Windows</Radio>
            </Radio.Group>
          </Form.Item>
          <Form.Item label="组织" name="team" rules={[{ required: true, message: '请选择组织' }]}>
            <GroupTreeSelect placeholder="选择组织" />
          </Form.Item>
          <Form.Item label="云区域" name="cloud_region_id" rules={[{ required: true, message: '请选择云区域' }]}>
            <Select
              placeholder="选择云区域"
              loading={cloudRegionLoading}
              virtual
              options={cloudRegions.map((r) => ({ label: r.display_name || r.name, value: r.id }))}
            />
          </Form.Item>
          <Form.Item label="执行驱动"><Input value="Ansible" disabled /></Form.Item>

          {os === 'linux' && (
            <>
              <Space style={{ display: 'flex' }} align="start">
                <Form.Item label="SSH 端口" name="ssh_port" initialValue={22}><InputNumber style={{ width: 120 }} /></Form.Item>
                <Form.Item label="SSH 用户名" name="ssh_user" rules={[{ required: true, message: '请输入 SSH 用户名' }]} style={{ flex: 1 }}><Input placeholder="如 root" style={{ width: 240 }} /></Form.Item>
              </Space>
              <Form.Item label="SSH 凭据">
                <Radio.Group value={cred} onChange={(e) => {
                  setCred(e.target.value);
                  setConnectivityResult(undefined);
                }}>
                  <Radio value="password">密码</Radio>
                  <Radio value="key">密钥</Radio>
                </Radio.Group>
              </Form.Item>
              {cred === 'password' ? (
                <Form.Item
                  label="SSH 密码"
                  name="ssh_password"
                  rules={[{
                    required:
                      !editingTarget?.has_ssh_password
                      || editingTarget?.os_type !== 'linux'
                      || editingCredential !== 'password',
                    message: '请输入 SSH 密码',
                  }]}
                >
                  <Password
                    placeholder="请输入 SSH 密码"
                    clickToEdit={Boolean(editingTarget?.has_ssh_password)}
                  />
                </Form.Item>
              ) : (
                <>
                  {keepExistingKey ? (
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16, padding: '8px 12px', border: '1px solid var(--color-border-1, #e8e8e8)', borderRadius: 6 }}>
                      <span>已上传私钥：{editingTarget?.ssh_key_file_name || '私钥文件'}</span>
                      <Button
                        type="text"
                        size="small"
                        aria-label="替换私钥"
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
                      label="SSH 私钥文件"
                      name="ssh_key_file"
                      rules={[{ required: true, message: '请上传 SSH 私钥文件' }]}
                    >
                      <Upload.Dragger maxCount={1} beforeUpload={() => false} accept=".pem,.key">
                        <p><InboxOutlined /></p>
                        <p>点击或拖拽私钥文件到此处</p>
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
                <Form.Item label="WinRM 端口" name="winrm_port" rules={[{ required: true, message: '请输入 WinRM 端口' }]}><InputNumber style={{ width: 120 }} placeholder="5986" /></Form.Item>
                <Form.Item label="WinRM 协议" name="winrm_scheme" rules={[{ required: true, message: '请选择 WinRM 协议' }]}>
                  <Select style={{ width: 120 }} placeholder="请选择" options={[{ label: 'https', value: 'https' }, { label: 'http', value: 'http' }]} />
                </Form.Item>
              </Space>
              <Form.Item label="WinRM 用户名" name="winrm_user" rules={[{ required: true, message: '请输入 WinRM 用户名' }]}><Input placeholder="如 Administrator" /></Form.Item>
              <Form.Item label="WinRM 密码" name="winrm_password" rules={[{
                required: !editingTarget?.has_winrm_password || editingTarget?.os_type !== 'windows',
                message: '请输入 WinRM 密码',
              }]}>
                <Password
                  placeholder="请输入 WinRM 密码"
                  clickToEdit={Boolean(editingTarget?.has_winrm_password)}
                />
              </Form.Item>
            </>
          )}
          {connectivityResult && (
            <Alert
              showIcon
              type={connectivityResult.status === 'connected' ? 'success' : 'error'}
              message={connectivityResult.status === 'connected' ? '连通性测试通过' : '连通性测试失败'}
              description={`${connectivityResult.detail} · ${convertToLocalizedTime(connectivityResult.checkedAt)}`}
            />
          )}
        </Form>
      </OperateDrawer>

      <OperateDrawer
        title="节点纳入"
        open={nodeOpen}
        onClose={() => setNodeOpen(false)}
        width={720}
        footer={
          <Space>
            <Button onClick={() => setNodeOpen(false)}>取消</Button>
            <Button type="primary" loading={loading} onClick={handleNodeSave}>保存</Button>
          </Space>
        }
      >
        <div style={{ fontSize: 12, color: 'var(--color-text-3, #8c8c8c)', marginBottom: 12 }}>
          节点管理节点复用平台已有连接，执行驱动同为 Ansible，经 NATS/执行器治理。
        </div>
        <Input.Search
          placeholder="搜索主机名 / IP"
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
            showTotal: (t) => `共 ${t} 条`,
          }}
          onPageChange={(page, pageSize) => loadNodeList(page, pageSize)}
          getCheckboxProps={(record: any) => ({
            disabled: includedNodeIds.has(String(record.id)),
          })}
          columns={[
            { title: '主机', dataIndex: 'name', width: 120 },
            { title: 'IP', dataIndex: 'ip', width: 120 },
            { title: 'OS', dataIndex: 'os', width: 100 },
            { title: '架构', dataIndex: 'arch', width: 90 },
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
