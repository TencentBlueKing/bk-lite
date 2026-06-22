// Route: /system-manager/channel/im-notification
'use client';

import React, { useEffect, useMemo, useState } from 'react';
import dayjs from 'dayjs';
import { useRouter } from 'next/navigation';
import {
  Alert,
  Button,
  Drawer,
  Form,
  Input,
  message,
  Popconfirm,
  Select,
  Space,
  Switch,
  Tag,
  TimePicker,
} from 'antd';
import type { ColumnItem } from '@/types';
import {
  ArrowLeftOutlined,
  PlusOutlined,
} from '@ant-design/icons';
import OperateModal from '@/components/operate-modal';
import PermissionWrapper from '@/components/permission';
import CustomTable from '@/components/custom-table';
import PageLayout from '@/components/page-layout';
import TopSection from '@/components/top-section';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { useImNotificationApi } from '@/app/system-manager/api/im-notification';
import { useIntegrationCenterApi } from '@/app/system-manager/api/integration-center';
import type {
  BusinessTemplate,
  ProviderManifest,
} from '@/app/system-manager/types/integration-center';
import type {
  AvailableInstance,
  IMNotificationChannel,
  IMNotificationChannelPayload,
  IMNotificationSyncRun,
  IMNotificationUserMapping,
  PlatformMatchField,
} from '@/app/system-manager/types/im-notification';
import {
  buildSchedulePayload,
  getDisplayStatusColor,
  getDisplayStatusText,
  getSyncRunStatusColor,
  getSyncRunStatusText,
  getSyncTriggerModeText,
  isChannelSendReady,
  isChannelSyncRunning,
  parseScheduleConfig,
  parseReceiversInput,
} from '@/app/system-manager/utils/imNotificationUtils';
import { useTranslation } from '@/utils/i18n';

interface PaginationState {
  current: number;
  total: number;
  pageSize: number;
}

interface IMNotificationChannelFormValues extends IMNotificationChannelPayload {
  schedule_enabled?: boolean;
  sync_time?: string;
}

const PLATFORM_MATCH_FIELD_OPTIONS: PlatformMatchField[] = ['username', 'email', 'phone'];

function getResolvedImTemplate(
  instanceId: number | undefined,
  availableInstances: AvailableInstance[],
  providers: ProviderManifest[],
): BusinessTemplate | null {
  if (!instanceId) return null;
  const instance = availableInstances.find((item) => item.id === instanceId);
  if (!instance) return null;
  const provider = providers.find((item) => item.key === instance.provider_key);
  if (!provider) return null;
  const capability = provider.capabilities.find((item) => item.key === 'im_notification');
  if (!capability?.business_template) return null;
  return provider.business_templates?.[capability.business_template] ?? null;
}

function buildLatestSyncSummary(
  record: IMNotificationChannel,
  t: (key: string, defaultMessage?: string, values?: Record<string, string | number>) => string,
): string {
  const total = record.latest_sync_total_external_user_count;
  const matched = record.latest_sync_matched_count;
  const unmatched = record.latest_sync_unmatched_count ?? 0;
  const conflict = record.latest_sync_conflict_count ?? 0;

  if (typeof total === 'number' && typeof matched === 'number') {
    if (unmatched > 0 && conflict > 0) {
      return t(
        'system.channel.imNotificationPage.latestSyncMatchedUnmatchedConflictSummary',
        'Matched {matched} of {total} external users, {unmatched} unmatched, {conflict} conflicts',
        { matched, total, unmatched, conflict },
      );
    }
    if (unmatched > 0) {
      return t(
        'system.channel.imNotificationPage.latestSyncMatchedUnmatchedSummary',
        'Matched {matched} of {total} external users, {unmatched} unmatched',
        { matched, total, unmatched },
      );
    }
    if (conflict > 0) {
      return t(
        'system.channel.imNotificationPage.latestSyncMatchedConflictSummary',
        'Matched {matched} of {total} external users, {conflict} conflicts',
        { matched, total, conflict },
      );
    }
    return t(
      'system.channel.imNotificationPage.latestSyncMatchedSummary',
      'Matched {matched} of {total} external users',
      { matched, total },
    );
  }

  return record.latest_sync_summary || getSyncRunStatusText(record.latest_sync_status, t);
}

function renderSyncPeriod(
  record: IMNotificationChannel,
  t: (key: string, defaultMessage?: string, values?: Record<string, string | number>) => string,
) {
  const scheduleEnabled = record.schedule_config?.enabled;
  const syncTime = record.schedule_config?.sync_time;

  if (!scheduleEnabled) {
    return (
      <div className="leading-6">
        <div className="text-base font-semibold text-[var(--color-text-1)]">
          {t('system.channel.imNotificationPage.syncPeriodManualTitle')}
        </div>
        <div className="font-xs text-[var(--color-text-3)]">
          {t('system.channel.imNotificationPage.syncPeriodManualDesc')}
        </div>
      </div>
    );
  }

  return (
    <div className="leading-6">
      <div className="text-base font-semibold text-[var(--color-text-1)]">
        {syncTime
          ? `${t('system.channel.imNotificationPage.syncPeriodDailyTitle')} ${syncTime}`
          : t('system.channel.imNotificationPage.syncPeriodDailyTitle')}
      </div>
      <div className="text-xs text-[var(--color-text-3)]">
        {t('system.channel.imNotificationPage.syncPeriodDailyDesc')}
      </div>
    </div>
  );
}

const ImNotificationPage: React.FC = () => {
  const { t } = useTranslation();
  const { convertToLocalizedTime } = useLocalizedTime();
  const router = useRouter();
  const {
    getChannels,
    createChannel,
    updateChannel,
    deleteChannel,
    getAvailableInstances,
    syncMappings,
    getMappings,
    getRecords,
    testSend,
  } = useImNotificationApi();
  const { getProviders } = useIntegrationCenterApi();

  const [channels, setChannels] = useState<IMNotificationChannel[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchText, setSearchText] = useState('');

  const [form] = Form.useForm<IMNotificationChannelFormValues>();
  const watchedIntegrationInstance = Form.useWatch('integration_instance', form);
  const [modalOpen, setModalOpen] = useState(false);
  const [modalLoading, setModalLoading] = useState(false);
  const [editing, setEditing] = useState<IMNotificationChannel | null>(null);
  const [availableInstances, setAvailableInstances] = useState<AvailableInstance[]>([]);
  const [providers, setProviders] = useState<ProviderManifest[]>([]);

  const [mappingsOpen, setMappingsOpen] = useState(false);
  const [mappingsChannel, setMappingsChannel] = useState<IMNotificationChannel | null>(null);
  const [mappings, setMappings] = useState<IMNotificationUserMapping[]>([]);
  const [mappingsLoading, setMappingsLoading] = useState(false);

  const [recordsOpen, setRecordsOpen] = useState(false);
  const [recordsChannel, setRecordsChannel] = useState<IMNotificationChannel | null>(null);
  const [records, setRecords] = useState<IMNotificationSyncRun[]>([]);
  const [recordsLoading, setRecordsLoading] = useState(false);

  const [testForm] = Form.useForm();
  const [testOpen, setTestOpen] = useState(false);
  const [testLoading, setTestLoading] = useState(false);
  const [testChannel, setTestChannel] = useState<IMNotificationChannel | null>(null);

  const [pagination, setPagination] = useState<PaginationState>({
    current: 1,
    total: 0,
    pageSize: 10,
  });
  const [mapPagination, setMapPagination] = useState<PaginationState>({
    current: 1,
    total: 0,
    pageSize: 10,
  });
  const [recordsPagination, setRecordsPagination] = useState<PaginationState>({
    current: 1,
    total: 0,
    pageSize: 10,
  });

  const resolvedTemplate = useMemo(
    () => getResolvedImTemplate(watchedIntegrationInstance, availableInstances, providers),
    [availableInstances, providers, watchedIntegrationInstance],
  );

  const externalMatchOptions = useMemo(
    () =>
      (resolvedTemplate?.matchable_fields || []).map((field) => ({
        value: field,
        label: t(`system.channel.imNotificationPage.externalFieldOption.${field}`, field),
      })),
    [resolvedTemplate, t],
  );

  const externalReceiveOptions = useMemo(
    () =>
      (resolvedTemplate?.receivable_fields || []).map((field) => ({
        value: field,
        label: t(`system.channel.imNotificationPage.externalFieldOption.${field}`, field),
      })),
    [resolvedTemplate, t],
  );

  const platformMatchOptions = useMemo(
    () =>
      PLATFORM_MATCH_FIELD_OPTIONS.map((field) => ({
        value: field,
        label: t(`system.channel.imNotificationPage.platformFieldOption.${field}`),
      })),
    [t],
  );

  const fetchChannels = async (current = pagination.current, pageSize = pagination.pageSize) => {
    setLoading(true);
    try {
      const { count, items } = await getChannels({
        page: current,
        page_size: pageSize,
      });
      setChannels(items);
      setPagination((prev) => ({
        ...prev,
        current,
        pageSize,
        total: count,
      }));
    } catch {
      message.error(t('common.fetchFailed'));
    } finally {
      setLoading(false);
    }
  };

  const fetchMeta = async () => {
    try {
      const [instancesData, providersData] = await Promise.all([
        getAvailableInstances(),
        getProviders(),
      ]);
      setAvailableInstances(instancesData ?? []);
      setProviders(providersData ?? []);
    } catch {
      setAvailableInstances([]);
      setProviders([]);
    }
  };

  useEffect(() => {
    fetchChannels(1, pagination.pageSize);
    fetchMeta();
  }, []);

  useEffect(() => {
    if (!modalOpen) return;

    const currentMatch = form.getFieldValue('external_match_field');
    const currentReceive = form.getFieldValue('external_receive_field');
    const nextValues: Partial<IMNotificationChannelPayload> = {};

    const matchableFields = resolvedTemplate?.matchable_fields || [];
    const receivableFields = resolvedTemplate?.receivable_fields || [];

    if (currentMatch && !matchableFields.includes(currentMatch)) {
      nextValues.external_match_field = undefined;
    }
    if (currentReceive && !receivableFields.includes(currentReceive)) {
      nextValues.external_receive_field = undefined;
    }

    if (!editing) {
      const nextMatch = nextValues.external_match_field ?? currentMatch;
      const nextReceive = nextValues.external_receive_field ?? currentReceive;

      if (!nextMatch && resolvedTemplate?.default_external_match_field) {
        nextValues.external_match_field = resolvedTemplate.default_external_match_field;
      }
      if (!nextReceive && resolvedTemplate?.default_external_receive_field) {
        nextValues.external_receive_field = resolvedTemplate.default_external_receive_field;
      }
    }

    if (Object.keys(nextValues).length > 0) {
      form.setFieldsValue(nextValues);
    }
  }, [editing, form, modalOpen, resolvedTemplate]);

  const filteredChannels = channels.filter((channel) =>
    channel.name.toLowerCase().includes(searchText.toLowerCase())
  );

  const openModal = async (record: IMNotificationChannel | null) => {
    setEditing(record);
    if (record) {
      form.setFieldsValue({
        name: record.name,
        integration_instance: record.integration_instance,
        description: record.description,
        enabled: record.enabled,
        status: record.status,
        platform_match_field: record.platform_match_field,
        external_match_field: record.external_match_field,
        external_receive_field: record.external_receive_field,
        schedule_enabled: parseScheduleConfig(record.schedule_config).scheduleEnabled,
        sync_time: parseScheduleConfig(record.schedule_config).syncTime,
        team: record.team ?? [],
      });
    } else {
      form.resetFields();
      form.setFieldsValue({
        enabled: true,
        schedule_enabled: false,
        sync_time: '',
        team: [],
        platform_match_field: 'email',
      });
    }
    await fetchMeta();
    setModalOpen(true);
  };

  const handleToggleEnabled = async (record: IMNotificationChannel, checked: boolean) => {
    try {
      const nextStatus = checked ? record.status : 'disabled';
      await updateChannel(record.id, { enabled: checked, status: nextStatus });
      setChannels((prev) =>
        prev.map((channel) =>
          channel.id === record.id
            ? {
              ...channel,
              enabled: checked,
              status: nextStatus,
              display_status: checked ? channel.display_status : 'disabled',
            }
            : channel
        )
      );
    } catch {
      message.error(t('common.operationFailed'));
    }
  };

  const handleDelete = async (record: IMNotificationChannel) => {
    try {
      await deleteChannel(record.id);
      message.success(t('common.delSuccess'));
      setChannels((prev) => prev.filter((channel) => channel.id !== record.id));
    } catch {
      message.error(t('common.delFailed'));
    }
  };

  const handleModalOk = async () => {
    try {
      const values = await form.validateFields();
      setModalLoading(true);
      const payload: IMNotificationChannelPayload = {
        name: values.name,
        integration_instance: values.integration_instance,
        description: values.description || '',
        enabled: values.enabled ?? true,
        status: values.status,
        platform_match_field: values.platform_match_field,
        external_match_field: values.external_match_field,
        external_receive_field: values.external_receive_field,
        schedule_config: buildSchedulePayload(values.schedule_enabled ?? false, values.sync_time),
        team: values.team ?? [],
      };
      if (editing) {
        const updated = await updateChannel(editing.id, payload);
        setChannels((prev) => prev.map((channel) => (channel.id === editing.id ? updated : channel)));
        message.success(t('common.saveSuccess'));
      } else {
        await createChannel(payload);
        message.success(t('common.addSuccess'));
        await fetchChannels(1, pagination.pageSize);
      }
      setModalOpen(false);
    } catch (error) {
      if (error && typeof error === 'object' && 'errorFields' in error) return;
      message.error(t('common.operationFailed'));
    } finally {
      setModalLoading(false);
    }
  };

  const handleSyncMappings = async (record: IMNotificationChannel) => {
    try {
      await syncMappings(record.id);
      message.success(t('system.channel.imNotificationPage.syncMappingsStarted'));
      await fetchChannels(pagination.current, pagination.pageSize);
    } catch (error) {
      message.error(error instanceof Error ? error.message : t('system.channel.imNotificationPage.syncMappingsFailed'));
    }
  };

  const fetchMappings = async (channelId: number, current = 1, pageSize = mapPagination.pageSize) => {
    setMappingsLoading(true);
    try {
      const { count, items } = await getMappings(channelId, {
        page: current,
        page_size: pageSize,
      });
      setMappings(items ?? []);
      setMapPagination((prev) => ({
        ...prev,
        current,
        pageSize,
        total: count,
      }));
    } catch {
      message.error(t('common.fetchFailed'));
      setMappings([]);
    } finally {
      setMappingsLoading(false);
    }
  };

  const handleViewMappings = async (record: IMNotificationChannel) => {
    setMappingsChannel(record);
    setMappingsOpen(true);
    setMappings([]);
    await fetchMappings(record.id, 1, mapPagination.pageSize);
  };

  const fetchRecords = async (channelId: number, current = 1, pageSize = recordsPagination.pageSize) => {
    setRecordsLoading(true);
    try {
      const { count, items } = await getRecords(channelId, {
        page: current,
        page_size: pageSize,
      });
      setRecords(items ?? []);
      setRecordsPagination((prev) => ({
        ...prev,
        current,
        pageSize,
        total: count,
      }));
    } catch {
      message.error(t('common.fetchFailed'));
      setRecords([]);
    } finally {
      setRecordsLoading(false);
    }
  };

  const handleViewRecords = async (record: IMNotificationChannel) => {
    setRecordsChannel(record);
    setRecordsOpen(true);
    setRecords([]);
    await fetchRecords(record.id, 1, recordsPagination.pageSize);
  };

  const handleTestSend = (record: IMNotificationChannel) => {
    if (!isChannelSendReady(record.display_status)) return;
    setTestChannel(record);
    testForm.resetFields();
    testForm.setFieldsValue({
      title: 'Test Message',
      content: 'This is a test message.',
    });
    setTestOpen(true);
  };

  const handleTestSendOk = async () => {
    if (!testChannel) return;
    try {
      const values = await testForm.validateFields();
      setTestLoading(true);
      const receivers = parseReceiversInput(values.receivers ?? '');
      await testSend(testChannel.id, {
        title: values.title,
        content: values.content,
        receivers,
      });
      message.success(t('system.channel.imNotificationPage.testSendSuccess'));
      setTestOpen(false);
      await fetchChannels(pagination.current, pagination.pageSize);
    } catch (error) {
      if (error && typeof error === 'object' && 'errorFields' in error) return;
      message.error(error instanceof Error ? error.message : t('system.channel.imNotificationPage.testSendFailed'));
    } finally {
      setTestLoading(false);
    }
  };

  const handleBack = () => {
    router.push('/system-manager/channel');
  };

  const renderTime = (value: string | null | undefined) => {
    if (!value) return '--';
    return convertToLocalizedTime(value, 'YYYY-MM-DD HH:mm:ss');
  };

  const mappingColumns: ColumnItem[] = [
    {
      key: 'username',
      title: t('system.channel.imNotificationPage.mappingColumns.username'),
      dataIndex: 'username',
    },
    {
      key: 'external_display_name',
      title: t('system.channel.imNotificationPage.mappingColumns.externalDisplayName'),
      dataIndex: 'external_display_name',
    },
    {
      key: 'external_identity',
      title: t('system.channel.imNotificationPage.mappingColumns.externalIdentity'),
      dataIndex: 'external_identity_value',
      render: (_, record: IMNotificationUserMapping) => (
        <span>{`${record.external_identity_key}: ${record.external_identity_value}`}</span>
      ),
    },
    {
      key: 'external_receive_key',
      title: t('system.channel.imNotificationPage.mappingColumns.externalReceiveKey'),
      dataIndex: 'external_receive_key',
    },
    {
      key: 'synced_at',
      title: t('system.channel.imNotificationPage.mappingColumns.syncedAt'),
      dataIndex: 'synced_at',
      render: (_, record: IMNotificationUserMapping) => <p>{renderTime(record.synced_at)}</p>,
    },
  ];

  const recordColumns: ColumnItem[] = [
    {
      key: 'started_at',
      title: t('system.channel.imNotificationPage.recordColumns.startedAt'),
      dataIndex: 'started_at',
      render: (_, record: IMNotificationSyncRun) => <p>{renderTime(record.started_at)}</p>,
    },
    {
      key: 'finished_at',
      title: t('system.channel.imNotificationPage.recordColumns.finishedAt'),
      dataIndex: 'finished_at',
      render: (_, record: IMNotificationSyncRun) => <p>{renderTime(record.finished_at)}</p>,
    },
    {
      key: 'trigger_mode',
      title: t('system.channel.imNotificationPage.recordColumns.triggerMode'),
      dataIndex: 'trigger_mode',
      render: (triggerMode: string) => <span>{getSyncTriggerModeText(triggerMode, t)}</span>,
      width: 100,
    },
    {
      key: 'status',
      title: t('system.channel.imNotificationPage.recordColumns.status'),
      dataIndex: 'status',
      render: (status: string) => (
        <Tag color={getSyncRunStatusColor(status)}>
          {getSyncRunStatusText(status, t)}
        </Tag>
      ),
      width: 100,
    },
    {
      key: 'total_external_user_count',
      title: t('system.channel.imNotificationPage.recordColumns.totalExternalUsers'),
      dataIndex: 'total_external_user_count',
      width: 90,
    },
    {
      key: 'matched_count',
      title: t('system.channel.imNotificationPage.recordColumns.matchedCount'),
      dataIndex: 'matched_count',
      width: 90,
    },
    {
      key: 'unmatched_count',
      title: t('system.channel.imNotificationPage.recordColumns.unmatchedCount'),
      dataIndex: 'unmatched_count',
      width: 100,
    },
    {
      key: 'conflict_count',
      title: t('system.channel.imNotificationPage.recordColumns.conflictCount'),
      dataIndex: 'conflict_count',
      width: 90,
    },
    {
      key: 'summary',
      title: t('system.channel.imNotificationPage.recordColumns.summary'),
      dataIndex: 'summary',
      ellipsis: true,
    },
  ];

  const columns: ColumnItem[] = [
    {
      key: 'name',
      title: t('system.channel.imNotificationPage.name'),
      dataIndex: 'name',
    },
    {
      key: 'integration_instance_name',
      title: t('system.channel.imNotificationPage.integrationInstance'),
      dataIndex: 'integration_instance_name',
    },
    {
      key: 'display_status',
      title: t('system.channel.imNotificationPage.displayStatusColumn'),
      dataIndex: 'display_status',
      render: (status: string) => (
        <Tag color={getDisplayStatusColor(status)}>
          {getDisplayStatusText(status, t)}
        </Tag>
      ),
      width: 110,
    },
    {
      key: 'sync_period',
      title: t('system.channel.imNotificationPage.syncPeriod'),
      dataIndex: 'schedule_config',
      render: (_, record: IMNotificationChannel) => renderSyncPeriod(record, t),
      width: 220,
    },
    {
      key: 'latest_sync',
      title: t('system.channel.imNotificationPage.latestSync'),
      dataIndex: 'latest_sync_status',
      render: (_, record: IMNotificationChannel) => {
        if (!record.latest_sync_status) {
          return <span>{t('system.channel.imNotificationPage.latestSyncEmpty')}</span>;
        }

        const latestSyncTime = record.latest_sync_finished_at || record.latest_sync_started_at;
        const latestSyncStatus = getSyncRunStatusText(record.latest_sync_status, t);
        const latestSyncSummary = buildLatestSyncSummary(record, t);

        return (
          <div className="leading-6">
            <div className="text-base font-semibold text-[var(--color-text-1)]">
              {latestSyncTime
                ? renderTime(latestSyncTime)
                : t('system.channel.imNotificationPage.latestSyncEmpty')}
            </div>
            <div className="text-xs text-[var(--color-text-3)]">
              {t(
                'system.channel.imNotificationPage.latestSyncPrefix',
                '{status} · {summary}',
                { status: latestSyncStatus, summary: latestSyncSummary },
              )}
            </div>
          </div>
        );
      },
      width: 220,
    },
    {
      key: 'enabled',
      title: t('system.channel.imNotificationPage.enabledColumn'),
      dataIndex: 'enabled',
      width: 80,
      render: (enabled: boolean, record: IMNotificationChannel) => (
        <Switch
          size="small"
          checked={enabled}
          onChange={(checked) => handleToggleEnabled(record, checked)}
        />
      ),
    },
    {
      title: t('common.actions'),
      key: 'actions',
      dataIndex: 'actions',
      fixed: 'right',
      width: 300,
      render: (_, record: IMNotificationChannel) => (
        <Space wrap>
          <PermissionWrapper requiredPermissions={['Edit']}>
            <Button
              type="link"
              size="small"
              onClick={() => openModal(record)}
            >
              {t('common.edit')}
            </Button>
          </PermissionWrapper>
          <PermissionWrapper requiredPermissions={['Edit']}>
            <Button
              type="link"
              size="small"
              onClick={() => handleSyncMappings(record)}
              disabled={isChannelSyncRunning(record.latest_sync_status)}
            >
              {t('system.channel.imNotificationPage.syncMappings')}
            </Button>
          </PermissionWrapper>
          <Button
            type="link"
            size="small"
            onClick={() => handleViewMappings(record)}
          >
            {t('system.channel.imNotificationPage.viewMappings')}
          </Button>
          <Button
            type="link"
            size="small"
            onClick={() => handleViewRecords(record)}
          >
            {t('system.channel.imNotificationPage.viewRecords')}
          </Button>
          <PermissionWrapper requiredPermissions={['Edit']}>
            <Button
              type="link"
              size="small"
              onClick={() => handleTestSend(record)}
              disabled={!isChannelSendReady(record.display_status)}
            >
              {t('system.channel.imNotificationPage.testSend')}
            </Button>
          </PermissionWrapper>
          <PermissionWrapper requiredPermissions={['Delete']}>
            <Popconfirm
              title={t('system.channel.imNotificationPage.deleteConfirm')}
              onConfirm={() => handleDelete(record)}
            >
              <Button type="link" size="small" danger>
                {t('common.delete')}
              </Button>
            </Popconfirm>
          </PermissionWrapper>
        </Space>
      ),
    },
  ];

  const manifestHintVisible = modalOpen && !!watchedIntegrationInstance && !resolvedTemplate;
  const showMatchFieldHint = modalOpen && !!watchedIntegrationInstance && externalMatchOptions.length === 0;
  const showReceiveFieldHint = modalOpen && !!watchedIntegrationInstance && externalReceiveOptions.length === 0;

  return (
    <PageLayout
      topSection={(
        <TopSection
          title={t('system.channel.imNotification')}
          content={t('system.channel.imNotificationPage.pageDesc')}
          iconType="liaotian"
        />
      )}
      rightSection={(
        <div className="w-full">
          <div className="mb-4 flex items-center justify-between gap-2">
            <div className="flex items-center">
              <Button
                color="default"
                variant="link"
                icon={<ArrowLeftOutlined />}
                onClick={handleBack}
              />
            </div>
            <div>
              <Input.Search
                placeholder={t('system.channel.imNotificationPage.search')}
                allowClear
                style={{ width: 280 }}
                onSearch={setSearchText}
                onChange={(event) => !event.target.value && setSearchText('')}
              />
              <PermissionWrapper requiredPermissions={['Add']}>
                <Button
                  type="primary"
                  icon={<PlusOutlined />}
                  onClick={() => openModal(null)}
                  className="ml-2"
                >
                  {t('common.add')}
                </Button>
              </PermissionWrapper>
            </div>
          </div>

          <div className="flex h-full">
            <div className="min-h-0 flex-1 bg-[var(--color-bg)] p-1">
              <CustomTable
                rowKey="id"
                scroll={{ y: 'calc(100vh - 385px)' }}
                loading={loading}
                dataSource={filteredChannels}
                columns={columns}
                pagination={{
                  ...pagination,
                  onChange: (current: number, pageSize: number) => {
                    const nextPage = pageSize !== pagination.pageSize ? 1 : current;
                    fetchChannels(nextPage, pageSize);
                  },
                }}
              />
            </div>
          </div>

          <OperateModal
            title={editing ? t('common.edit') : t('common.add')}
            open={modalOpen}
            onOk={handleModalOk}
            onCancel={() => !modalLoading && setModalOpen(false)}
            confirmLoading={modalLoading}
            width={640}
          >
            <Form form={form} layout="vertical">
              <div className="mb-6">
                <div className="mb-2 text-[16px] font-semibold text-[var(--color-text-1)]">
                  {t('system.channel.imNotificationPage.basicInfoTitle')}
                </div>
                <div className="mb-5 text-[13px] text-[var(--color-text-3)]">
                  {t('system.channel.imNotificationPage.basicInfoDesc')}
                </div>
                <Form.Item
                  name="name"
                  label={t('system.channel.imNotificationPage.name')}
                  rules={[{ required: true, whitespace: true }]}
                >
                  <Input placeholder={t('system.channel.imNotificationPage.namePlaceholder')} />
                </Form.Item>
                <Form.Item
                  name="integration_instance"
                  label={t('system.channel.imNotificationPage.integrationInstance')}
                  rules={[{ required: true }]}
                >
                  <Select
                    placeholder={t('system.channel.imNotificationPage.integrationInstancePlaceholder')}
                    options={availableInstances.map((instance) => ({ value: instance.id, label: instance.name }))}
                  />
                </Form.Item>
                <Form.Item
                  name="description"
                  label={t('system.channel.imNotificationPage.description')}
                >
                  <Input.TextArea
                    rows={3}
                    placeholder={t('system.channel.imNotificationPage.descriptionPlaceholder')}
                  />
                </Form.Item>
              </div>

              <div className="border-t border-[var(--color-border-1)] pt-6">
                <div className="mb-2 text-[16px] font-semibold text-[var(--color-text-1)]">
                  {t('system.channel.imNotificationPage.fieldMappingTitle')}
                </div>
                <div className="mb-5 text-[13px] text-[var(--color-text-3)]">
                  {t('system.channel.imNotificationPage.fieldMappingDesc')}
                </div>
                {manifestHintVisible ? (
                  <Alert
                    className="mb-4"
                    type="warning"
                    showIcon
                    message={t('system.channel.imNotificationPage.manifestNotFound')}
                  />
                ) : null}
                <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg)] px-4 py-4">
                  <div className="grid grid-cols-[minmax(0,1fr)_24px_minmax(0,1fr)] gap-x-4 gap-y-3 text-[13px] text-[var(--color-text-3)]">
                    <div>{t('system.channel.imNotificationPage.platformMatchField')}</div>
                    <div />
                    <div>{t('system.channel.imNotificationPage.externalMatchField')}</div>
                  </div>
                  <div className="mt-3 grid grid-cols-[minmax(0,1fr)_24px_minmax(0,1fr)] gap-x-4 gap-y-3">
                    <Form.Item
                      name="platform_match_field"
                      rules={[{ required: true }]}
                      className="mb-0"
                    >
                      <Select options={platformMatchOptions} />
                    </Form.Item>
                    <div className="flex h-10 items-center justify-center text-lg text-[var(--color-primary)]">
                      =
                    </div>
                    <Form.Item
                      name="external_match_field"
                      rules={[{ required: true }]}
                      className="mb-0"
                    >
                      <Select
                        options={externalMatchOptions}
                        disabled={externalMatchOptions.length === 0}
                        placeholder={t('system.channel.imNotificationPage.externalMatchFieldPlaceholder')}
                      />
                    </Form.Item>
                  </div>
                  {showMatchFieldHint ? (
                    <div className="mt-3 text-[12px] text-[var(--color-text-3)]">
                      {t('system.channel.imNotificationPage.matchFieldUnavailableHint')}
                    </div>
                  ) : null}
                  <div className="mt-5">
                    <Form.Item
                      name="external_receive_field"
                      label={t('system.channel.imNotificationPage.receiveField')}
                      rules={[{ required: true }]}
                      className="mb-0"
                    >
                      <Select
                        options={externalReceiveOptions}
                        disabled={externalReceiveOptions.length === 0}
                        placeholder={t('system.channel.imNotificationPage.externalReceiveFieldPlaceholder')}
                      />
                    </Form.Item>
                    {showReceiveFieldHint ? (
                      <div className="mt-3 text-[12px] text-[var(--color-text-3)]">
                        {t('system.channel.imNotificationPage.receiveFieldUnavailableHint')}
                      </div>
                    ) : null}
                  </div>
                </div>
              </div>

              <div className="border-t border-[var(--color-border-1)] pt-6">
                <div className="mb-2 text-[16px] font-semibold text-[var(--color-text-1)]">
                  {t('system.channel.imNotificationPage.syncOptionsTitle')}
                </div>
                <div className="mb-5 text-[13px] text-[var(--color-text-3)]">
                  {t('system.channel.imNotificationPage.syncOptionsDesc')}
                </div>
                <Form.Item
                  name="schedule_enabled"
                  label={t('system.channel.imNotificationPage.syncMode')}
                  className="mb-0"
                >
                  <Select
                    options={[
                      {
                        label: t('system.channel.imNotificationPage.syncModeManual'),
                        value: false,
                      },
                      {
                        label: t('system.channel.imNotificationPage.syncModeAutomatic'),
                        value: true,
                      },
                    ]}
                  />
                </Form.Item>
                <Form.Item noStyle shouldUpdate={(prev, cur) => prev.schedule_enabled !== cur.schedule_enabled}>
                  {({ getFieldValue }) =>
                    getFieldValue('schedule_enabled') ? (
                      <Form.Item
                        name="sync_time"
                        label={t('system.channel.imNotificationPage.syncTime')}
                        required
                        rules={[{ required: true }]}
                        className="mb-0 mt-5"
                        normalize={(value) => (value ? (dayjs.isDayjs(value) ? value.format('HH:mm') : value) : '')}
                        getValueProps={(value) => ({ value: value ? dayjs(value, 'HH:mm') : null })}
                      >
                        <TimePicker format="HH:mm" className="w-full md:w-[220px]" />
                      </Form.Item>
                    ) : null
                  }
                </Form.Item>
              </div>
            </Form>
          </OperateModal>

          <Drawer
            title={`${mappingsChannel?.name ?? ''} — ${t('system.channel.imNotificationPage.mappingsTitle')}`}
            open={mappingsOpen}
            onClose={() => setMappingsOpen(false)}
            width={880}
          >
            {!mappingsLoading && mappings.length === 0 ? (
              <div className="mb-4 text-[13px] text-[var(--color-text-3)]">
                {t('system.channel.imNotificationPage.noFormalMappings')}
              </div>
            ) : null}
            <CustomTable
              rowKey="id"
              scroll={{ y: 'calc(100vh - 205px)' }}
              loading={mappingsLoading}
              dataSource={mappings}
              columns={mappingColumns}
              pagination={{
                ...mapPagination,
                onChange: (current: number, pageSize: number) => {
                  if (!mappingsChannel) return;
                  const nextPage = pageSize !== mapPagination.pageSize ? 1 : current;
                  fetchMappings(mappingsChannel.id, nextPage, pageSize);
                },
              }}
            />
          </Drawer>

          <Drawer
            title={`${recordsChannel?.name ?? ''} — ${t('system.channel.imNotificationPage.recordsTitle')}`}
            open={recordsOpen}
            onClose={() => setRecordsOpen(false)}
            width={980}
          >
            {!recordsLoading && records.length === 0 ? (
              <div className="mb-4 text-[13px] text-[var(--color-text-3)]">
                {t('system.channel.imNotificationPage.noSyncRecords')}
              </div>
            ) : null}
            <CustomTable
              rowKey="id"
              scroll={{ x: '100%', y: 'calc(100vh - 205px)' }}
              loading={recordsLoading}
              dataSource={records}
              columns={recordColumns}
              pagination={{
                ...recordsPagination,
                onChange: (current: number, pageSize: number) => {
                  if (!recordsChannel) return;
                  const nextPage = pageSize !== recordsPagination.pageSize ? 1 : current;
                  fetchRecords(recordsChannel.id, nextPage, pageSize);
                },
              }}
            />
          </Drawer>

          <OperateModal
            title={t('system.channel.imNotificationPage.testSendTitle')}
            open={testOpen}
            onOk={handleTestSendOk}
            onCancel={() => !testLoading && setTestOpen(false)}
            confirmLoading={testLoading}
            width={520}
          >
            <Form form={testForm} layout="vertical">
              <Form.Item
                name="title"
                label={t('system.channel.imNotificationPage.testSendTitleField')}
                rules={[{ required: true }]}
              >
                <Input />
              </Form.Item>
              <Form.Item
                name="content"
                label={t('system.channel.imNotificationPage.testSendContent')}
                rules={[{ required: true }]}
              >
                <Input.TextArea rows={3} />
              </Form.Item>
              <Form.Item
                name="receivers"
                label={t('system.channel.imNotificationPage.testSendReceivers')}
              >
                <Input.TextArea
                  rows={3}
                  placeholder={t('system.channel.imNotificationPage.testSendReceiversPlaceholder')}
                />
              </Form.Item>
            </Form>
          </OperateModal>
        </div>
      )}
    />
  );
};

export default ImNotificationPage;
