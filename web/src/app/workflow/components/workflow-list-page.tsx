'use client';

import { DownloadOutlined, MoreOutlined, PlusOutlined, ReloadOutlined, UploadOutlined } from '@ant-design/icons';
import { App, Button, Dropdown, Empty, Input, Popconfirm, Switch, Tag, Tooltip } from 'antd';
import type { MenuProps } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useRouter, useSearchParams } from 'next/navigation';
import { useCallback, useMemo, useState } from 'react';

import CustomTable from '@/components/custom-table';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import { useUserInfoContext } from '@/context/userInfo';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { useTranslation } from '@/utils/i18n';
import useApiClient from '@/utils/request';
import { organizationDisplayText } from '../lib/organization-display';
import type { ExecutionRecord, PaginatedResponse, WorkflowRecord } from '../lib/types';
import { useAutoRequest, useRequestCoordinator } from '../lib/use-request-coordinator';
import { WorkflowImportDialog } from './workflow-import-dialog';
import { WorkflowLaunchDialog } from './workflow-launch-dialog';
import { WorkflowPermission } from './workflow-permission';
import { WorkflowProfileDialog, type WorkflowProfileValue } from './workflow-profile-dialog';
import { WorkflowTablePanel } from './workflow-table-panel';

const API = '/workflow/api';
type ListStatus = 'DRAFT' | 'PUBLISHED';
type EnabledFilter = 'true' | 'false';
type WorkflowCatalog = 'custom' | 'market';

export function WorkflowListPage({ catalog = 'custom' }: { catalog?: WorkflowCatalog }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { message, modal } = App.useApp();
  const { t } = useTranslation();
  const { convertToLocalizedTime } = useLocalizedTime();
  const { selectedGroup, flatGroups } = useUserInfoContext();
  const { get, post, patch, del } = useApiClient();
  const [records, setRecords] = useState<WorkflowRecord[]>([]);
  const [count, setCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [queryDraft, setQueryDraft] = useState('');
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState<ListStatus | undefined>(() => {
    const initial = searchParams.get('status');
    return initial === 'DRAFT' || initial === 'PUBLISHED' ? initial : undefined;
  });
  const [enabledFilter, setEnabledFilter] = useState<EnabledFilter>();
  const isMarket = catalog === 'market';
  const permissionArea = isMarket ? 'market' : 'workflows';
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20 });
  const [busyId, setBusyId] = useState<number>();
  const [profile, setProfile] = useState<{ mode: 'create' | 'edit' | 'copy'; workflow?: WorkflowRecord } | null>(null);
  const [profileBusy, setProfileBusy] = useState(false);
  const [runWorkflow, setRunWorkflow] = useState<WorkflowRecord>();
  const [selectedRowKeys, setSelectedRowKeys] = useState<number[]>([]);
  const [exporting, setExporting] = useState(false);
  const [importing, setImporting] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const requestCoordinator = useRequestCoordinator(setLoading);

  const load = useCallback(async () => {
    const ticket = requestCoordinator.begin({ visible: true });
    if (!ticket) return;
    try {
      const params = new URLSearchParams({ page: String(pagination.current), page_size: String(pagination.pageSize) });
      if (query.trim()) params.set('query', query.trim());
      if (status) params.set('status', status);
      if (enabledFilter) params.set('enabled', enabledFilter);
      params.set('is_builtin', isMarket ? 'true' : 'false');
      const response = await get<PaginatedResponse<WorkflowRecord>>(`${API}/workflows/?${params.toString()}`, { signal: ticket.signal });
      if (!requestCoordinator.shouldApply(ticket)) return;
      setRecords(response?.items || []); setCount(response?.count || 0);
    } catch {
      if (!requestCoordinator.shouldApply(ticket)) return;
      setRecords([]);
      setCount(0);
    } finally { requestCoordinator.finish(ticket); }
  }, [enabledFilter, get, isMarket, pagination.current, pagination.pageSize, query, requestCoordinator, status]);

  const requestKey = useMemo(
    () => JSON.stringify([pagination.current, pagination.pageSize, query, status, enabledFilter, isMarket]),
    [enabledFilter, isMarket, pagination.current, pagination.pageSize, query, status],
  );
  useAutoRequest(requestKey, load);

  const includesCurrentOrganization = (team: number[]) => team.some((id) => String(id) === String(selectedGroup?.id));

  const profileSavedMessage = (mode: 'create' | 'copy', team: number[]) => {
    if (includesCurrentOrganization(team)) {
      return mode === 'create'
        ? t('workflowOrchestration.workflow.createdSuccess', '已创建为纯草稿')
        : t('workflowOrchestration.workflow.duplicatedSuccess', '已复制为新的纯草稿');
    }
    const organizations = organizationDisplayText(team, flatGroups);
    return mode === 'create'
      ? t('workflowOrchestration.workflow.createdElsewhere', '已创建到 {organizations}，切换组织后可见', { organizations })
      : t('workflowOrchestration.workflow.copiedElsewhere', '已复制到 {organizations}，切换组织后可见', { organizations });
  };

  const submitProfile = async (value: WorkflowProfileValue) => {
    if (!profile) return;
    setProfileBusy(true);
    try {
      if (profile.mode === 'create') {
        await post(`${API}/workflows/`, { ...value, starter: 'blank' });
        message.success(profileSavedMessage('create', value.team));
      } else if (profile.mode === 'copy' && profile.workflow) {
        await post(`${API}/workflows/${profile.workflow.id}/duplicate/`, value);
        message.success(profileSavedMessage('copy', value.team));
      } else if (profile.workflow) {
        const body = profile.workflow.current_version
          ? { name: value.name, description: value.description }
          : value;
        await patch(`${API}/workflows/${profile.workflow.id}/`, body);
        message.success(t('workflowOrchestration.editor.draftSaved', '草稿已保存'));
      }
      setProfile(null);
      await load();
    } finally {
      setProfileBusy(false);
    }
  };

  const exportFailureList = async (error: unknown) => {
    const record = error as { payload?: unknown; response?: { data?: unknown } };
    const raw = record.payload ?? record.response?.data;
    if (raw == null) return null;
    try {
      const text = raw instanceof Blob ? await raw.text() : typeof raw === 'string' ? raw : JSON.stringify(raw);
      const parsed = JSON.parse(text) as { data?: { exported?: number; failed?: { name: string; reason: string }[] } };
      if (!Array.isArray(parsed.data?.failed)) return null;
      return { exported: parsed.data?.exported ?? 0, failed: parsed.data.failed };
    } catch {
      return null;
    }
  };

  const packErrorText = async (error: unknown) => {
    const data = (error as { response?: { data?: unknown } })?.response?.data;
    if (data instanceof Blob) {
      try {
        const parsed = JSON.parse(await data.text()) as { detail?: string };
        return parsed.detail || '';
      } catch {
        return '';
      }
    }
    if (data && typeof data === 'object' && 'detail' in data) return String((data as { detail?: unknown }).detail || '');
    return '';
  };

  const downloadPack = (payload: Blob) => {
    const url = window.URL.createObjectURL(payload);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'workflow-pack.zip';
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  };

  const showExportResult = (exported: number, failed: { name: string; reason: string }[]) => {
    if (!failed.length) {
      message.success(t('workflowOrchestration.workflow.exportSuccess', '已下载流程压缩包'));
      return;
    }
    const summary = t('workflowOrchestration.workflow.exportSummary', '已导出 {exported} 条，失败 {failed} 条', {
      exported,
      failed: failed.length,
    });
    modal.info({
      title: t('workflowOrchestration.workflow.exportResultTitle', '导出结果'),
      content: (
        <div className="space-y-2">
          <p>{summary}</p>
          {failed.map((item) => <p key={`${item.name}-${item.reason}`}>{item.name}：{item.reason}</p>)}
        </div>
      ),
    });
  };

  const exportWorkflows = async () => {
    if (!selectedRowKeys.length || exporting) return;
    setExporting(true);
    try {
      const payload = await post<Blob>(`${API}/workflows/export/`, { ids: selectedRowKeys }, {
        responseType: 'blob',
        suppressErrorNotification: true,
      });
      const header = await payload.slice(0, 2).text();
      if (header === 'PK') {
        downloadPack(payload);
        showExportResult(0, []);
        return;
      }
      const parsed = JSON.parse(await payload.text()) as {
        data?: { exported?: number; failed?: { name: string; reason: string }[]; pack?: string };
      };
      const failed = parsed.data?.failed ?? [];
      if (parsed.data?.pack) {
        const binary = window.atob(parsed.data.pack);
        const bytes = new Uint8Array(binary.length);
        for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
        downloadPack(new Blob([bytes], { type: 'application/zip' }));
      }
      showExportResult(parsed.data?.exported ?? 0, failed);
    } catch (error) {
      const failed = await exportFailureList(error);
      if (failed) {
        showExportResult(failed.exported, failed.failed);
        return;
      }
      message.error((await packErrorText(error)) || t('workflowOrchestration.workflow.exportFailed', '没有可导出的流程'));
    } finally {
      setExporting(false);
    }
  };

  const importWorkflows = async (team: number[], file: File) => {
    if (importing) return;
    setImporting(true);
    try {
      const body = new FormData();
      team.forEach((id) => body.append('team', String(id)));
      body.append('file', file);
      const result = await post<{
        created: { name: string; id: number }[];
        failed: { name: string; reason: string }[];
        rebind: { name: string; nodes: string[] }[];
      }>(`${API}/workflows/import/`, body, {
        headers: { 'Content-Type': 'multipart/form-data' },
        suppressErrorNotification: true,
      });
      setImportOpen(false);
      const summary = t('workflowOrchestration.workflow.importSummary', '已导入 {created} 条，失败 {failed} 条', {
        created: result.created.length,
        failed: result.failed.length,
      });
      const elsewhere = includesCurrentOrganization(team)
        ? ''
        : t('workflowOrchestration.workflow.importedElsewhere', '已导入到 {organizations}，切换组织后可见', {
          organizations: organizationDisplayText(team, flatGroups),
        });
      if (!result.failed.length && !result.rebind.length) message.success(elsewhere || summary);
      else {
        modal.info({
          title: t('workflowOrchestration.workflow.importResultTitle', '导入结果'),
          content: (
            <div className="space-y-2">
              <p>{summary}</p>
              {elsewhere ? <p>{elsewhere}</p> : null}
              {result.failed.map((item) => <p key={`${item.name}-${item.reason}`}>{item.name}：{item.reason}</p>)}
              {result.rebind.map((item) => (
                <p key={item.name}>{t('workflowOrchestration.workflow.rebindLine', '{name}需要重新选择：{nodes}', { name: item.name, nodes: item.nodes.join('、') })}</p>
              ))}
            </div>
          ),
        });
      }
      await load();
    } catch (error) {
      message.error((await packErrorText(error)) || t('workflowOrchestration.workflow.importFailed', '导入失败'));
    } finally {
      setImporting(false);
    }
  };

  const toggle = async (record: WorkflowRecord) => {
    setBusyId(record.id);
    try {
      const updated = await post<WorkflowRecord>(`${API}/workflows/${record.id}/enabled/`, { enabled: !record.enabled });
      setRecords((items) => items.map((item) => item.id === record.id ? updated : item));
      message.success(updated.enabled
        ? t('workflowOrchestration.workflow.enabledSuccess', '流程已启用')
        : t('workflowOrchestration.workflow.disabledSuccess', '流程已停用，不影响历史执行'));
    } finally { setBusyId(undefined); }
  };

  const remove = async (record: WorkflowRecord) => {
    setBusyId(record.id);
    try { await del(`${API}/workflows/${record.id}/`); setRecords((items) => items.filter((item) => item.id !== record.id)); setCount((value) => Math.max(0, value - 1)); message.success(t('workflowOrchestration.workflow.deletedSuccess', '流程已删除，历史执行仍保留')); }
    finally { setBusyId(undefined); }
  };

  const execute = (record: WorkflowRecord) => {
    setRunWorkflow(record);
  };

  const openMoreAction = (key: string, record: WorkflowRecord) => {
    if (key === 'executions') {
      router.push(`/workflow/executions?query=${encodeURIComponent(record.name)}`);
      return;
    }
    if (key === 'duplicate') {
      setProfile({ mode: 'copy', workflow: record });
      return;
    }
    if (key === 'profile') {
      setProfile({ mode: 'edit', workflow: record });
      return;
    }
    if (key === 'delete') {
      modal.confirm({
        title: t('workflowOrchestration.workflow.deleteConfirm', '确认删除流程？'),
        content: t('workflowOrchestration.workflow.deleteHint', '流程本身不可恢复，历史版本快照与执行记录仍保留。'),
        okText: t('common.delete', '删除'),
        cancelText: t('common.cancel', '取消'),
        okButtonProps: { danger: true },
        onOk: () => remove(record),
      });
    }
  };

  const moreActions = (record: WorkflowRecord): MenuProps['items'] => [
    { key: 'executions', label: <WorkflowPermission operation="View" area="executions"><span>{t('workflowOrchestration.execution.records', '执行记录')}</span></WorkflowPermission> },
    { key: 'duplicate', label: <WorkflowPermission operation="Add"><span>{t('common.copy', '复制')}</span></WorkflowPermission> },
    ...(record.is_builtin ? [] : [{ key: 'profile', label: <WorkflowPermission operation="Edit" instancePermissions={record.permission}><span>{t('workflowOrchestration.workflow.basicInfo', '基本信息')}</span></WorkflowPermission> }]),
    ...(record.is_builtin
      ? []
      : [
        { type: 'divider' as const },
        {
          key: 'delete',
          label: (
              <WorkflowPermission operation="Delete" instancePermissions={record.permission}>
                <span>{t('common.delete', '删除')}</span>
              </WorkflowPermission>
          ),
          danger: true,
        },
      ]),
  ];

  const runDisabledReason = (record: WorkflowRecord) => {
    if (!record.current_version) return t('workflowOrchestration.workflow.runRequiresPublish', '请先发布流程');
    if (!record.enabled) return t('workflowOrchestration.workflow.runRequiresEnable', '请先启用流程');
    if (record.trigger_summary?.includes('FORM')) return '';
    const types = record.trigger_summary || [];
    if (types.length === 1 && types[0] === 'SCHEDULE') {
      return t('workflowOrchestration.workflow.scheduleRunHint', '流程将按配置时间自动触发；如需验证，请到编辑页测试定时触发器');
    }
    if (types.length === 1 && types[0] === 'WEBHOOK') {
      return t('workflowOrchestration.workflow.webhookRunHint', '请通过 Postman、curl 或外部系统向正式 Webhook 地址发送 POST 请求');
    }
    if (types.length === 1 && types[0] === 'NATS') {
      return t('workflowOrchestration.workflow.natsRunHint', '流程由 NATS 事件自动触发；如需验证，请到编辑页监听测试事件');
    }
    return t('workflowOrchestration.workflow.externalRunHint', '该流程由定时、Webhook 或 NATS 入口自动触发；请到编辑页查看入口或测试触发器');
  };

  const columns: ColumnsType<WorkflowRecord> = [
    {
      title: isMarket
        ? t('workflowOrchestration.workflow.templateName', '模版名称')
        : t('workflowOrchestration.workflow.name', '流程名称'),
      dataIndex: 'name',
      key: 'name',
      width: 220,
      render: (value: string) => <EllipsisWithTooltip text={value || '--'} className="w-full overflow-hidden text-ellipsis whitespace-nowrap" />,
    },
    {
      title: t('workflowOrchestration.workflow.description', '描述'),
      dataIndex: 'description',
      key: 'description',
      width: 200,
      render: (value: string) => <EllipsisWithTooltip text={value || '--'} className="w-full overflow-hidden text-ellipsis whitespace-nowrap" />,
    },
    {
      title: t('workflowOrchestration.workflow.organization', '组织'),
      dataIndex: 'team',
      key: 'organization',
      width: 180,
      render: (value: number[]) => <EllipsisWithTooltip text={organizationDisplayText(value, flatGroups)} className="w-full overflow-hidden text-ellipsis whitespace-nowrap" />,
    },
    {
      title: t('workflowOrchestration.workflow.publishStatus', '发布状态'),
      key: 'status',
      width: 105,
      filters: [
        { value: 'DRAFT', text: t('workflowOrchestration.status.draftOnly', '纯草稿') },
        { value: 'PUBLISHED', text: t('workflowOrchestration.status.published', '已发布') },
      ],
      filterMultiple: false,
      filteredValue: status ? [status] : null,
      render: (_, record) => record.current_version
        ? <Tag color="blue">{t('workflowOrchestration.status.published', '已发布')}</Tag>
        : <Tag>{t('workflowOrchestration.status.draftOnly', '纯草稿')}</Tag>,
    },
    {
      title: t('workflowOrchestration.workflow.enableStatus', '启用状态'),
      key: 'enabled',
      width: 105,
      filters: [
        { value: 'true', text: t('workflowOrchestration.status.enabled', '已启用') },
        { value: 'false', text: t('workflowOrchestration.status.disabled', '已停用') },
      ],
      filterMultiple: false,
      filteredValue: enabledFilter ? [enabledFilter] : null,
      render: (_, record) => {
        const unavailable = !record.current_version;
        const title = unavailable
          ? t('workflowOrchestration.workflow.enableRequiresPublish', '发布后可启用')
          : undefined;
        const control = <Switch
          size="small"
          checked={record.enabled}
          disabled={unavailable}
          loading={busyId === record.id}
          aria-label={t('workflowOrchestration.workflow.enableSwitchFor', '启用状态：{name}', { name: record.name })}
        />;
        if (unavailable) return <Tooltip title={title}><span className="inline-flex">{control}</span></Tooltip>;
        return <WorkflowPermission operation="Publish" instancePermissions={record.permission}>
          <Popconfirm
            title={record.enabled ? t('workflowOrchestration.workflow.disableConfirm', '停用该流程？') : t('workflowOrchestration.workflow.enableConfirm', '启用当前发布版本？')}
            description={record.enabled
              ? t('workflowOrchestration.workflow.disableHint', '停用后将拒绝新的触发事件，正在执行的流程不受影响。')
              : t('workflowOrchestration.workflow.enableHint', '启用后，定时、Webhook 和 NATS 正式入口将立即生效。')}
            okText={record.enabled ? t('common.disable', '停用') : t('common.enable', '启用')}
            cancelText={t('common.cancel', '取消')}
            okButtonProps={record.enabled ? { danger: true } : undefined}
            onConfirm={() => toggle(record)}
          >
            <span className="inline-flex">{control}</span>
          </Popconfirm>
        </WorkflowPermission>;
      },
    },
    {
      title: t('common.version', '版本'),
      key: 'version',
      width: 160,
      render: (_, record) => {
        const value = record.current_version
          ? `v${record.current_version}${record.has_draft ? t('workflowOrchestration.workflow.unpublishedSuffix', ' · 有未发布更改') : ''}`
          : '--';
        return <EllipsisWithTooltip text={value} className="w-full overflow-hidden text-ellipsis whitespace-nowrap" />;
      },
    },
    {
      title: t('common.updatedBy', '更新人'),
      dataIndex: 'updated_by',
      key: 'updated_by',
      width: 110,
      render: (value: string) => <EllipsisWithTooltip text={value || '--'} className="w-full overflow-hidden text-ellipsis whitespace-nowrap" />,
    },
    { title: t('common.updatedTime', '更新时间'), dataIndex: 'updated_at', key: 'updated_at', width: 170, render: (value: string) => <span className="whitespace-nowrap tabular-nums">{value ? convertToLocalizedTime(value) : '--'}</span> },
    {
      title: t('common.actions', '操作'),
      key: 'actions',
      width: isMarket ? 168 : 136,
      fixed: 'right',
      render: (_, record) => (
        isMarket ? (
          <div className="flex items-center gap-1 whitespace-nowrap">
            <WorkflowPermission operation="View" area="market" instancePermissions={record.permission}>
              <Button type="link" size="small" onClick={() => router.push(`/workflow/market/${record.id}?mode=view`)}>
                {t('common.view', '查看')}
              </Button>
            </WorkflowPermission>
            <WorkflowPermission operation="Add" area="market">
              <Button
                type="link"
                size="small"
                loading={busyId === record.id}
                onClick={() => openMoreAction('duplicate', record)}
              >
                {t('workflowOrchestration.action.copyToWorkflows', '复制到流程')}
              </Button>
            </WorkflowPermission>
          </div>
        ) : (
          <div className="flex items-center gap-1 whitespace-nowrap">
            <WorkflowPermission operation={record.is_builtin ? 'View' : 'Edit'} instancePermissions={record.permission}>
              <Button
                type="link"
                size="small"
                onClick={() => router.push(`/workflow/workflows/${record.id}?mode=${record.is_builtin ? 'view' : 'edit'}`)}
              >
                {record.is_builtin ? t('common.view', '查看') : t('common.edit', '编辑')}
              </Button>
            </WorkflowPermission>
            <WorkflowPermission operation="Execute" instancePermissions={record.permission}>
              <Tooltip title={runDisabledReason(record) || undefined}>
                <span><Button type="link" size="small" disabled={Boolean(runDisabledReason(record))} onClick={() => void execute(record)}>{t('workflowOrchestration.action.run', '运行')}</Button></span>
              </Tooltip>
            </WorkflowPermission>
            <WorkflowPermission operation="View" instancePermissions={record.permission}>
              <Dropdown
                trigger={['click']}
                menu={{ items: moreActions(record), onClick: ({ key }) => openMoreAction(key, record) }}
              >
                <Button
                  type="text"
                  size="small"
                  loading={busyId === record.id}
                  aria-label={t('workflowOrchestration.action.moreFor', '更多操作：{name}', { name: record.name })}
                  icon={<MoreOutlined />}
                />
              </Dropdown>
            </WorkflowPermission>
          </div>
        )
      ),
    },
  ];
  const visibleColumns = isMarket
    ? columns.filter((column) => !['status', 'enabled', 'version', 'organization'].includes(String(column.key)))
    : columns;

  return <main className="flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-[var(--color-bg-1)] p-4">
    <WorkflowTablePanel
      filters={<Input.Search className="w-[220px]" allowClear enterButton placeholder={t('workflowOrchestration.workflow.searchPlaceholder', '搜索流程名称')} value={queryDraft} onChange={(event) => { const value = event.target.value; setQueryDraft(value); if (!value) { setPagination((item) => ({ ...item, current: 1 })); setQuery(''); } }} onSearch={(value) => { setPagination((item) => ({ ...item, current: 1 })); setQuery(value.trim()); }} />}
      actions={<><WorkflowPermission operation="View" area={permissionArea}><Button aria-label={t('workflowOrchestration.workflow.refresh', '刷新流程列表')} icon={<ReloadOutlined />} onClick={() => void load()} /></WorkflowPermission>{isMarket ? null : <><WorkflowPermission operation="View"><Button icon={<DownloadOutlined />} loading={exporting} disabled={!selectedRowKeys.length} onClick={() => void exportWorkflows()}>{t('workflowOrchestration.workflow.export', '导出')}</Button></WorkflowPermission><WorkflowPermission operation="Add"><Button icon={<UploadOutlined />} loading={importing} onClick={() => setImportOpen(true)}>{t('workflowOrchestration.workflow.import', '导入')}</Button></WorkflowPermission><WorkflowPermission operation="Add"><Button type="primary" icon={<PlusOutlined />} onClick={() => setProfile({ mode: 'create' })}>{t('common.new', '新建')}</Button></WorkflowPermission></>}</>}
    >
      <CustomTable rowKey="id" loading={loading} columns={visibleColumns} dataSource={records} className="[&_.ant-table-cell]:whitespace-nowrap" rowSelection={isMarket ? undefined : { selectedRowKeys, preserveSelectedRowKeys: true, onChange: (keys) => setSelectedRowKeys(keys.map((key) => Number(key)).filter((key) => Number.isInteger(key) && key > 0)) }} locale={{ emptyText: <Empty description={isMarket ? t('workflowOrchestration.workflow.marketEmpty', '还没有内置流程') : t('workflowOrchestration.workflow.empty', '当前组织还没有流程')} /> }} pagination={{ current: pagination.current, pageSize: pagination.pageSize, total: count, showSizeChanger: true, pageSizeOptions: [10, 20, 50, 100], onChange: (current, pageSize) => setPagination({ current, pageSize }) }} onChange={(_, tableFilters, __, extra) => {
        if (extra.action !== 'filter') return;
        setStatus(tableFilters.status?.[0] as ListStatus | undefined);
        setEnabledFilter(tableFilters.enabled?.[0] as EnabledFilter | undefined);
        setPagination((item) => ({ ...item, current: 1 }));
      }} />
    </WorkflowTablePanel>
    <WorkflowImportDialog
      open={!isMarket && importOpen}
      confirmLoading={importing}
      onCancel={() => { if (!importing) setImportOpen(false); }}
      onSubmit={(value) => void importWorkflows(value.team, value.file)}
    />
    <WorkflowProfileDialog
      open={Boolean(profile)}
      mode={profile?.mode || 'create'}
      workflow={profile?.workflow}
      marketCopy={isMarket && profile?.mode === 'copy'}
      confirmLoading={profileBusy}
      permissionOperation={profile?.mode === 'edit' ? 'Edit' : 'Add'}
      permissionArea={isMarket ? 'market' : 'workflows'}
      onCancel={() => setProfile(null)}
      onSubmit={(value) => void submitProfile(value)}
    />
    {runWorkflow && <WorkflowLaunchDialog open title={t('workflowOrchestration.workflow.runTitle', '运行流程')} subTitle={runWorkflow.name} planUrl={`${API}/workflows/${runWorkflow.id}/launch-plan/`} submitUrl={`${API}/workflows/${runWorkflow.id}/run/`} instancePermissions={runWorkflow.permission} onClose={() => setRunWorkflow(undefined)} onSubmittingChange={() => undefined} onStarted={(execution: ExecutionRecord) => { setRunWorkflow(undefined); router.push(`/workflow/executions/${execution.id}`); }} />}
  </main>;
}
