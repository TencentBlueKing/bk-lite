// Route: /system-manager/channel/im-notification
'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  Button,
  Form,
  message,
  Popconfirm,
  Space,
  Switch,
  Tag,
  Tooltip,
} from 'antd';
import type { ColumnItem } from '@/types';
import {
  ArrowLeftOutlined,
  PlusOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import PermissionWrapper from '@/components/permission';
import CustomTable from '@/components/custom-table';
import SystemManagerFillTable from '@/app/system-manager/components/system-manager-fill-table';
import EllipsisWithTooltip from '@/components/ellipsis-with-tooltip';
import TopSection from '@/components/top-section';
import PageLayout from '@/components/page-layout';
import SearchActionBar from '@/components/search-action-bar';
import type { NotificationTagOption } from '@/app/system-manager/components/channel/NotificationTagSelect';
import IMNotificationConfigModal, {
  type IMNotificationChannelFormValues,
} from '@/app/system-manager/components/channel/im-notification/IMNotificationConfigModal';
import IMNotificationSendModal from '@/app/system-manager/components/channel/im-notification/IMNotificationSendModal';
import { useChannelApi } from '@/app/system-manager/api/channel';
import { useImNotificationApi } from '@/app/system-manager/api/im-notification';
import type {
  AvailableInstance,
  IMNotificationChannel,
  IMNotificationChannelPayload,
  IMNotificationUserMapping,
} from '@/app/system-manager/types/im-notification';
import { coerceImNotificationTeamIds } from '@/app/system-manager/utils/imNotificationUtils';
import { useTranslation } from '@/utils/i18n';

interface PaginationState {
  current: number;
  total: number;
  pageSize: number;
}

const ImNotificationPage: React.FC = () => {
  const { t } = useTranslation();
  const router = useRouter();
  const {
    getChannels,
    createChannel,
    updateChannel,
    deleteChannel,
    getAvailableInstances,
    getAccountAssociationOptions,
    getAssociationMappings,
    sendNotification,
  } = useImNotificationApi();
  const { getNotificationTagCatalog } = useChannelApi();

  const [channels, setChannels] = useState<IMNotificationChannel[]>([]);
  const [associationOptions, setAssociationOptions] = useState<Array<{
    id: number;
    name: string;
    integration_instance_id: number;
    integration_instance_name: string;
    status: string;
  }>>([]);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [searchText, setSearchText] = useState('');

  const [form] = Form.useForm<IMNotificationChannelFormValues>();
  const [modalOpen, setModalOpen] = useState(false);
  const [modalLoading, setModalLoading] = useState(false);
  const [editing, setEditing] = useState<IMNotificationChannel | null>(null);
  const [availableInstances, setAvailableInstances] = useState<AvailableInstance[]>([]);
  const [tagOptions, setTagOptions] = useState<NotificationTagOption[]>([]);

  const [sendForm] = Form.useForm();
  const [sendOpen, setSendOpen] = useState(false);
  const [sendLoading, setSendLoading] = useState(false);
  const [sendChannelId, setSendChannelId] = useState<number | undefined>();
  const [sendMappings, setSendMappings] = useState<IMNotificationUserMapping[]>([]);
  const [sendMappingsLoading, setSendMappingsLoading] = useState(false);

  const [pagination, setPagination] = useState<PaginationState>({
    current: 1,
    total: 0,
    pageSize: 10,
  });

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

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await fetchChannels(pagination.current, pagination.pageSize);
    } finally {
      setRefreshing(false);
    }
  };

  const fetchMeta = async () => {
    try {
      setAvailableInstances(await getAvailableInstances() ?? []);
    } catch {
      setAvailableInstances([]);
    }
  };

  const refreshAssociationOptions = async () => {
    const options = await getAccountAssociationOptions();
    const nextOptions = Array.isArray(options) ? options : [];
    setAssociationOptions(nextOptions);
    return nextOptions;
  };

  useEffect(() => {
    fetchChannels(1, pagination.pageSize);
    fetchMeta();
  }, []);

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
        account_association: record.account_association,
        team: coerceImNotificationTeamIds(record.team),
        tag: record.tag || [],
      });
    } else {
      form.resetFields();
      form.setFieldsValue({
        enabled: true,
        team: [],
        tag: [],
      });
    }
    try {
      const rows = await getNotificationTagCatalog();
      setTagOptions(Array.isArray(rows) ? rows : []);
    } catch {
      setTagOptions([]);
    }
    await fetchMeta();
    try {
      const options = await getAccountAssociationOptions();
      setAssociationOptions(Array.isArray(options) ? options : []);
    } catch {
      setAssociationOptions([]);
    }
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
        account_association: values.account_association ?? null,
        team: coerceImNotificationTeamIds(values.team),
        tag: values.tag || [],
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
    } catch {
      message.error(t('common.error'))
    } finally {
      setModalLoading(false);
    }
  };

  const handleSendOpen = () => {
    sendForm.resetFields();
    setSendChannelId(undefined);
    setSendMappings([]);
    setSendOpen(true);
  };

  const handleSendChannelChange = async (channelId: number) => {
    setSendChannelId(channelId);
    sendForm.setFieldsValue({ user_ids: [] });
    setSendMappings([]);
    if (!channelId) return;

    const channel = channels.find((item) => item.id === channelId);
    if (!channel?.account_association) return;

    setSendMappingsLoading(true);
    try {
      const { items } = await getAssociationMappings(channel.account_association, { page: 1, page_size: 1000 });
      setSendMappings(items ?? []);
    } catch {
      message.error(t('common.fetchFailed'));
      setSendMappings([]);
    } finally {
      setSendMappingsLoading(false);
    }
  };

  const handleSendOk = async () => {
    try {
      const values = await sendForm.validateFields();
      setSendLoading(true);
      await sendNotification({
        channel_id: values.channel_id,
        user_ids: values.user_ids ?? [],
        title: values.title,
        content: values.content,
      });
      message.success(t('system.channel.imNotificationPage.sendSuccess'));
      setSendOpen(false);
    } catch (error) {
      if (error && typeof error === 'object' && 'errorFields' in error) return;
      message.error(error instanceof Error ? error.message : t('system.channel.imNotificationPage.sendFailed'));
    } finally {
      setSendLoading(false);
    }
  };

  const handleBack = () => {
    router.push('/system-manager/channel');
  };

  const sendChannelOptions = useMemo(
    () =>
      channels
        .filter((channel) => channel.enabled && channel.account_association && channel.dependency_status?.available !== false)
        .map((channel) => ({
          value: channel.id,
          label: `${channel.name}`,
        })),
    [channels],
  );

  const sendReceiverOptions = useMemo(
    () =>
      sendMappings.map((mapping) => {
        return ({
          value: mapping.user,
          label: mapping.display_name || mapping.username,
        })
      }),
    [sendMappings],
  );

  const columns: ColumnItem[] = [
    {
      key: 'name',
      title: t('system.channel.imNotificationPage.name'),
      dataIndex: 'name',
      render: (_, record) => (
        <div className="min-w-0">
          <EllipsisWithTooltip text={record.name} className="truncate text-sm text-[var(--color-text-1)]" />
          <EllipsisWithTooltip
            text={record.description || '--'}
            className="truncate text-xs text-[var(--color-text-3)]"
          />
        </div>
      ),
    },
    {
      key: 'tag',
      title: t('system.channel.table.tag'),
      dataIndex: 'tag',
      render: (tags: string[] = []) => (
        <div className="flex flex-wrap gap-1">
          {tags.map((item) => (
            <Tag key={item}>{item}</Tag>
          ))}
        </div>
      ),
    },
    {
      key: 'integration_instance_name',
      title: t('system.channel.imNotificationPage.integrationInstance'),
      dataIndex: 'integration_instance_name',
      render: (_, record) => {
        const dependencyStatus = record.dependency_status;
        return (
          <div className="flex min-w-0 items-center gap-2">
            <EllipsisWithTooltip
              className="min-w-0 flex-1 truncate"
              text={`${record.integration_instance_name} / ${record.provider_name || record.provider_key}`}
            />
            {dependencyStatus?.available === false ? (
              <Tooltip title={t(`system.channel.imNotificationPage.dependencyReason.${dependencyStatus.reason}`)}>
                <Tag className="shrink-0" color="warning">{t('system.channel.imNotificationPage.dependencyPaused')}</Tag>
              </Tooltip>
            ) : null}
          </div>
        );
      },
    },
    {
      key: 'account_association_name',
      title: t('system.channel.imNotificationPage.accountAssociation', '账号关联'),
      dataIndex: 'account_association_name',
      render: (value: string) => value || '--',
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
      width: 320,
      render: (_, record: IMNotificationChannel) => {
        return (
          <Space wrap className="max-w-full">
            <PermissionWrapper requiredPermissions={['Edit']}>
              <Button
                type="link"
                size="small"
                onClick={() => openModal(record)}
              >
                {t('common.edit')}
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
        );
      },
    },
  ];

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
        <div className="flex h-full min-h-0 min-w-0 w-full max-w-full flex-col overflow-hidden">
          <div className="mb-4 flex min-w-0 items-center justify-between gap-2">
            <div className="flex shrink-0 items-center">
              <Button
                color="default"
                variant="link"
                icon={<ArrowLeftOutlined />}
                onClick={handleBack}
              />
            </div>
            <SearchActionBar
              spacing="flush"
              className="min-w-0"
              searchClassName="!w-[280px]"
              searchProps={{
                placeholder: t('system.channel.imNotificationPage.search'),
                allowClear: true,
                onSearch: setSearchText,
                onChange: (event) => !event.target.value && setSearchText(''),
              }}
              actions={(
                <>
                  <PermissionWrapper requiredPermissions={['Edit']}>
                    <Button onClick={handleSendOpen}>
                      {t('system.channel.imNotificationPage.sendTitle')}
                    </Button>
                  </PermissionWrapper>
                  <Button
                    icon={<ReloadOutlined />}
                    onClick={handleRefresh}
                    loading={refreshing}
                  >
                    {t('common.refresh')}
                  </Button>
                  <PermissionWrapper requiredPermissions={['Add']}>
                    <Button
                      type="primary"
                      icon={<PlusOutlined />}
                      onClick={() => openModal(null)}
                    >
                      {t('common.new')}
                    </Button>
                  </PermissionWrapper>
                </>
              )}
            />
          </div>

          <SystemManagerFillTable className="bg-[var(--color-bg)]">
            <CustomTable
              rowKey="id"
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
          </SystemManagerFillTable>

          <IMNotificationConfigModal
            open={modalOpen}
            editing={editing}
            loading={modalLoading}
            form={form}
            availableInstances={availableInstances}
            associationOptions={associationOptions}
            tagOptions={tagOptions}
            t={t}
            onRefreshOptions={refreshAssociationOptions}
            onOk={handleModalOk}
            onCancel={() => !modalLoading && setModalOpen(false)}
          />

          <IMNotificationSendModal
            open={sendOpen}
            loading={sendLoading}
            form={sendForm}
            channelOptions={sendChannelOptions}
            receiverOptions={sendReceiverOptions}
            receiversLoading={sendMappingsLoading}
            selectedChannelId={sendChannelId}
            t={t}
            onOk={handleSendOk}
            onCancel={() => !sendLoading && setSendOpen(false)}
            onChannelChange={handleSendChannelChange}
          />
        </div>
      )}
    />
  );
};

export default ImNotificationPage;
