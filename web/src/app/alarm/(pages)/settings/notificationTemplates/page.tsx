'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Button, Input, Modal, Space, Tag, Tooltip, message } from 'antd';
import { useScreenAwareRouter } from '@/console-layout';
import CustomTable from '@/components/custom-table';
import Introduction from '@/components/introduction';
import PermissionWrapper from '@/components/permission';
import { useSettingApi } from '@/app/alarm/api/settings';
import { NotificationTemplateItem } from '@/app/alarm/types/settings';
import { useLocalizedTime } from '@/hooks/useLocalizedTime';
import { useTranslation } from '@/utils/i18n';
import { NOTIFICATION_TEMPLATE_CHANNELS } from '@/app/alarm/utils/notificationTemplateChannels';
import {
  getNotificationTemplateDeleteErrorKey,
  isNotificationTemplateDeleteDisabled,
} from './notificationTemplateActions';

export default function NotificationTemplatesPage() {
  const { t } = useTranslation();
  const router = useScreenAwareRouter();
  const [messageApi, messageContextHolder] = message.useMessage();
  const [modalApi, modalContextHolder] = Modal.useModal();
  const { convertToLocalizedTime } = useLocalizedTime();
  const { getNotificationTemplateList, deleteNotificationTemplate } = useSettingApi();
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [items, setItems] = useState<NotificationTemplateItem[]>([]);
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20, total: 0 });
  const channelLabels = useMemo<Record<string, string>>(
    () => Object.fromEntries(NOTIFICATION_TEMPLATE_CHANNELS.map((channel) => [channel.key, t(channel.labelKey)])),
    [t],
  );

  const load = useCallback(async (page = pagination.current, pageSize = pagination.pageSize, name = search) => {
    setLoading(true);
    try {
      const data = await getNotificationTemplateList({ page, page_size: pageSize, name: name || undefined });
      setItems(data.items || []);
      setPagination((current) => ({ ...current, current: page, pageSize, total: data.count || 0 }));
    } catch {
      messageApi.error(t('common.loadFailed'));
    } finally {
      setLoading(false);
    }
  }, [getNotificationTemplateList, pagination.current, pagination.pageSize, search, t]);

  useEffect(() => {
    void load(1, 20, '');
    // API hooks are recreated with the request client; the initial load should run once.
  }, []);

  const remove = (row: NotificationTemplateItem) => {
    modalApi.confirm({
      title: t('settings.notificationTemplate.deleteConfirm'),
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await deleteNotificationTemplate(row.id);
          messageApi.success(t('successfullyDeleted'));
          await load();
        } catch (error: unknown) {
          messageApi.error(t(getNotificationTemplateDeleteErrorKey(error)));
        }
      },
    });
  };

  const columns = useMemo(() => [
    {
      title: t('settings.notificationTemplate.name'),
      dataIndex: 'name',
      key: 'name',
      width: 220,
      render: (name: string, row: NotificationTemplateItem) => (
        <Space size={6}>
          <span>{name}</span>
          {row.scope === 'alert_operation' && <Tag color="blue">{t('settings.notificationTemplate.builtin')}</Tag>}
        </Space>
      ),
    },
    {
      title: t('settings.notificationTemplate.channels'),
      key: 'channels',
      width: 260,
      render: (_: unknown, row: NotificationTemplateItem) => (
        <Space size={[4, 4]} wrap>
          {row.contents.map((content) => (
            <Tag key={content.channel_type} color={content.channel_type === 'email' ? 'blue' : 'green'}>
              {channelLabels[content.channel_type] || content.channel_type}
            </Tag>
          ))}
        </Space>
      ),
    },
    {
      title: t('settings.notificationTemplate.scope'),
      dataIndex: 'scope',
      key: 'scope',
      width: 140,
      render: (scope: string) => scope === 'alert_operation'
        ? t('settings.notificationTemplate.alertOperation')
        : scope === 'single_alert'
          ? t('settings.notificationTemplate.singleAlert')
          : t('settings.notificationTemplate.alertSummary'),
    },
    {
      title: t('settings.notificationTemplate.usage'),
      dataIndex: 'assignment_count',
      key: 'assignment_count',
      width: 160,
      render: (count: number, row: NotificationTemplateItem) => row.scope === 'alert_operation'
        ? <Tag color="processing">{t('settings.notificationTemplate.systemEffective')}</Tag>
        : count > 0
          ? <Tag color="processing">{t('settings.notificationTemplate.boundAssignments', undefined, { count })}</Tag>
          : <Tag>{t('settings.notificationTemplate.unused')}</Tag>,
    },
    {
      title: t('settings.notificationTemplate.updatedAt'),
      dataIndex: 'updated_at',
      key: 'updated_at',
      width: 180,
      render: (value: string) => convertToLocalizedTime(value, 'YYYY-MM-DD HH:mm:ss'),
    },
    {
      title: t('settings.assignActions'),
      key: 'actions',
      width: 240,
      render: (_: unknown, row: NotificationTemplateItem) => (
        <Space>
          {row.scope !== 'alert_operation' && <PermissionWrapper requiredPermissions={['View']}>
            <Button
              type="link"
              size="small"
              onClick={() => router.push('/alarm/settings/alertAssign')}
            >
              {t('settings.notificationTemplate.goToAssignment')}
            </Button>
          </PermissionWrapper>}
          <PermissionWrapper requiredPermissions={['Edit']}>
            <Button
              type="link"
              size="small"
              disabled={row.is_global || (row.is_builtin && row.scope !== 'alert_operation')}
              onClick={() => router.push(`/alarm/settings/notificationTemplates/${row.id}`)}
            >
              {t('common.edit')}
            </Button>
          </PermissionWrapper>
          <PermissionWrapper requiredPermissions={['Delete']}>
            <Tooltip title={row.is_builtin
              ? t('settings.notificationTemplate.builtinCannotDelete')
              : row.assignment_count > 0 ? t('settings.notificationTemplate.inUse') : undefined}
            >
              <span>
                <Button
                  type="link"
                  size="small"
                  danger
                  disabled={isNotificationTemplateDeleteDisabled(row)}
                  onClick={() => remove(row)}
                >
                  {t('common.delete')}
                </Button>
              </span>
            </Tooltip>
          </PermissionWrapper>
        </Space>
      ),
    },
  ], [channelLabels, convertToLocalizedTime, router, t]);

  return (
    <>
      {messageContextHolder}
      {modalContextHolder}
      <Introduction
        title={t('settings.notificationTemplate.title')}
        message={t('settings.notificationTemplate.message')}
      />
      <div className="rounded-lg border border-[var(--color-border-1)] bg-[var(--color-bg-1)] p-4">
        <div className="mb-5 flex flex-wrap items-center justify-end gap-2">
          <Input.Search
            allowClear
            value={search}
            className="w-[280px]"
            placeholder={t('common.search')}
            onChange={(event) => setSearch(event.target.value)}
            onSearch={(value) => void load(1, pagination.pageSize, value)}
          />
          <PermissionWrapper requiredPermissions={['Add']}>
            <Button type="primary" onClick={() => router.push('/alarm/settings/notificationTemplates/new')}>
              {t('common.addNew')}
            </Button>
          </PermissionWrapper>
        </div>
        <CustomTable
          rowKey="id"
          size="middle"
          loading={loading}
          columns={columns}
          dataSource={items}
          pagination={pagination}
          onChange={(next) => void load(next.current || 1, next.pageSize || 20)}
          scroll={{ y: 'calc(100vh - 440px)' }}
        />
      </div>
    </>
  );
}
