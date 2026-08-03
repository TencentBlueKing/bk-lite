'use client';

import { useState, useEffect, useMemo, useRef } from 'react';
import { Tag, Button, Input, Select, Space, Tabs, Modal, Form, message, Popconfirm, Tooltip, Upload } from 'antd';
import PermissionWrapper from '@/components/permission';
import type { ColumnsType } from 'antd/es/table';
import { PlusOutlined, CloudDownloadOutlined, EditOutlined, DeleteOutlined, CloseOutlined, InboxOutlined, UploadOutlined } from '@ant-design/icons';
import SearchCombination from '@/components/search-combination';
import type { FieldConfig, SearchFilters } from '@/components/search-combination/types';
import useApiClient from '@/utils/request';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import usePatchManagerApi from '@/app/patch-manager/api';
import { createListRequestCoordinator } from '@/app/patch-manager/utils/list-request-coordinator';
import type { Patch, PatchSeverity, OSType, PackageStatus, PatchParams, CandidateItem, PatchSource, IngestResult } from '@/app/patch-manager/types';
import SeverityTag from '@/app/patch-manager/components/severity-tag';
import ReadyTag from '@/app/patch-manager/components/ready-tag';
import CustomTable from '@/components/custom-table';
import OperateDrawer from '@/app/patch-manager/components/operate-drawer';
import { getWindowsPackageUploadState } from '@/app/patch-manager/components/windows-package-upload-state';
import {
  createCandidateSelection,
  reconcileCandidatePageSelection,
  removeCandidateFromSelection,
} from '@/app/patch-manager/components/candidate-selection';
import { useTranslation } from '@/utils/i18n';
import { PATCH_MANAGER_POLL_INTERVAL_MS } from '@/app/patch-manager/constants/polling';

type TabKey = 'win' | 'linux';
type SourceType = 'auto' | 'manual';

const OS_TYPE_MAP: Record<TabKey, OSType> = {
  win: 'windows',
  linux: 'linux',
};

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
      return 'manual';
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

function normalizeRepoType(repoType?: string): string {
  switch (repoType) {
    case 'yum_repo':
      return 'yum';
    case 'dnf_repo':
      return 'dnf';
    case 'apt_repo':
      return 'apt';
    default:
      return repoType || 'yum';
  }
}

export default function LibraryPage() {
  const { t } = useTranslation();
  const api = usePatchManagerApi();
  const { isLoading } = useApiClient();
  const { convertToLocalizedTime } = useLocalizedTime();
  const [activeTab, setActiveTab] = useState<TabKey>('win');
  const [data, setData] = useState<Patch[]>([]);
  const [loading, setLoading] = useState(false);
  const listRequestCoordinatorRef = useRef(createListRequestCoordinator(setLoading));
  const [filters, setFilters] = useState<SearchFilters>({});
  const [createOpen, setCreateOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [candidateSearch, setCandidateSearch] = useState('');
  const [candidateSelection, setCandidateSelection] = useState(createCandidateSelection);
  const [editingPatch, setEditingPatch] = useState<Patch | null>(null);
  const [createSaving, setCreateSaving] = useState(false);
  const [editSaving, setEditSaving] = useState(false);
  const [createForm] = Form.useForm();
  const [editForm] = Form.useForm();
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20, total: 0 });

  // 同步入库抽屉
  const [sources, setSources] = useState<PatchSource[]>([]);
  const sourceRequestCoordinatorRef = useRef(createListRequestCoordinator(() => undefined));
  const [selectedSourceId, setSelectedSourceId] = useState<number | null>(null);
  const [candidateData, setCandidateData] = useState<CandidateItem[]>([]);
  const [candidateLoading, setCandidateLoading] = useState(false);
  const candidateRequestCoordinatorRef = useRef(createListRequestCoordinator(setCandidateLoading));
  const [candidateActionLoading, setCandidateActionLoading] = useState(false);
  const [candidatePagination, setCandidatePagination] = useState({ current: 1, pageSize: 20, total: 0 });
  const [candidateSeverity, setCandidateSeverity] = useState<Record<string, string>>({});
  const [batchSeverityOpen, setBatchSeverityOpen] = useState(false);
  const [batchSeverityValue, setBatchSeverityValue] = useState<string | undefined>(undefined);

  const SEVERITY_SELECT_OPTIONS = (['critical', 'important', 'moderate', 'low'] as const)
    .map((value) => ({ label: t(`patchManager.severityValues.${value}`), value }));
  const severityFilterOptions = (['critical', 'important', 'moderate', 'low', 'unspecified'] as const)
    .map((id) => ({ id, name: t(`patchManager.severityValues.${id}`) }));
  const readyFilterOptions = (['ready', 'processing', 'action_required', 'unavailable'] as const)
    .map((id) => ({ id, name: t(`patchManager.readyStatus.${id}`) }));

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

  const loadData = async (
    page?: number,
    pageSize?: number,
    currentFilters?: SearchFilters,
    silent = false,
  ) => {
    const coordinator = listRequestCoordinatorRef.current;
    const ticket = coordinator.begin({ visible: !silent });
    if (!ticket) return;
    const targetPage = page ?? pagination.current;
    const targetSize = pageSize ?? pagination.pageSize;
    const targetFilters = currentFilters ?? filters;
    try {
      const res = await api.getPatchList(
        buildParams(targetPage, targetSize, targetFilters),
        { signal: ticket.signal },
      );
      if (coordinator.shouldApply(ticket)) {
        setData(res.items || []);
        setPagination((p) => ({ ...p, current: targetPage, pageSize: targetSize, total: res.count || 0 }));
      }
    } catch {
      if (coordinator.shouldApply(ticket)) {
        setData([]);
        setPagination((p) => ({ ...p, current: targetPage, pageSize: targetSize, total: 0 }));
      }
    } finally {
      coordinator.finish(ticket);
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
    const timer = window.setInterval(
      () => loadData(undefined, undefined, undefined, true),
      PATCH_MANAGER_POLL_INTERVAL_MS,
    );
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasProcessingPackage, activeTab, pagination.current, pagination.pageSize, filters]);

  useEffect(() => () => {
    listRequestCoordinatorRef.current.invalidate();
    sourceRequestCoordinatorRef.current.invalidate();
    candidateRequestCoordinatorRef.current.invalidate();
  }, []);

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
        name: editingPatch.windows_detail?.kb_number || '',
        version: (editingPatch.windows_detail?.product_list || []).join('、') || '',
        arch: (editingPatch.windows_detail?.architectures || [])[0] || '',
        package_file: getWindowsPackageUploadState(editingPatch).fileList,
      };
    }
    return {
      ...base,
      name: editingPatch.linux_detail?.pkg_name || '',
      minVer: editingPatch.linux_detail?.pkg_version || '',
      dist: editingPatch.linux_detail?.distro_name || '',
      arch: (editingPatch.linux_detail?.architectures || [])[0] || '',
    };
  }, [editingPatch, activeTab]);

  const winFieldConfigs: FieldConfig[] = [
    { name: 'name', label: t('patchManager.kbNumber'), lookup_expr: 'icontains' },
    { name: 'title', label: t('patchManager.libraryPage.description'), lookup_expr: 'icontains' },
    { name: 'version', label: t('patchManager.libraryPage.applicableVersion'), lookup_expr: 'icontains', options: [{ id: '2019', name: '2019' }, { id: '2022', name: '2022' }, { id: '2008', name: '2008' }] },
    { name: 'arch', label: t('patchManager.arch'), lookup_expr: 'in', options: ARCH_OPTIONS },
    { name: 'severity', label: t('patchManager.severity'), lookup_expr: 'in', options: severityFilterOptions },
    { name: 'ready', label: t('patchManager.libraryPage.readyStatus'), lookup_expr: 'in', options: readyFilterOptions },
    { name: 'sourceType', label: t('patchManager.libraryPage.sourceType'), lookup_expr: 'in', options: [{ id: 'auto', name: t('patchManager.libraryPage.automatic') }, { id: 'manual', name: t('patchManager.manual') }] },
  ];

  const linuxFieldConfigs: FieldConfig[] = [
    { name: 'name', label: t('patchManager.packageName'), lookup_expr: 'icontains' },
    { name: 'title', label: t('patchManager.libraryPage.description'), lookup_expr: 'icontains' },
    { name: 'version', label: t('patchManager.distro'), lookup_expr: 'in', options: [{ id: 'Rocky 8', name: 'Rocky 8' }, { id: 'Rocky 9', name: 'Rocky 9' }, { id: 'CentOS 7', name: 'CentOS 7' }] },
    { name: 'arch', label: t('patchManager.arch'), lookup_expr: 'in', options: ARCH_OPTIONS },
    { name: 'severity', label: t('patchManager.severity'), lookup_expr: 'in', options: severityFilterOptions },
    { name: 'ready', label: t('patchManager.libraryPage.readyStatus'), lookup_expr: 'in', options: readyFilterOptions },
    { name: 'sourceType', label: t('patchManager.libraryPage.sourceType'), lookup_expr: 'in', options: [{ id: 'auto', name: t('patchManager.libraryPage.automatic') }, { id: 'manual', name: t('patchManager.manual') }] },
  ];

  const handleDelete = async (row: Patch) => {
    if ((row.baseline_requirement_count ?? 0) > 0) return;
    try {
      await api.deletePatch(row.id);
      message.success(t('patchManager.libraryPage.deleted'));
      loadData();
    } catch {
    }
  };

  const columns: ColumnsType<Patch> = useMemo(() => {
    const isWin = activeTab === 'win';
    return [
      { title: isWin ? t('patchManager.kbNumber') : t('patchManager.packageName'), dataIndex: 'name', width: 120, render: (_: unknown, r: Patch) => getPatchName(r) },
      { title: t('patchManager.libraryPage.description'), dataIndex: 'title', ellipsis: true },
      { title: t('patchManager.severity'), dataIndex: 'severity', width: 100, render: (v: PatchSeverity) => <SeverityTag severity={v} /> },
      { title: isWin ? t('patchManager.libraryPage.applicableVersion') : t('patchManager.distro'), dataIndex: 'version', width: 140, render: (_: unknown, r: Patch) => getPatchVersion(r) },
      { title: t('patchManager.arch'), dataIndex: 'arch', width: 100, render: (_: unknown, r: Patch) => getPatchArch(r) },
      { title: t('patchManager.libraryPage.source'), dataIndex: 'sources', width: 120, render: (_: unknown, r: Patch) => <span style={{ color: '#8c8c8c' }}>{getSourceLabel(r) === 'manual' ? t('patchManager.manual') : getSourceLabel(r)}</span> },
      { title: t('patchManager.libraryPage.sourceType'), dataIndex: 'sourceType', width: 100, render: (_: unknown, r: Patch) => {
        const sourceType = getSourceType(r);
        return <Tag color={sourceType === 'auto' ? 'default' : 'warning'}>{sourceType === 'auto' ? t('patchManager.libraryPage.automatic') : t('patchManager.manual')}</Tag>;
      }},
      { title: t('patchManager.libraryPage.readyStatus'), dataIndex: 'pkg_status', width: 120, render: (_: unknown, r: Patch) => <ReadyTag status={mapPkgStatus(r.pkg_status)} /> },
      { title: t('patchManager.libraryPage.baselineReferences'), dataIndex: 'baseline_requirement_count', width: 110, render: (v: number) => <span style={{ color: '#bfbfbf' }}>{v ?? 0}</span> },
      { title: t('patchManager.libraryPage.lastUpdated'), dataIndex: 'last_synced_at', width: 180, render: (v: string | null, r: Patch) => convertToLocalizedTime(v || r.updated_at) || '—' },
      { title: t('patchManager.operation'), dataIndex: 'op', width: 180, fixed: 'right', render: (_: unknown, r: Patch) => {
        const deleteBlocked = (r.baseline_requirement_count ?? 0) > 0;
        const deleteButton = <Button
          type="link"
          size="small"
          danger
          disabled={deleteBlocked}
          icon={<DeleteOutlined />}
          style={{ paddingInline: 0 }}
        >
          {t('patchManager.delete')}
        </Button>;
        return <Space size={12}>
          <PermissionWrapper requiredPermissions={['Edit']}><a style={{ color: '#1677ff' }} onClick={() => setEditingPatch(r)}><EditOutlined /> {t('patchManager.edit')}</a></PermissionWrapper>
          <PermissionWrapper requiredPermissions={['Delete']}>
            {deleteBlocked ? <Tooltip title={t('patchManager.libraryPage.deleteReferenced')}><span>{deleteButton}</span></Tooltip> : <Popconfirm title={t('patchManager.libraryPage.deleteConfirm')} onConfirm={() => handleDelete(r)} okText={t('patchManager.delete')} cancelText={t('patchManager.cancel')}>
              {deleteButton}
            </Popconfirm>}
          </PermissionWrapper>
        </Space>;
      }},
    ];
  }, [activeTab, convertToLocalizedTime, t]);

  const handleCreateSubmit = async () => {
    let values;
    try {
      values = await createForm.validateFields();
    } catch (err: any) {
      if (err?.errorFields) return;
      message.error(t('patchManager.libraryPage.validationFailed'));
      return;
    }
    const osType = OS_TYPE_MAP[activeTab];
    const patchPayload: Partial<Patch> = {
      title: values.desc?.trim() || values.name,
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

    const file = values.package_file?.[0]?.originFileObj as File | undefined;
    if (activeTab === 'win' && !file) {
      message.error(t('patchManager.libraryPage.packageFileRequired'));
      return;
    }

    setCreateSaving(true);
    try {
      if (activeTab === 'win') {
        await api.saveManualWindowsPatch(patchPayload, file);
      } else {
        await api.createPatch(patchPayload);
      }
      createForm.resetFields();
      setCreateOpen(false);
      message.success(t('patchManager.libraryPage.created'));
      loadData(1);
    } catch {
      loadData(1);
    } finally {
      setCreateSaving(false);
    }
  };

  const loadSources = async () => {
    const coordinator = sourceRequestCoordinatorRef.current;
    const ticket = coordinator.begin({ visible: false });
    if (!ticket) return;
    try {
      const res = await api.getPatchSourceList(
        { page: 1, page_size: -1, is_enabled: true },
        { signal: ticket.signal },
      );
      if (!coordinator.shouldApply(ticket)) return;
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
    } finally {
      coordinator.finish(ticket);
    }
  };

  const loadCandidates = async (sourceId: number, page = 1, pageSize = 20, search = '') => {
    const coordinator = candidateRequestCoordinatorRef.current;
    const ticket = coordinator.begin({ visible: true });
    if (!ticket) return;
    try {
      const res = await api.previewSyncPatchSource(
        sourceId,
        { search, page, page_size: pageSize },
        { signal: ticket.signal },
      );
      if (!coordinator.shouldApply(ticket)) return;
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
      setCandidateSeverity((previous) => ({ ...previous, ...sevMap }));
    } catch {
      if (!coordinator.shouldApply(ticket)) return;
      setCandidateData([]);
      setCandidatePagination({ current: 1, pageSize: 20, total: 0 });
    } finally {
      coordinator.finish(ticket);
    }
  };

  const closeImportDrawer = () => {
    setImportOpen(false);
    sourceRequestCoordinatorRef.current.invalidate();
    candidateRequestCoordinatorRef.current.invalidate();
  };

  const handleImportSearch = () => {
    setImportOpen(true);
    setCandidateSelection(createCandidateSelection());
    setCandidateSeverity({});
    setCandidateSearch('');
    setCandidateData([]);
    setCandidatePagination({ current: 1, pageSize: 20, total: 0 });
    setSelectedSourceId(null);
    loadSources();
  };

  const handleSourceChange = (id: number) => {
    setSelectedSourceId(id);
    setCandidateSelection(createCandidateSelection());
    setCandidateSeverity({});
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
    if (!selectedSourceId || candidateSelection.keys.length === 0) return;
    setCandidateActionLoading(true);
    try {
      const severityOverrides: Record<string, string> = {};
      candidateSelection.keys.forEach((key) => {
        const sev = candidateSeverity[key];
        if (sev) severityOverrides[key] = sev;
      });
      const res = await api.ingestPatchSource(selectedSourceId, candidateSelection.keys, severityOverrides);
      if (isAsyncIngestResult(res)) {
        message.success(t('patchManager.libraryPage.ingestSubmitted'));
      } else {
        message.success(t('patchManager.libraryPage.ingestCompleted', undefined, { created: res.created, updated: res.updated }));
      }
      closeImportDrawer();
      setCandidateSelection(createCandidateSelection());
      setCandidateSearch('');
      loadData(1);
    } catch {
    } finally {
      setCandidateActionLoading(false);
    }
  };

  const handleSingleIngest = async (item: CandidateItem) => {
    if (!selectedSourceId) return;
    setCandidateActionLoading(true);
    try {
      const severityOverrides: Record<string, string> = {};
      const sev = candidateSeverity[item.key];
      if (sev) severityOverrides[item.key] = sev;
      const res = await api.ingestPatchSource(selectedSourceId, [item.key], severityOverrides);
      if (isAsyncIngestResult(res)) {
        message.success(t('patchManager.libraryPage.ingestSubmitted'));
      } else {
        message.success(t('patchManager.libraryPage.ingestCompleted', undefined, { created: res.created, updated: res.updated }));
        setCandidateData((prev) => prev.map((c) => c.key === item.key ? { ...c, added: true } : c));
      }
      loadData();
    } catch {
    } finally {
      setCandidateActionLoading(false);
    }
  };

  const candidateColumns: ColumnsType<CandidateItem> = [
    { title: activeTab === 'win' ? t('patchManager.kbNumber') : t('patchManager.packageName'), dataIndex: 'name', width: 130 },
    {
      title: t('patchManager.severity'),
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
    { title: t('patchManager.libraryPage.description'), dataIndex: 'title', ellipsis: true },
    ...(activeTab === 'win'
      ? [{ title: t('patchManager.libraryPage.applicableVersion'), dataIndex: 'version', width: 100 }, { title: t('patchManager.arch'), dataIndex: 'arch', width: 80 }]
      : [
        { title: t('patchManager.pkgVersion'), dataIndex: 'version', width: 150, ellipsis: true },
        { title: t('patchManager.distro'), dataIndex: 'dist', width: 100 },
        { title: t('patchManager.arch'), dataIndex: 'arch', width: 80 },
      ]),
    { title: t('patchManager.operation'), dataIndex: 'op', width: 90, fixed: 'right', render: (_: unknown, r: CandidateItem) => (
      r.added
        ? <Button type="link" disabled>{t('patchManager.libraryPage.ingested')}</Button>
        : <Button type="link" onClick={() => handleSingleIngest(r)}>{t('patchManager.libraryPage.ingest')}</Button>
    )},
  ];

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
          <PermissionWrapper requiredPermissions={['Edit']}><Button icon={<CloudDownloadOutlined />} onClick={handleImportSearch}>{t('patchManager.libraryPage.syncIngest')}</Button></PermissionWrapper>
          {activeTab === 'win' && (
            <PermissionWrapper requiredPermissions={['Add']}><Button icon={<PlusOutlined />} onClick={() => { createForm.resetFields(); setCreateOpen(true); }}>{t('patchManager.libraryPage.addPatch')}</Button></PermissionWrapper>
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
            showTotal: (total: number) => t('patchManager.common.totalItems', undefined, { count: total }),
            style: { marginBottom: 0 },
            onChange: (page, pageSize) => loadData(page, pageSize),
          }}
        />
      </div>

      <OperateDrawer
        title={t('patchManager.libraryPage.addPatch')}
        open={createOpen}
        onClose={() => {
          if (!createSaving) setCreateOpen(false);
        }}
        closable={!createSaving}
        maskClosable={!createSaving}
        keyboard={!createSaving}
        width={520}
        footer={
          <Space>
            <Button disabled={createSaving} onClick={() => { createForm.resetFields(); setCreateOpen(false); }}>{t('patchManager.cancel')}</Button>
            <Button type="primary" loading={createSaving} onClick={handleCreateSubmit}>{t('patchManager.confirm')}</Button>
          </Space>
        }
      >
        <Form layout="vertical" form={createForm} preserve={false}>
          <Form.Item label={activeTab === 'win' ? t('patchManager.kbNumber') : t('patchManager.packageName')} name="name" rules={[{ required: true, message: activeTab === 'win' ? t('patchManager.libraryPage.kbRequired') : t('patchManager.libraryPage.packageNameRequired') }]}>
            <Input placeholder={activeTab === 'win' ? t('patchManager.libraryPage.kbPlaceholder') : t('patchManager.libraryPage.packagePlaceholder')} />
          </Form.Item>
          {activeTab === 'win' && (
            <>
              <Form.Item
                label={t('patchManager.libraryPage.patchFile')}
                name="package_file"
                valuePropName="fileList"
                getValueFromEvent={(event) => Array.isArray(event) ? event : event?.fileList}
                rules={[{ required: true, message: t('patchManager.libraryPage.packageFileRequired') }]}
              >
                <Upload.Dragger maxCount={1} beforeUpload={() => false} accept=".msu,.cab">
                  <p><InboxOutlined /></p>
                  <p>{t('patchManager.libraryPage.fileDrop')}</p>
                </Upload.Dragger>
              </Form.Item>
            </>
          )}
          <Form.Item label={t('patchManager.libraryPage.description')} name="desc">
            <Input placeholder={t('patchManager.libraryPage.descriptionPlaceholder')} />
          </Form.Item>
          {activeTab === 'win' && (
            <Form.Item label={t('patchManager.severity')} name="severity" rules={[{ required: true, message: t('patchManager.libraryPage.severityRequired') }]}>
              <Select placeholder={t('patchManager.libraryPage.select')} options={SEVERITY_SELECT_OPTIONS} />
            </Form.Item>
          )}
          {activeTab === 'win' ? (
            <>
              <Form.Item label={t('patchManager.libraryPage.applicableVersion')} name="version">
                <Input placeholder={t('patchManager.libraryPage.versionPlaceholder')} />
              </Form.Item>
              <Form.Item label={t('patchManager.arch')} name="arch">
                <Select placeholder={t('patchManager.libraryPage.select')} options={[{ label: 'x64', value: 'x64' }, { label: 'x86', value: 'x86' }]} />
              </Form.Item>
            </>
          ) : (
            <>
              <Form.Item label={t('patchManager.distro')} name="dist" rules={[{ required: true, message: t('patchManager.libraryPage.distroRequired') }]}>
                <Input placeholder={t('patchManager.libraryPage.distroPlaceholder')} />
              </Form.Item>
              <Form.Item label={t('patchManager.libraryPage.minimumVersion')} name="minVer" rules={[{ required: true, message: t('patchManager.libraryPage.minimumVersionRequired') }]}>
                <Input placeholder={t('patchManager.libraryPage.minimumVersionPlaceholder')} />
              </Form.Item>
              <Form.Item label={t('patchManager.arch')} name="arch" rules={[{ required: true, message: t('patchManager.libraryPage.archRequired') }]}>
                <Select placeholder={t('patchManager.libraryPage.select')} options={[{ label: 'x64', value: 'x64' }, { label: 'x86', value: 'x86' }]} />
              </Form.Item>
            </>
          )}
          {activeTab !== 'win' && (
            <Form.Item label={t('patchManager.severity')} name="severity" rules={[{ required: true, message: t('patchManager.libraryPage.severityRequired') }]}>
              <Select placeholder={t('patchManager.libraryPage.select')} options={SEVERITY_SELECT_OPTIONS} />
            </Form.Item>
          )}
        </Form>
      </OperateDrawer>

      <OperateDrawer
        title={t('patchManager.libraryPage.syncIngest')}
        open={importOpen}
        onClose={closeImportDrawer}
        width={900}
        bodyStyle={{ padding: 0, overflow: 'hidden' }}
        footer={
          <Space>
            <Button onClick={closeImportDrawer}>{t('patchManager.cancel')}</Button>
            <Button type="primary" loading={candidateActionLoading} disabled={candidateSelection.keys.length === 0} icon={<CloudDownloadOutlined />} onClick={handleImportSubmit}>{t('patchManager.libraryPage.batchIngest', undefined, { count: candidateSelection.keys.length })}</Button>
          </Space>
        }
      >
        <div style={{ display: 'flex', gap: 16, height: '100%', padding: 16, boxSizing: 'border-box' }}>
          <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            <div style={{ display: 'flex', gap: 12, marginBottom: 12, alignItems: 'center' }}>
              <Select
                style={{ width: 220 }}
                placeholder={t('patchManager.libraryPage.selectSource')}
                virtual
                value={selectedSourceId ?? undefined}
                onChange={handleSourceChange}
                options={sources.map((s) => ({ value: s.id, label: `${s.name} (${s.source_type_display || s.source_type})` }))}
              />
              <Input.Search
                placeholder={activeTab === 'win' ? t('patchManager.kbNumber') : t('patchManager.packageName')}
                value={candidateSearch}
                onChange={(e) => setCandidateSearch(e.target.value)}
                onSearch={(v) => handleCandidateSearch(v)}
                style={{ width: 200 }}
              />
            </div>
            <div style={{ flex: 1, minHeight: 0 }}>
              <CustomTable<CandidateItem>
                rowKey="key"
                loading={candidateLoading || candidateActionLoading}
                rowSelection={{
                  selectedRowKeys: candidateSelection.keys,
                  preserveSelectedRowKeys: true,
                  onChange: (selectedRowKeys) => setCandidateSelection((previous) =>
                    reconcileCandidatePageSelection(previous, candidateData, selectedRowKeys)
                  ),
                  getCheckboxProps: (r) => ({ disabled: r.added }),
                }}
                columns={candidateColumns}
                dataSource={candidateData}
                pagination={{
                  current: candidatePagination.current,
                  pageSize: candidatePagination.pageSize,
                  total: candidatePagination.total,
                  showSizeChanger: true,
                  showTotal: (total) => t('patchManager.common.totalItems', undefined, { count: total }),
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
              <span style={{ fontWeight: 500 }}>{t('patchManager.libraryPage.selectedCount', undefined, { count: candidateSelection.keys.length })}</span>
              {candidateSelection.keys.length > 0 && (
                <a style={{ color: '#ff4d4f', fontSize: 12 }} onClick={() => setCandidateSelection(createCandidateSelection())}>{t('patchManager.common.clearAll')}</a>
              )}
            </div>
            <div style={{ flex: 1, overflowY: 'auto' }}>
              {candidateSelection.items.map((c) => (
                <div key={c.key} className="candidate-item" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '6px 8px', borderRadius: 6, marginBottom: 4, background: 'var(--color-fill-1, #f4f6f9)', fontSize: 13 }}>
                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.name}</span>
                  <CloseOutlined className="candidate-remove-btn" style={{ color: '#bfbfbf', fontSize: 12, cursor: 'pointer', opacity: 0, transition: 'opacity 0.2s' }} onClick={() => setCandidateSelection((previous) => removeCandidateFromSelection(previous, c.key))} />
                </div>
              ))}
              {candidateSelection.keys.length === 0 && (
                <div style={{ color: 'var(--color-text-3, #8c8c8c)', fontSize: 13, textAlign: 'center', marginTop: 40 }}>{t('patchManager.common.noSelection')}</div>
              )}
            </div>
          </div>
        </div>
        <style>{`.candidate-item:hover .candidate-remove-btn { opacity: 1 !important; }`}</style>
      </OperateDrawer>

      <Modal
        title={t('patchManager.libraryPage.batchSeverity')}
        open={batchSeverityOpen}
        onCancel={() => setBatchSeverityOpen(false)}
        onOk={() => {
          if (!batchSeverityValue) {
            message.warning(t('patchManager.libraryPage.severityRequired'));
            return;
          }
          setCandidateSeverity((prev) => {
            const next = { ...prev };
            candidateData.forEach((c) => { next[c.key] = batchSeverityValue; });
            return next;
          });
          setBatchSeverityOpen(false);
          message.success(t('patchManager.libraryPage.batchSeverityUpdated'));
        }}
        width={360}
      >
        <div style={{ padding: '16px 0' }}>
          <span style={{ marginRight: 12 }}>{t('patchManager.severity')}：</span>
          <Select
            value={batchSeverityValue}
            onChange={setBatchSeverityValue}
            options={SEVERITY_SELECT_OPTIONS}
            style={{ width: 160 }}
            placeholder={t('patchManager.libraryPage.select')}
          />
          <div style={{ marginTop: 12, color: 'var(--color-text-3, #8c8c8c)', fontSize: 12 }}>
            {t('patchManager.libraryPage.batchSeverityHelp')}
          </div>
        </div>
      </Modal>

      <Modal
        title={t('patchManager.libraryPage.editPatch')}
        open={!!editingPatch}
        onCancel={() => {
          if (!editSaving) setEditingPatch(null);
        }}
        confirmLoading={editSaving}
        cancelButtonProps={{ disabled: editSaving }}
        closable={!editSaving}
        maskClosable={!editSaving}
        keyboard={!editSaving}
        onOk={async () => {
          let values;
          try {
            values = await editForm.validateFields();
          } catch (err: any) {
            if (err?.errorFields) return;
            message.error(t('patchManager.libraryPage.validationFailed'));
            return;
          }
          if (!editingPatch) return;
          setEditSaving(true);
          try {
            const payload: Partial<Patch> = {
              title: values.title?.trim() || values.name,
              os_type: editingPatch.os_type,
              severity: values.severity,
              team: editingPatch.team,
            };
            if (activeTab === 'win') {
              payload.windows_detail = {
                kb_number: values.name,
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
                repo_type: normalizeRepoType(editingPatch.linux_detail?.repo_type),
              };
            }
            const replacement = values.package_file?.[0]?.originFileObj as File | undefined;
            if (activeTab === 'win') {
              await api.saveManualWindowsPatch(payload, replacement, editingPatch.id);
            } else {
              await api.updatePatch(editingPatch.id, payload);
            }
            message.success(t('patchManager.libraryPage.saved'));
            setEditingPatch(null);
            loadData();
          } catch {
          } finally {
            setEditSaving(false);
          }
        }}
        okText={t('patchManager.save')}
        destroyOnClose
      >
        <Form layout="vertical" form={editForm} preserve={false} initialValues={editInitialValues}>
          <Form.Item
            label={activeTab === 'win' ? t('patchManager.kbNumber') : t('patchManager.packageName')}
            name="name"
            rules={[{ required: true, message: activeTab === 'win' ? t('patchManager.libraryPage.kbRequired') : t('patchManager.libraryPage.packageNameRequired') }]}
          >
            <Input disabled={Boolean(activeTab === 'win' ? editingPatch?.windows_detail?.kb_number : editingPatch?.linux_detail?.pkg_name)} />
          </Form.Item>
          {activeTab === 'win' ? (
            <>
              {editPackageUploadState.visible && (
                <Form.Item
                  label={t('patchManager.libraryPage.patchFile')}
                  name="package_file"
                  valuePropName="fileList"
                  getValueFromEvent={(event) => Array.isArray(event) ? event : event?.fileList}
                  extra={editPackageUploadState.disabled
                    ? t('patchManager.libraryPage.packageNotReplaceable')
                    : t('patchManager.libraryPage.packageRetryHelp')}
                  rules={editingPatch?.pkg_status === 'download_failed' ? [
                    { required: true, message: t('patchManager.libraryPage.packageReuploadRequired') },
                    {
                      validator: async (_rule, files) => {
                        if (files?.some((file: any) => file.originFileObj)) return;
                        throw new Error(t('patchManager.libraryPage.packageReuploadRequired'));
                      },
                    },
                  ] : undefined}
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
                      <Button icon={<UploadOutlined />}>{t('patchManager.libraryPage.selectFile')}</Button>
                    )}
                  </Upload>
                </Form.Item>
              )}
              <Form.Item label={t('patchManager.libraryPage.description')} name="title">
                <Input />
              </Form.Item>
              <Form.Item label={t('patchManager.severity')} name="severity" rules={[{ required: true, message: t('patchManager.libraryPage.severityRequired') }]}>
                <Select options={severityFilterOptions.map(({ id, name }) => ({ label: name, value: id }))} />
              </Form.Item>
              <Form.Item label={t('patchManager.libraryPage.applicableVersion')} name="version">
                <Input />
              </Form.Item>
              <Form.Item label={t('patchManager.arch')} name="arch">
                <Input />
              </Form.Item>
            </>
          ) : (
            <>
              <Form.Item label={t('patchManager.libraryPage.description')} name="title">
                <Input />
              </Form.Item>
              <Form.Item label={t('patchManager.libraryPage.minimumVersion')} name="minVer">
                <Input />
              </Form.Item>
              <Form.Item label={t('patchManager.distro')} name="dist">
                <Input />
              </Form.Item>
              <Form.Item label={t('patchManager.arch')} name="arch">
                <Input />
              </Form.Item>
              <Form.Item label={t('patchManager.severity')} name="severity" rules={[{ required: true, message: t('patchManager.libraryPage.severityRequired') }]}>
                <Select options={severityFilterOptions.map(({ id, name }) => ({ label: name, value: id }))} />
              </Form.Item>
            </>
          )}
        </Form>
      </Modal>
    </div>
  );
}
