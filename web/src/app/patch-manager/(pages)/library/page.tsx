'use client';

import React, { useState, useEffect, useMemo } from 'react';
import { Tag, Button, Input, Select, Space, Tabs, Modal, Form, message, Tooltip, Popconfirm, Upload } from 'antd';
import PermissionWrapper from '@/components/permission';
import type { ColumnsType } from 'antd/es/table';
import { PlusOutlined, CloudDownloadOutlined, EditOutlined, DeleteOutlined, CloseOutlined, InboxOutlined, UploadOutlined } from '@ant-design/icons';
import SearchCombination from '@/components/search-combination';
import type { FieldConfig, SearchFilters } from '@/components/search-combination/types';
import useApiClient from '@/utils/request';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import usePatchManagerApi from '@/app/patch-manager/api';
import type { Patch, PatchSeverity, OSType, PackageStatus, PatchParams, CandidateItem, PatchSource, IngestResult } from '@/app/patch-manager/types';
import SeverityTag from '@/app/patch-manager/components/severity-tag';
import ReadyTag from '@/app/patch-manager/components/ready-tag';
import CustomTable from '@/components/custom-table';
import OperateDrawer from '@/app/patch-manager/components/operate-drawer';
import { getWindowsPackageUploadState } from '@/app/patch-manager/components/windows-package-upload-state';

type TabKey = 'win' | 'linux';
type SourceType = 'auto' | 'manual';

const OS_TYPE_MAP: Record<TabKey, OSType> = {
  win: 'windows',
  linux: 'linux',
};

const SEVERITY_OPTIONS = [
  { id: 'critical', name: '严重' },
  { id: 'important', name: '重要' },
  { id: 'moderate', name: '中等' },
  { id: 'low', name: '低' },
  { id: 'unspecified', name: '未指定' },
];

const READY_OPTIONS = [
  { id: 'ready', name: '就绪' },
  { id: 'processing', name: '处理中' },
  { id: 'action_required', name: '需处理' },
  { id: 'unavailable', name: '不可用' },
];

const ARCH_OPTIONS = [
  { id: 'x64', name: 'x64' },
  { id: 'x86', name: 'x86' },
  { id: 'arm64', name: 'arm64' },
];

function mapPkgStatus(pkgStatus?: string): string {
  switch (pkgStatus) {
    case 'ready':
      return 'ready';
    case 'downloading':
    case 'pending':
      return 'processing';
    case 'download_failed':
      return 'action_required';
    default:
      return 'unavailable';
  }
}

function getSourceType(patch: Patch): SourceType {
  return patch.sources.length > 0 ? 'auto' : 'manual';
}

function getSourceLabel(patch: Patch): string {
  switch (patch.source_type) {
    case 'wsus':
      return 'WSUS';
    case 'yum_repo':
      return 'yum';
    case 'dnf_repo':
      return 'dnf';
    case 'apt_repo':
      return 'apt';
    case null:
    case undefined:
      return '手动';
    default:
      return patch.source_type;
  }
}

function getPatchName(patch: Patch): string {
  if (patch.os_type === 'windows') {
    return patch.windows_detail?.kb_number || patch.title || '—';
  }
  return patch.linux_detail?.pkg_name || patch.title || '—';
}

function getPatchVersion(patch: Patch): string {
  if (patch.os_type === 'windows') {
    return (patch.windows_detail?.product_list || []).join('、') || '—';
  }
  return patch.linux_detail?.distro_name || '—';
}

function getPatchArch(patch: Patch): string {
  const archs = patch.os_type === 'windows'
    ? patch.windows_detail?.architectures
    : patch.linux_detail?.architectures;
  return (archs || []).join('、') || '—';
}

export default function LibraryPage() {
  const api = usePatchManagerApi();
  const { isLoading } = useApiClient();
  const { convertToLocalizedTime } = useLocalizedTime();
  const [activeTab, setActiveTab] = useState<TabKey>('win');
  const [data, setData] = useState<Patch[]>([]);
  const [loading, setLoading] = useState(false);
  const [filters, setFilters] = useState<SearchFilters>({});
  const [createOpen, setCreateOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [candidateSearch, setCandidateSearch] = useState('');
  const [selectedCandidates, setSelectedCandidates] = useState<React.Key[]>([]);
  const [editingPatch, setEditingPatch] = useState<Patch | null>(null);
  const [createForm] = Form.useForm();
  const [editForm] = Form.useForm();
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20, total: 0 });

  // 同步入库抽屉
  const [sources, setSources] = useState<PatchSource[]>([]);
  const [selectedSourceId, setSelectedSourceId] = useState<number | null>(null);
  const [candidateData, setCandidateData] = useState<CandidateItem[]>([]);
  const [candidateLoading, setCandidateLoading] = useState(false);
  const [candidatePagination, setCandidatePagination] = useState({ current: 1, pageSize: 20, total: 0 });
  const [candidateSeverity, setCandidateSeverity] = useState<Record<string, string>>({});
  const [batchSeverityOpen, setBatchSeverityOpen] = useState(false);
  const [batchSeverityValue, setBatchSeverityValue] = useState<string | undefined>(undefined);

  const SEVERITY_SELECT_OPTIONS = [
    { label: '严重', value: 'critical' },
    { label: '重要', value: 'important' },
    { label: '中等', value: 'moderate' },
    { label: '低', value: 'low' },
  ];

  const buildParams = (page: number, pageSize: number, currentFilters: SearchFilters): PatchParams => {
    const params: PatchParams = {
      page,
      page_size: pageSize,
      os_type: activeTab === 'win' ? 'windows' : 'linux',
    };
    Object.entries(currentFilters).forEach(([key, conds]) => {
      conds.forEach((c) => {
        if (c.lookup_expr === 'icontains') {
          if (key === 'name') params.name = String(c.value);
          else if (key === 'title') params.search = String(c.value);
          else if (key === 'version') params.version = String(c.value);
        } else if (c.lookup_expr === 'in') {
          const arr = c.value as string[];
          if (arr.length === 0) return;
          if (key === 'severity') params.severity = arr[0] as PatchSeverity;
          else if (key === 'ready') params.pkg_status = arr[0] as PackageStatus;
          else if (key === 'arch') params.arch = arr[0];
          else if (key === 'version') params.version = arr[0];
          else if (key === 'sourceType') params.source_isnull = arr[0] === 'manual';
        }
      });
    });
    return params;
  };

  const loadData = async (page?: number, pageSize?: number, currentFilters?: SearchFilters) => {
    setLoading(true);
    const requestedTab = activeTab;
    const targetPage = page ?? pagination.current;
    const targetSize = pageSize ?? pagination.pageSize;
    const targetFilters = currentFilters ?? filters;
    try {
      const res = await api.getPatchList(buildParams(targetPage, targetSize, targetFilters));
      if (requestedTab === activeTab) {
        setData(res.items || []);
        setPagination((p) => ({ ...p, current: targetPage, pageSize: targetSize, total: res.count || 0 }));
      }
    } catch {
      if (requestedTab === activeTab) {
        setData([]);
        setPagination((p) => ({ ...p, current: targetPage, pageSize: targetSize, total: 0 }));
      }
    } finally {
      if (requestedTab === activeTab) {
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    if (isLoading) return;
    setPagination((p) => ({ ...p, current: 1 }));
    loadData(1, pagination.pageSize, filters);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLoading, activeTab]);

  const hasProcessingPackage = data.some((patch) => patch.pkg_status === 'downloading');
  useEffect(() => {
    if (!hasProcessingPackage) return;
    const timer = window.setInterval(() => loadData(), 2000);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasProcessingPackage, activeTab, pagination.current, pagination.pageSize, filters]);

  const editPackageUploadState = useMemo(
    () => getWindowsPackageUploadState(editingPatch),
    [editingPatch],
  );

  const editInitialValues = useMemo(() => {
    if (!editingPatch) return {};
    const base = { title: editingPatch.title, severity: editingPatch.severity };
    if (activeTab === 'win') {
      return {
        ...base,
        version: (editingPatch.windows_detail?.product_list || []).join('、') || '',
        arch: (editingPatch.windows_detail?.architectures || [])[0] || '',
        package_file: getWindowsPackageUploadState(editingPatch).fileList,
      };
    }
    return {
      ...base,
      minVer: editingPatch.linux_detail?.pkg_version || '',
      dist: editingPatch.linux_detail?.distro_name || '',
      arch: (editingPatch.linux_detail?.architectures || [])[0] || '',
    };
  }, [editingPatch, activeTab]);

  const winFieldConfigs: FieldConfig[] = [
    { name: 'name', label: 'KB 号', lookup_expr: 'icontains' },
    { name: 'title', label: '描述', lookup_expr: 'icontains' },
    { name: 'version', label: '适用版本', lookup_expr: 'icontains', options: [{ id: '2019', name: '2019' }, { id: '2022', name: '2022' }, { id: '2008', name: '2008' }] },
    { name: 'arch', label: '架构', lookup_expr: 'in', options: ARCH_OPTIONS },
    { name: 'severity', label: '严重级别', lookup_expr: 'in', options: SEVERITY_OPTIONS },
    { name: 'ready', label: '就绪状态', lookup_expr: 'in', options: READY_OPTIONS },
    { name: 'sourceType', label: '来源类型', lookup_expr: 'in', options: [{ id: 'auto', name: '自动' }, { id: 'manual', name: '手动' }] },
  ];

  const linuxFieldConfigs: FieldConfig[] = [
    { name: 'name', label: '包名', lookup_expr: 'icontains' },
    { name: 'title', label: '描述', lookup_expr: 'icontains' },
    { name: 'version', label: '发行版', lookup_expr: 'in', options: [{ id: 'Rocky 8', name: 'Rocky 8' }, { id: 'Rocky 9', name: 'Rocky 9' }, { id: 'CentOS 7', name: 'CentOS 7' }] },
    { name: 'arch', label: '架构', lookup_expr: 'in', options: ARCH_OPTIONS },
    { name: 'severity', label: '严重级别', lookup_expr: 'in', options: SEVERITY_OPTIONS },
    { name: 'ready', label: '就绪状态', lookup_expr: 'in', options: READY_OPTIONS },
    { name: 'sourceType', label: '来源类型', lookup_expr: 'in', options: [{ id: 'auto', name: '自动' }, { id: 'manual', name: '手动' }] },
  ];

  const handleDelete = async (row: Patch) => {
    try {
      await api.deletePatch(row.id);
      message.success('已删除');
      loadData();
    } catch {
    }
  };

  const columns: ColumnsType<Patch> = useMemo(() => {
    const isWin = activeTab === 'win';
    return [
      { title: isWin ? 'KB 号' : '包名', dataIndex: 'name', width: 120, render: (_: unknown, r: Patch) => getPatchName(r) },
      { title: '描述', dataIndex: 'title', ellipsis: true },
      { title: '严重级别', dataIndex: 'severity', width: 100, render: (v: PatchSeverity) => <SeverityTag severity={v} /> },
      { title: isWin ? '适用版本' : '发行版', dataIndex: 'version', width: 140, render: (_: unknown, r: Patch) => getPatchVersion(r) },
      { title: '架构', dataIndex: 'arch', width: 100, render: (_: unknown, r: Patch) => getPatchArch(r) },
      { title: '来源', dataIndex: 'sources', width: 120, render: (_: unknown, r: Patch) => <span style={{ color: '#8c8c8c' }}>{getSourceLabel(r)}</span> },
      { title: '来源类型', dataIndex: 'sourceType', width: 100, render: (_: unknown, r: Patch) => {
        const t = getSourceType(r);
        return <Tag color={t === 'auto' ? 'default' : 'warning'}>{t === 'auto' ? '自动' : '手动'}</Tag>;
      }},
      { title: '就绪状态', dataIndex: 'pkg_status', width: 120, render: (_: unknown, r: Patch) => <ReadyTag status={mapPkgStatus(r.pkg_status)} /> },
      { title: '被基线引用', dataIndex: 'baseline_requirement_count', width: 110, render: (v: number) => <span style={{ color: '#bfbfbf' }}>{v ?? 0}</span> },
      { title: '最近更新', dataIndex: 'last_synced_at', width: 180, render: (v: string | null, r: Patch) => convertToLocalizedTime(v || r.updated_at) || '—' },
      { title: '操作', dataIndex: 'op', width: 180, fixed: 'right', render: (_: unknown, r: Patch) => (
        <Space size={12}>
          <PermissionWrapper requiredPermissions={['Edit']}><a style={{ color: '#1677ff' }} onClick={() => setEditingPatch(r)}><EditOutlined /> 编辑</a></PermissionWrapper>
          <PermissionWrapper requiredPermissions={['Delete']}><Popconfirm title="确定删除该补丁？" onConfirm={() => handleDelete(r)} okText="删除" cancelText="取消">
            <a style={{ color: '#ff4d4f' }}><DeleteOutlined /> 删除</a>
          </Popconfirm></PermissionWrapper>
        </Space>
      )},
    ];
  }, [activeTab]);

  const handleCreateSubmit = async () => {
    let values;
    try {
      values = await createForm.validateFields();
    } catch (err: any) {
      if (err?.errorFields) return;
      message.error('表单校验失败');
      return;
    }
    const osType = OS_TYPE_MAP[activeTab];
    const patchPayload: Partial<Patch> = {
      title: values.desc || '',
      os_type: osType,
      severity: values.severity,
      patch_type: 'security',
    };
    if (activeTab === 'win') {
      patchPayload.windows_detail = {
        kb_number: values.name || '',
        product_list: values.version ? [values.version] : [],
        architectures: values.arch ? [values.arch] : [],
        ms_bulletin: '',
      };
    } else {
      patchPayload.linux_detail = {
        pkg_name: values.name || '',
        pkg_version: values.minVer || '',
        distro_name: values.dist || '',
        os_version_range: '',
        architectures: values.arch ? [values.arch] : [],
        repo_type: 'yum',
      };
    }

    try {
      const created = await api.createPatch(patchPayload);
      createForm.resetFields();
      setCreateOpen(false);
      loadData(1);
      if (activeTab === 'win') {
        const file = values.package_file?.[0]?.originFileObj as File | undefined;
        if (file) {
          message.success('补丁记录已创建，补丁包正在处理中');
          void api.uploadWindowsPatchPackage(created.id, file)
            .then(() => {
              message.success('补丁包上传完成');
              loadData(1);
            })
            .catch(() => loadData(1));
        }
      } else {
        message.success('新增成功');
      }
    } catch {
    }
  };

  const loadSources = async () => {
    try {
      const res = await api.getPatchSourceList({ page: 1, page_size: -1, is_enabled: true });
      const items = Array.isArray(res) ? res : (res.items || []);
      const osType = OS_TYPE_MAP[activeTab];
      const filtered = items.filter((s: PatchSource) =>
        s.source_type === 'wsus' ? osType === 'windows' : osType === 'linux'
      );
      setSources(filtered);
      if (filtered.length > 0) {
        handleSourceChange(filtered[0].id);
      } else {
        setSelectedSourceId(null);
        setCandidateData([]);
      }
    } catch {
    }
  };

  const loadCandidates = async (sourceId: number, page = 1, pageSize = 20, search = '') => {
    setCandidateLoading(true);
    try {
      const res = await api.previewSyncPatchSource(sourceId, { search, page, page_size: pageSize });
      const items = res.items || [];
      setCandidateData(items);
      setCandidatePagination({ current: res.page || page, pageSize: res.page_size || pageSize, total: res.total || 0 });
      // 初始化严重级别：有值且能识别的用实际值，否则默认「中等」
      const sevMap: Record<string, string> = {};
      const validSeverities = ['critical', 'important', 'moderate', 'low'];
      items.forEach((c: CandidateItem) => {
        if (c.severity) {
          const lower = c.severity.toLowerCase();
          if (validSeverities.includes(lower)) {
            sevMap[c.key] = lower;
          }
        }
        if (!sevMap[c.key]) {
          sevMap[c.key] = 'moderate';
        }
      });
      setCandidateSeverity(sevMap);
    } catch {
      setCandidateData([]);
      setCandidatePagination({ current: 1, pageSize: 20, total: 0 });
    } finally {
      setCandidateLoading(false);
    }
  };

  const handleImportSearch = () => {
    setImportOpen(true);
    setSelectedCandidates([]);
    setCandidateSearch('');
    setCandidateData([]);
    setCandidatePagination({ current: 1, pageSize: 10, total: 0 });
    setSelectedSourceId(null);
    loadSources();
  };

  const handleSourceChange = (id: number) => {
    setSelectedSourceId(id);
    setSelectedCandidates([]);
    setCandidateSearch('');
    loadCandidates(id, 1, candidatePagination.pageSize);
  };

  const handleCandidateSearch = (value: string) => {
    setCandidateSearch(value);
    if (selectedSourceId) {
      loadCandidates(selectedSourceId, 1, candidatePagination.pageSize, value);
    }
  };

  const isAsyncIngestResult = (res: IngestResult): res is { accepted: true; task_id: string } =>
    'accepted' in res && res.accepted === true;

  const handleImportSubmit = async () => {
    if (!selectedSourceId || selectedCandidates.length === 0) return;
    setCandidateLoading(true);
    try {
      const severityOverrides: Record<string, string> = {};
      selectedCandidates.forEach((k) => {
        const sev = candidateSeverity[String(k)];
        if (sev) severityOverrides[String(k)] = sev;
      });
      const res = await api.ingestPatchSource(selectedSourceId, selectedCandidates.map(String), severityOverrides);
      if (isAsyncIngestResult(res)) {
        message.success('已提交后台入库任务，完成后补丁状态将自动更新');
      } else {
        message.success(`入库完成：新增 ${res.created}，更新 ${res.updated}`);
      }
      setImportOpen(false);
      setSelectedCandidates([]);
      setCandidateSearch('');
      loadData(1);
    } catch {
    } finally {
      setCandidateLoading(false);
    }
  };

  const handleSingleIngest = async (item: CandidateItem) => {
    if (!selectedSourceId) return;
    try {
      const severityOverrides: Record<string, string> = {};
      const sev = candidateSeverity[item.key];
      if (sev) severityOverrides[item.key] = sev;
      const res = await api.ingestPatchSource(selectedSourceId, [item.key], severityOverrides);
      if (isAsyncIngestResult(res)) {
        message.success('已提交后台入库任务，完成后补丁状态将自动更新');
      } else {
        message.success(`入库完成：新增 ${res.created}，更新 ${res.updated}`);
        setCandidateData((prev) => prev.map((c) => c.key === item.key ? { ...c, added: true } : c));
      }
      loadData();
    } catch {
    }
  };

  const candidateColumns: ColumnsType<CandidateItem> = [
    { title: activeTab === 'win' ? 'KB 号' : '包名', dataIndex: 'name', width: 130 },
    {
      title: () => (
        <span>
          严重级别
          <Tooltip title="批量修改严重级别">
            <EditOutlined
              style={{ marginLeft: 6, cursor: 'pointer', color: 'var(--color-primary, #1677ff)' }}
              onClick={() => {
                setBatchSeverityValue(undefined);
                setBatchSeverityOpen(true);
              }}
            />
          </Tooltip>
        </span>
      ),
      dataIndex: 'severity',
      width: 130,
      render: (_: unknown, r: CandidateItem) => (
        <Select
          size="small"
          value={candidateSeverity[r.key]}
          onChange={(v) => setCandidateSeverity((prev) => ({ ...prev, [r.key]: v }))}
          options={SEVERITY_SELECT_OPTIONS}
          style={{ width: 100 }}
        />
      ),
    },
    { title: '描述', dataIndex: 'title', ellipsis: true },
    ...(activeTab === 'win'
      ? [{ title: '适用版本', dataIndex: 'version', width: 100 }, { title: '架构', dataIndex: 'arch', width: 80 }]
      : [{ title: '发行版', dataIndex: 'dist', width: 100 }, { title: '架构', dataIndex: 'arch', width: 80 }]),
    { title: '操作', dataIndex: 'op', width: 90, fixed: 'right', render: (_: unknown, r: CandidateItem) => (
      r.added
        ? <Button type="link" disabled>已入库</Button>
        : <Button type="link" onClick={() => handleSingleIngest(r)}>入库</Button>
    )},
  ];

  const selectedItems = candidateData.filter((c) => selectedCandidates.includes(c.key));

  return (
    <div style={{ background: 'var(--color-bg-1, #fff)', border: '1px solid var(--color-border-1, #e8e8e8)', borderRadius: 10, padding: '16px', flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
      <Tabs activeKey={activeTab} onChange={(k) => setActiveTab(k as TabKey)} items={[
        { key: 'win', label: 'Windows', children: null },
        { key: 'linux', label: 'Linux', children: null },
      ]} />

      <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10, marginBottom: 12 }}>
        <SearchCombination
          fieldConfigs={activeTab === 'win' ? winFieldConfigs : linuxFieldConfigs}
          onChange={(next) => {
            setFilters(next);
            setPagination((p) => ({ ...p, current: 1 }));
            loadData(1, pagination.pageSize, next);
          }}
          fieldWidth={110}
          selectWidth={360}
        />
        <Space>
          <PermissionWrapper requiredPermissions={['Edit']}><Button icon={<CloudDownloadOutlined />} onClick={handleImportSearch}>同步入库</Button></PermissionWrapper>
          {activeTab === 'win' && (
            <PermissionWrapper requiredPermissions={['Add']}><Button icon={<PlusOutlined />} onClick={() => { createForm.resetFields(); setCreateOpen(true); }}>新增补丁</Button></PermissionWrapper>
          )}
        </Space>
      </div>

      <div style={{ flex: 1, minHeight: 0 }}>
        <CustomTable<Patch>
          rowKey="id"
          columns={columns}
          dataSource={data}
          loading={loading}
          scroll={{ x: 1300 }}
          pagination={{
            current: pagination.current,
            pageSize: pagination.pageSize,
            total: pagination.total,
            showSizeChanger: true,
            showTotal: (t: number) => `共 ${t} 条`,
            style: { marginBottom: 0 },
            onChange: (page, pageSize) => loadData(page, pageSize),
          }}
        />
      </div>

      <OperateDrawer
        title="新增补丁"
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        width={520}
        footer={
          <Space>
            <Button onClick={() => { createForm.resetFields(); setCreateOpen(false); }}>取消</Button>
            <Button type="primary" onClick={handleCreateSubmit}>确定</Button>
          </Space>
        }
      >
        <Form layout="vertical" form={createForm} preserve={false}>
          <Form.Item label={activeTab === 'win' ? 'KB 号' : '包名'} name="name" rules={[{ required: true, message: activeTab === 'win' ? '请输入 KB 号' : '请输入包名' }]}>
            <Input placeholder={activeTab === 'win' ? '例如 KB5034441' : '例如 openssl'} />
          </Form.Item>
          <Form.Item label="描述" name="desc" rules={[{ required: true, message: '请输入补丁描述' }]}>
            <Input placeholder="请输入补丁描述" />
          </Form.Item>
          {activeTab === 'win' ? (
            <>
              <Form.Item label="适用版本" name="version" rules={[{ required: true, message: '请输入适用版本' }]}>
                <Input placeholder="例如 Windows Server 2019" />
              </Form.Item>
              <Form.Item label="架构" name="arch" rules={[{ required: true, message: '请选择架构' }]}>
                <Select placeholder="请选择" options={[{ label: 'x64', value: 'x64' }, { label: 'x86', value: 'x86' }]} />
              </Form.Item>
              <Form.Item
                label="补丁文件"
                name="package_file"
                valuePropName="fileList"
                getValueFromEvent={(event) => Array.isArray(event) ? event : event?.fileList}
                rules={[{ required: true, message: '请上传 MSU 或 CAB 补丁文件' }]}
              >
                <Upload.Dragger maxCount={1} beforeUpload={() => false} accept=".msu,.cab">
                  <p><InboxOutlined /></p>
                  <p>点击或拖拽 MSU / CAB 文件到此处</p>
                </Upload.Dragger>
              </Form.Item>
            </>
          ) : (
            <>
              <Form.Item label="发行版" name="dist" rules={[{ required: true, message: '请输入发行版' }]}>
                <Input placeholder="例如 Rocky 8" />
              </Form.Item>
              <Form.Item label="最低版本要求" name="minVer" rules={[{ required: true, message: '请输入最低版本要求' }]}>
                <Input placeholder="例如 1.1.1k-7.el8" />
              </Form.Item>
              <Form.Item label="架构" name="arch" rules={[{ required: true, message: '请选择架构' }]}>
                <Select placeholder="请选择" options={[{ label: 'x64', value: 'x64' }, { label: 'x86', value: 'x86' }]} />
              </Form.Item>
            </>
          )}
          <Form.Item label="严重级别" name="severity" rules={[{ required: true, message: '请选择严重级别' }]}>
            <Select placeholder="请选择" options={[{ label: '严重', value: 'critical' }, { label: '重要', value: 'important' }, { label: '中等', value: 'moderate' }, { label: '低', value: 'low' }]} />
          </Form.Item>
        </Form>
      </OperateDrawer>

      <OperateDrawer
        title="同步入库"
        open={importOpen}
        onClose={() => setImportOpen(false)}
        width={900}
        bodyStyle={{ padding: 0, overflow: 'hidden' }}
        footer={
          <Space>
            <Button onClick={() => setImportOpen(false)}>取消</Button>
            <Button type="primary" disabled={selectedCandidates.length === 0} icon={<CloudDownloadOutlined />} onClick={handleImportSubmit}>批量入库 ({selectedCandidates.length})</Button>
          </Space>
        }
      >
        <div style={{ display: 'flex', gap: 16, height: '100%', padding: 16, boxSizing: 'border-box' }}>
          <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            <div style={{ display: 'flex', gap: 12, marginBottom: 12, alignItems: 'center' }}>
              <Select
                style={{ width: 220 }}
                placeholder="请选择补丁源"
                virtual
                value={selectedSourceId ?? undefined}
                onChange={handleSourceChange}
                options={sources.map((s) => ({ value: s.id, label: `${s.name} (${s.source_type_display || s.source_type})` }))}
              />
              <Input.Search
                placeholder={activeTab === 'win' ? 'KB 号' : '包名'}
                value={candidateSearch}
                onChange={(e) => setCandidateSearch(e.target.value)}
                onSearch={(v) => handleCandidateSearch(v)}
                style={{ width: 200 }}
              />
            </div>
            <div style={{ flex: 1, minHeight: 0 }}>
              <CustomTable<CandidateItem>
                rowKey="key"
                loading={candidateLoading}
                rowSelection={{ selectedRowKeys: selectedCandidates, onChange: setSelectedCandidates, getCheckboxProps: (r) => ({ disabled: r.added }) }}
                columns={candidateColumns}
                dataSource={candidateData}
                pagination={{
                  current: candidatePagination.current,
                  pageSize: candidatePagination.pageSize,
                  total: candidatePagination.total,
                  showSizeChanger: true,
                  showTotal: (t) => `共 ${t} 条`,
                  onChange: (p, ps) => {
                    if (selectedSourceId) loadCandidates(selectedSourceId, p, ps, candidateSearch);
                  },
                }}
                size="small"
              />
            </div>
          </div>
          <div style={{ width: 220, display: 'flex', flexDirection: 'column', borderLeft: '1px solid var(--color-border-1, #e8e8e8)', paddingLeft: 16 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
              <span style={{ fontWeight: 500 }}>已选 {selectedCandidates.length} 条</span>
              {selectedCandidates.length > 0 && (
                <a style={{ color: '#ff4d4f', fontSize: 12 }} onClick={() => setSelectedCandidates([])}>全部清除</a>
              )}
            </div>
            <div style={{ flex: 1, overflowY: 'auto' }}>
              {selectedItems.map((c) => (
                <div key={c.key} className="candidate-item" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '6px 8px', borderRadius: 6, marginBottom: 4, background: 'var(--color-fill-1, #f4f6f9)', fontSize: 13 }}>
                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.name}</span>
                  <CloseOutlined className="candidate-remove-btn" style={{ color: '#bfbfbf', fontSize: 12, cursor: 'pointer', opacity: 0, transition: 'opacity 0.2s' }} onClick={() => setSelectedCandidates((prev) => prev.filter((k) => k !== c.key))} />
                </div>
              ))}
              {selectedCandidates.length === 0 && (
                <div style={{ color: 'var(--color-text-3, #8c8c8c)', fontSize: 13, textAlign: 'center', marginTop: 40 }}>暂未选择</div>
              )}
            </div>
          </div>
        </div>
        <style>{`.candidate-item:hover .candidate-remove-btn { opacity: 1 !important; }`}</style>
      </OperateDrawer>

      <Modal
        title="批量修改严重级别"
        open={batchSeverityOpen}
        onCancel={() => setBatchSeverityOpen(false)}
        onOk={() => {
          if (!batchSeverityValue) {
            message.warning('请选择严重级别');
            return;
          }
          setCandidateSeverity((prev) => {
            const next = { ...prev };
            candidateData.forEach((c) => { next[c.key] = batchSeverityValue; });
            return next;
          });
          setBatchSeverityOpen(false);
          message.success('已批量修改当前页严重级别');
        }}
        width={360}
      >
        <div style={{ padding: '16px 0' }}>
          <span style={{ marginRight: 12 }}>严重级别：</span>
          <Select
            value={batchSeverityValue}
            onChange={setBatchSeverityValue}
            options={SEVERITY_SELECT_OPTIONS}
            style={{ width: 160 }}
            placeholder="请选择"
          />
          <div style={{ marginTop: 12, color: 'var(--color-text-3, #8c8c8c)', fontSize: 12 }}>
            将当前页所有候选补丁的严重级别统一修改为所选值。
          </div>
        </div>
      </Modal>

      <Modal title="编辑补丁" open={!!editingPatch} onCancel={() => setEditingPatch(null)} onOk={async () => {
        let values;
        try {
          values = await editForm.validateFields();
        } catch (err: any) {
          if (err?.errorFields) return;
          message.error('表单校验失败');
          return;
        }
        if (!editingPatch) return;
        try {
          const payload: Partial<Patch> = { title: values.title, severity: values.severity };
          if (activeTab === 'win') {
            payload.windows_detail = {
              kb_number: editingPatch.windows_detail?.kb_number || '',
              ms_bulletin: editingPatch.windows_detail?.ms_bulletin || '',
              product_list: values.version ? values.version.split('、').map((s: string) => s.trim()) : [],
              architectures: values.arch ? [values.arch] : [],
            };
          } else {
            payload.linux_detail = {
              pkg_name: editingPatch.linux_detail?.pkg_name || '',
              pkg_version: values.minVer || '',
              distro_name: values.dist || '',
              os_version_range: editingPatch.linux_detail?.os_version_range || '',
              architectures: values.arch ? [values.arch] : [],
              repo_type: editingPatch.linux_detail?.repo_type || 'yum',
            };
          }
          await api.updatePatch(editingPatch.id, payload);
          const replacement = values.package_file?.[0]?.originFileObj as File | undefined;
          if (editingPatch.pkg_status === 'download_failed' && replacement) {
            await api.uploadWindowsPatchPackage(editingPatch.id, replacement, true);
          }
          message.success('已保存');
          setEditingPatch(null);
          loadData();
        } catch {
        }
      }} okText="保存" destroyOnClose>
        <Form layout="vertical" form={editForm} preserve={false} initialValues={editInitialValues}>
          <Form.Item label={activeTab === 'win' ? 'KB 号' : '包名'}>
            <Input disabled value={editingPatch ? getPatchName(editingPatch) : ''} />
          </Form.Item>
          <Form.Item label="描述" name="title" rules={[{ required: true, message: '请输入描述' }]}>
            <Input />
          </Form.Item>
          {activeTab === 'win' ? (
            <>
              <Form.Item label="适用版本" name="version">
                <Input />
              </Form.Item>
              {editPackageUploadState.visible && (
                <Form.Item
                  label="补丁文件"
                  name="package_file"
                  valuePropName="fileList"
                  getValueFromEvent={(event) => Array.isArray(event) ? event : event?.fileList}
                  extra={editPackageUploadState.disabled
                    ? '补丁包已就绪或正在处理中，暂不能替换'
                    : '上次上传失败，可删除旧文件后重新选择 MSU 或 CAB 文件'}
                >
                  <Upload
                    maxCount={1}
                    beforeUpload={() => false}
                    accept=".msu,.cab"
                    disabled={editPackageUploadState.disabled}
                    showUploadList={{
                      showPreviewIcon: false,
                      showDownloadIcon: false,
                      showRemoveIcon: editPackageUploadState.showRemoveIcon,
                    }}
                  >
                    {!editPackageUploadState.disabled && (
                      <Button icon={<UploadOutlined />}>选择文件</Button>
                    )}
                  </Upload>
                </Form.Item>
              )}
            </>
          ) : (
            <>
              <Form.Item label="最低版本要求" name="minVer">
                <Input />
              </Form.Item>
              <Form.Item label="发行版" name="dist">
                <Input />
              </Form.Item>
            </>
          )}
          <Form.Item label="架构" name="arch">
            <Input />
          </Form.Item>
          <Form.Item label="严重级别" name="severity" rules={[{ required: true, message: '请选择严重级别' }]}>
            <Select options={SEVERITY_OPTIONS.map(({ id, name }) => ({ label: name, value: id }))} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
