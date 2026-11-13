'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Button, Drawer, Form, Input, Modal, Select, Tag, TimePicker, Tooltip, message } from 'antd';
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';

import CustomTable from '@/components/custom-table';
import OperateModal from '@/components/operate-modal';
import PermissionWrapper from '@/components/permission';
import SearchActionBar from '@/components/search-action-bar';
import { useIntegrationCenterApi } from '@/app/system-manager/api/integration-center';
import SystemManagerEntityGrid from '@/app/system-manager/components/system-manager-entity-grid';
import SystemManagerUnifiedCard from '@/app/system-manager/components/system-manager-unified-card';
import type { BusinessTemplate, ProviderManifest } from '@/app/system-manager/types/integration-center';
import { resolveExternalFieldOptionLabel, resolveImNotificationFieldPatches } from '@/app/system-manager/utils/imNotificationUtils';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import useApiClient from '@/utils/request';
import { useTranslation } from '@/utils/i18n';

interface AccountAssociation {
  id: number;
  name: string;
  integration_instance: number;
  integration_instance_name: string;
  provider_key: string;
  platform_match_field: string;
  external_match_field: string;
  external_receive_field: string;
  schedule_config: { enabled?: boolean; sync_time?: string };
  status: 'pending_sync' | 'ready' | 'needs_resync' | string;
  updated_at?: string;
  created_at?: string;
}

interface InstanceOption {
  id: number;
  name: string;
  provider_key?: string;
  provider_name?: string;
}

interface RecordRow {
  id: number;
  account_association_name?: string;
  trigger_mode: string;
  status: string;
  summary: string;
  matched_count: number;
  unmatched_count: number;
  conflict_count: number;
  started_at: string;
  finished_at: string | null;
}

const RUN_STATUS_TAG: Record<string, string> = {
  running: 'processing',
  success: 'success',
  failed: 'error',
  partial: 'default',
};

interface Paged<T> {
  count?: number;
  items?: T[];
}

export interface AccountAssociationPanelProps {
  filterInstanceId?: number | null;
  filterProvider?: string;
  openCreate?: boolean;
}

const PLATFORM_FIELDS = [
  { value: 'username', labelKey: 'system.channel.imNotificationPage.platformFieldOption.username' },
  { value: 'email', labelKey: 'system.channel.imNotificationPage.platformFieldOption.email' },
  { value: 'phone', labelKey: 'system.channel.imNotificationPage.platformFieldOption.phone' },
];

const PLATFORM_FIELD_MAP: Record<string, string> = {
  username: 'system.channel.imNotificationPage.platformFieldOption.username',
  email: 'system.channel.imNotificationPage.platformFieldOption.email',
  phone: 'system.channel.imNotificationPage.platformFieldOption.phone',
};

const normalizeList = <T,>(response: T[] | { items?: T[] } | null | undefined): T[] => {
  if (Array.isArray(response)) return response;
  return response?.items || [];
};

const templateFor = (providerKey: string | undefined, providers: ProviderManifest[]): BusinessTemplate | null => {
  if (!providerKey) return null;
  const provider = providers.find((item) => item.key === providerKey);
  const capability = provider?.capabilities.find((item) => item.key === 'im_notification');
  if (!provider || !capability?.business_template) return null;
  return provider.business_templates?.[capability.business_template] ?? null;
};

const AccountAssociationPanel: React.FC<AccountAssociationPanelProps> = ({
  filterInstanceId = null,
  filterProvider = '',
  openCreate = false,
}) => {
  const { t } = useTranslation();
  const { convertToLocalizedTime } = useLocalizedTime();
  const { get, post, put, del } = useApiClient();
  const { getProviders } = useIntegrationCenterApi();
  const [form] = Form.useForm();
  const [rows, setRows] = useState<AccountAssociation[]>([]);
  const [instances, setInstances] = useState<InstanceOption[]>([]);
  const [providers, setProviders] = useState<ProviderManifest[]>([]);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState<AccountAssociation | null>(null);
  const [recordsOpen, setRecordsOpen] = useState(false);
  const [recordRows, setRecordRows] = useState<RecordRow[]>([]);
  const [recordsLoading, setRecordsLoading] = useState(false);
  const [recordsSearch, setRecordsSearch] = useState('');
  const [recordsPagination, setRecordsPagination] = useState({ current: 1, total: 0, pageSize: 10 });
  const appliedLink = useRef(false);
  const watchedInstance = Form.useWatch('integration_instance', form);
  const watchedSchedule = Form.useWatch('schedule_mode', form);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = filterInstanceId ? { integration_instance: filterInstanceId } : undefined;
      const response = await get<AccountAssociation[] | { items: AccountAssociation[] }>('/system_mgmt/im_account_association/', { params });
      setRows(normalizeList(response));
    } catch {
      message.error(t('common.fetchFailed'));
    } finally {
      setLoading(false);
    }
  }, [filterInstanceId, get, t]);

  useEffect(() => {
    load();
    get<InstanceOption[] | { items: InstanceOption[] }>('/system_mgmt/integration_instance/available_instances/', {
      params: { capability: 'im_notification' },
    }).then((response) => setInstances(normalizeList(response))).catch(() => setInstances([]));
    getProviders().then((response) => setProviders(response || [])).catch(() => setProviders([]));
    // 实例和供应商清单只在进入页签时取一次。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [load]);

  const visibleRows = useMemo(
    () => rows.filter((row) => !filterProvider || row.provider_key === filterProvider),
    [filterProvider, rows],
  );

  const selectedInstance = instances.find((item) => item.id === watchedInstance);
  const fieldTemplate = templateFor(selectedInstance?.provider_key, providers);
  const externalMatchOptions = (fieldTemplate?.matchable_fields || []).map((field) => ({
    value: field,
    label: resolveExternalFieldOptionLabel(field, fieldTemplate?.external_field_labels),
  }));
  const externalReceiveOptions = (fieldTemplate?.receivable_fields || []).map((field) => ({
    value: field,
    label: resolveExternalFieldOptionLabel(field, fieldTemplate?.external_field_labels),
  }));

  useEffect(() => {
    if (!editorOpen) return;
    const nextValues = resolveImNotificationFieldPatches({
      editing: Boolean(editing),
      currentMatch: form.getFieldValue('external_match_field'),
      currentReceive: form.getFieldValue('external_receive_field'),
      template: fieldTemplate,
    });
    const names = Object.keys(nextValues) as Array<keyof typeof nextValues>;
    if (names.length > 0) {
      form.setFields(names.map((name) => ({ name, value: nextValues[name] })));
    }
  }, [editing, editorOpen, fieldTemplate, form]);

  const openEditor = (record: AccountAssociation | null, instanceId?: number) => {
    setEditing(record);
    const scheduleEnabled = Boolean(record?.schedule_config?.enabled);
    form.resetFields();
    form.setFieldsValue(record ? {
      name: record.name,
      integration_instance: record.integration_instance,
      platform_match_field: record.platform_match_field,
      external_match_field: record.external_match_field,
      external_receive_field: record.external_receive_field,
      schedule_mode: scheduleEnabled ? 'daily' : 'manual',
      sync_time: record.schedule_config?.sync_time || '02:00',
    } : {
      integration_instance: instanceId,
      platform_match_field: 'email',
      schedule_mode: 'manual',
      sync_time: '02:00',
    });
    setEditorOpen(true);
  };

  const fetchRecords = useCallback(async (current = 1, pageSize = recordsPagination.pageSize, search = recordsSearch) => {
    setRecordsLoading(true);
    try {
      const params: Record<string, unknown> = { page: current, page_size: pageSize };
      if (search) params.search = search;
      if (filterInstanceId) params.integration_instance = filterInstanceId;
      const response = await get<Paged<RecordRow>>('/system_mgmt/im_account_association/records/', { params });
      setRecordRows(response?.items || []);
      setRecordsPagination({ current, pageSize, total: response?.count || 0 });
    } catch {
      setRecordRows([]);
    } finally {
      setRecordsLoading(false);
    }
  }, [filterInstanceId, get, recordsPagination.pageSize, recordsSearch]);

  const openRecords = () => {
    setRecordsOpen(true);
    setRecordsSearch('');
    fetchRecords(1, recordsPagination.pageSize, '');
  };

  useEffect(() => {
    if (appliedLink.current || loading || !openCreate) return;
    appliedLink.current = true;
    openEditor(null, filterInstanceId || undefined);
  }, [filterInstanceId, loading, openCreate]);

  const save = async () => {
    const values = await form.validateFields();
    const payload = {
      name: values.name,
      integration_instance: values.integration_instance,
      platform_match_field: values.platform_match_field,
      external_match_field: values.external_match_field,
      external_receive_field: values.external_receive_field,
      schedule_config: values.schedule_mode === 'daily'
        ? { enabled: true, sync_time: values.sync_time }
        : { enabled: false },
    };
    setSaving(true);
    try {
      if (editing) {
        await put(`/system_mgmt/im_account_association/${editing.id}/`, payload);
      } else {
        await post('/system_mgmt/im_account_association/', payload);
      }
      message.success(t('common.saveSuccess'));
      setEditorOpen(false);
      await load();
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('common.error'));
    } finally {
      setSaving(false);
    }
  };

  const [updatingId, setUpdatingId] = useState<number | null>(null);

  const updateAssociation = async (record: AccountAssociation) => {
    setUpdatingId(record.id);
    try {
      await post(`/system_mgmt/im_account_association/${record.id}/update_association/`);
      message.success(t('system.user.accountAssociation.updated', '已开始更新关联'));
      await load();
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('common.operationFailed'));
    } finally {
      setUpdatingId(null);
    }
  };

  const removeAssociation = (record: AccountAssociation) => {
    Modal.confirm({
      title: t('system.user.accountAssociation.deleteConfirm', '删除这个账号关联？'),
      content: t(
        'system.user.accountAssociation.deleteConfirmContent',
        '删除「{name}」后，映射结果和同步记录会一起删除，不能恢复。仍被 IM 应用通知选用时，需要先改选其他账号关联才能删除。',
      ).replace('{name}', record.name),
      okType: 'danger',
      onOk: async () => {
        await del(`/system_mgmt/im_account_association/${record.id}/`);
        message.success(t('common.delSuccess'));
        await load();
      },
    });
  };

  const statusLabel = (status: string) => {
    if (status === 'ready') return t('system.user.accountAssociation.statusReady', '可用');
    if (status === 'needs_resync') return t('system.user.accountAssociation.statusNeedsResync', '需重新同步');
    return t('system.user.accountAssociation.statusPending', '待同步');
  };

  const statusClass = (status: string) => {
    if (status === 'ready') return 'text-[var(--color-success)]';
    if (status === 'needs_resync') return 'text-[var(--color-warning)]';
    return 'text-[var(--color-text-4)]';
  };

  const resolvePlatformFieldLabel = useCallback((field: string) => {
    const key = PLATFORM_FIELD_MAP[field];
    return key ? t(key, field) : field;
  }, [t]);

  const resolveExternalFieldLabel = useCallback((providerKey: string | undefined, field: string) => {
    const template = templateFor(providerKey, providers);
    return resolveExternalFieldOptionLabel(field, template?.external_field_labels);
  }, [providers]);

  const getCardDescription = useCallback((item: AccountAssociation) => {
    const platform = resolvePlatformFieldLabel(item.platform_match_field);
    const external = resolveExternalFieldLabel(item.provider_key, item.external_match_field);
    return `${platform} → ${external}`;
  }, [resolveExternalFieldLabel, resolvePlatformFieldLabel]);

  const scheduleText = (record: AccountAssociation) => (
    record.schedule_config?.enabled
      ? `${t('system.user.accountAssociation.daily', '每天')} ${record.schedule_config.sync_time || ''}`.trim()
      : t('system.user.accountAssociation.manual', '手动')
  );

  const renderTime = (value: string | null | undefined) => (
    value ? convertToLocalizedTime(value, 'YYYY-MM-DD HH:mm') : '--'
  );

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await load();
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <>
      <SystemManagerEntityGrid
        items={visibleRows}
        loading={loading}
        searchPlaceholder={t('system.user.accountAssociation.search', '搜索账号关联')}
        actions={(
          <>
            <Button onClick={openRecords} disabled={rows.length === 0}>
              {t('system.user.accountAssociation.records', '同步记录')}
            </Button>
            <Button icon={<ReloadOutlined />} onClick={handleRefresh} loading={refreshing}>
              {t('common.refresh')}
            </Button>
            <PermissionWrapper requiredPermissions={['Add']}>
              <Button type="primary" icon={<PlusOutlined />} onClick={() => openEditor(null, filterInstanceId || undefined)}>
                {t('common.new')}
              </Button>
            </PermissionWrapper>
          </>
        )}
        getItemKey={(item) => item.id}
        getSearchText={(item) => `${item.name} ${item.integration_instance_name}`}
        renderCard={(item) => {
          const externalReceiveLabel = resolveExternalFieldLabel(item.provider_key, item.external_receive_field);

          return (
            <SystemManagerUnifiedCard
              name={item.name}
              description={getCardDescription(item)}
              icon={item.provider_key || 'shezhi'}
              caption={item.integration_instance_name}
              menuItems={[
                {
                  key: 'edit',
                  label: t('common.edit'),
                  onClick: () => openEditor(item),
                },
                {
                  key: 'delete',
                  label: t('common.delete'),
                  danger: true,
                  onClick: () => removeAssociation(item),
                },
              ]}
              body={(
                <div className="flex flex-col gap-2">
                  <div className="grid grid-cols-2 gap-1">
                    <div className="rounded-md bg-[var(--color-fill-1)] px-3 py-2.5">
                      <div
                        className="truncate text-sm font-medium leading-none text-[var(--color-text-1)]"
                        title={externalReceiveLabel || item.external_receive_field}
                      >
                        {externalReceiveLabel || item.external_receive_field}
                      </div>
                      <div className="mt-1.5 truncate text-xs text-[var(--color-text-3)]">
                        {t('system.user.accountAssociation.receiveField', '消息接收标识')}
                      </div>
                    </div>
                    <div className="rounded-md bg-[var(--color-fill-1)] px-3 py-2.5">
                      <div className="truncate text-sm font-medium leading-none text-[var(--color-text-1)]">
                        {scheduleText(item)}
                      </div>
                      <div className="mt-1.5 truncate text-xs text-[var(--color-text-3)]">
                        {t('system.user.accountAssociation.updateCycle', '更新周期')}
                      </div>
                    </div>
                  </div>

                  <div
                    className="flex min-w-0 items-center justify-between gap-2"
                    onClick={(event) => event.stopPropagation()}
                  >
                    <div className="min-w-0 truncate text-xs leading-5 text-[var(--color-text-3)]">
                      <span>{t('system.user.accountAssociation.latestSyncLabel', '最近同步：')}</span>
                      <span className="tabular-nums">{renderTime(item.updated_at)}</span>
                      <span className="mx-1">·</span>
                      <span className={statusClass(item.status)}>{statusLabel(item.status)}</span>
                    </div>
                    <PermissionWrapper requiredPermissions={['Edit']}>
                      <Button
                        type="primary"
                        size="small"
                        loading={updatingId === item.id}
                        className="shrink-0 font-mini"
                        onClick={() => updateAssociation(item)}
                      >
                        {t('system.user.accountAssociation.update', '更新关联')}
                      </Button>
                    </PermissionWrapper>
                  </div>
                </div>
              )}
            />
          );
        }}
      />

      <OperateModal
        title={editing ? t('common.edit') : t('common.new')}
        open={editorOpen}
        confirmLoading={saving}
        onOk={save}
        onCancel={() => !saving && setEditorOpen(false)}
        width={640}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label={t('common.name')} rules={[{ required: true, whitespace: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="integration_instance" label={t('system.channel.imNotificationPage.integrationInstance')} rules={[{ required: true }]}>
            <Select
              disabled={Boolean(editing)}
              options={instances.map((item) => ({
                value: item.id,
                label: item.provider_name ? `${item.name}（${item.provider_name}）` : item.name,
              }))}
            />
          </Form.Item>
          <div className="mb-6">
            <div className="mb-2 text-[16px] font-semibold text-[var(--color-text-1)]">
              {t('system.channel.imNotificationPage.fieldMappingTitle')}
            </div>
            <div className="mb-5 text-[13px] text-[var(--color-text-3)]">
              {t('system.channel.imNotificationPage.fieldMappingDesc')}
            </div>
            <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg)] px-4 py-4">
              <div className="grid grid-cols-[minmax(0,1fr)_24px_minmax(0,1fr)] gap-x-4 text-[13px] text-[var(--color-text-3)]">
                <div>{t('system.channel.imNotificationPage.platformMatchField')}</div>
                <div />
                <div>{t('system.channel.imNotificationPage.externalMatchField')}</div>
              </div>
              <div className="mt-3 grid grid-cols-[minmax(0,1fr)_24px_minmax(0,1fr)] items-start gap-x-4">
                <Form.Item name="platform_match_field" rules={[{ required: true }]} className="mb-0">
                  <Select options={PLATFORM_FIELDS.map((item) => ({ value: item.value, label: t(item.labelKey) }))} />
                </Form.Item>
                <div className="flex h-8 items-center justify-center text-lg text-[var(--color-primary)]">=</div>
                <Form.Item name="external_match_field" rules={[{ required: true }]} className="mb-0">
                  <Select
                    options={externalMatchOptions}
                    disabled={!watchedInstance || externalMatchOptions.length === 0}
                    placeholder={t('system.channel.imNotificationPage.externalMatchFieldPlaceholder')}
                  />
                </Form.Item>
              </div>
              {watchedInstance && externalMatchOptions.length === 0 ? (
                <div className="mt-3 text-[12px] text-[var(--color-text-3)]">
                  {t('system.channel.imNotificationPage.matchFieldUnavailableHint')}
                </div>
              ) : null}
            </div>
          </div>
          <Form.Item name="external_receive_field" label={t('system.user.accountAssociation.receiveField', '消息接收标识')} rules={[{ required: true }]}>
            <Select
              options={externalReceiveOptions}
              disabled={!watchedInstance || externalReceiveOptions.length === 0}
              placeholder={t('system.user.accountAssociation.receiveFieldPlaceholder', '请选择消息接收标识')}
            />
          </Form.Item>
          <Form.Item name="schedule_mode" label={t('system.user.accountAssociation.schedule', '定时')}>
            <Select
              options={[
                { value: 'manual', label: t('system.user.accountAssociation.manual', '手动') },
                { value: 'daily', label: t('system.user.accountAssociation.daily', '每天') },
              ]}
            />
          </Form.Item>
          {watchedSchedule === 'daily' ? (
            <Form.Item
              name="sync_time"
              label={t('system.user.accountAssociation.time', '时间')}
              rules={[{ required: true }]}
              getValueProps={(value) => ({ value: value ? dayjs(value, 'HH:mm') : null })}
              normalize={(value) => (value ? dayjs(value).format('HH:mm') : '')}
            >
              <TimePicker format="HH:mm" />
            </Form.Item>
          ) : null}
        </Form>
      </OperateModal>

      <Drawer
        title={t('system.user.accountAssociation.records', '同步记录')}
        open={recordsOpen}
        width={980}
        onClose={() => setRecordsOpen(false)}
      >
        <div className="mb-4">
          <SearchActionBar
            spacing="flush"
            searchClassName="!w-60"
            searchProps={{
              size: 'middle',
              allowClear: true,
              enterButton: true,
              placeholder: `${t('common.search')}...`,
              onSearch: (value) => {
                setRecordsSearch(value);
                fetchRecords(1, recordsPagination.pageSize, value);
              },
            }}
            actions={(
              <Button
                icon={<ReloadOutlined />}
                onClick={() => fetchRecords(recordsPagination.current, recordsPagination.pageSize, recordsSearch)}
                loading={recordsLoading}
              >
                {t('common.refresh')}
              </Button>
            )}
          />
        </div>
        <CustomTable
          rowKey="id"
          scroll={{ x: '100%', y: 'calc(100vh - 280px)' }}
          dataSource={recordRows}
          loading={recordsLoading}
          pagination={{
            ...recordsPagination,
            onChange: (current, pageSize) => {
              const nextPage = pageSize !== recordsPagination.pageSize ? 1 : current;
              fetchRecords(nextPage, pageSize, recordsSearch);
            },
          }}
          columns={[
            {
              title: t('common.name'),
              dataIndex: 'account_association_name',
              key: 'account_association_name',
              width: 160,
              ellipsis: true,
            },
            {
              title: t('system.channel.imNotificationPage.recordColumns.startedAt'),
              dataIndex: 'started_at',
              key: 'started_at',
              width: 180,
              render: (value: string) => convertToLocalizedTime(value, 'YYYY-MM-DD HH:mm:ss'),
            },
            {
              title: t('system.channel.imNotificationPage.recordColumns.triggerMode'),
              dataIndex: 'trigger_mode',
              key: 'trigger_mode',
              width: 100,
              render: (value: string) => t(`system.channel.imNotificationPage.triggerMode.${value}`, value),
            },
            {
              title: t('system.channel.imNotificationPage.recordColumns.status'),
              dataIndex: 'status',
              key: 'status',
              width: 110,
              render: (status: string) => (
                <Tag color={RUN_STATUS_TAG[status] || 'default'}>
                  {t(`system.channel.imNotificationPage.syncRunStatus.${status}`, status)}
                </Tag>
              ),
            },
            {
              title: t('system.channel.imNotificationPage.recordColumns.matchedCount'),
              dataIndex: 'matched_count',
              key: 'matched_count',
              width: 90,
            },
            {
              title: t('system.channel.imNotificationPage.recordColumns.unmatchedCount'),
              dataIndex: 'unmatched_count',
              key: 'unmatched_count',
              width: 100,
            },
            {
              title: t('system.channel.imNotificationPage.recordColumns.conflictCount'),
              dataIndex: 'conflict_count',
              key: 'conflict_count',
              width: 90,
            },
            {
              title: t('system.channel.imNotificationPage.recordColumns.summary'),
              dataIndex: 'summary',
              key: 'summary',
              ellipsis: true,
              render: (summary: string) => (
                <Tooltip title={summary}>
                  <span>{summary || '--'}</span>
                </Tooltip>
              ),
            },
          ]}
        />
      </Drawer>
    </>
  );
};

export default AccountAssociationPanel;
