'use client';

import { DeleteOutlined } from '@ant-design/icons';
import { Button, Select, Tag } from 'antd';

import type { RumNotificationChannel, RumNotificationRecipient, RumNotificationTarget } from '@/app/rum/api';
import { useTranslation } from '@/utils/i18n';

export default function NotificationTargetFields({
  targets,
  channels,
  recipients,
  onChange,
  onSearchRecipients,
}: {
  targets: RumNotificationTarget[];
  channels: RumNotificationChannel[];
  recipients: RumNotificationRecipient[];
  onChange: (next: RumNotificationTarget[]) => void;
  onSearchRecipients: (search: string) => void;
}) {
  const { t } = useTranslation();
  const selected = new Set(targets.map((item) => item.channelId));
  const available = channels.filter((channel) => !selected.has(channel.id) && channel.availability !== 'unavailable');

  function addChannel(channelId: number) {
    const channel = channels.find((item) => item.id === channelId);
    if (!channel) return;
    onChange([
      ...targets,
      {
        channelId: channel.id,
        channelName: channel.name,
        channelType: channel.channel_type,
        deliveryMode: channel.delivery_mode,
        recipientMode: channel.recipient_mode,
        recipients: channel.recipient_mode === 'none' || channel.delivery_mode === 'alert_event_copy' ? [] : [],
      },
    ]);
  }

  return (
    <div className="space-y-3">
      <Select
        showSearch
        value={undefined}
        placeholder={t('rum.monitors.addChannel', '添加通知渠道')}
        className="w-full"
        options={available.map((channel) => ({
          value: channel.id,
          label: `${channel.name} · ${channel.delivery_mode === 'alert_event_copy' ? t('rum.monitors.alertCopy', '告警中心副本') : t('rum.monitors.plainNotice', '普通通知')}`,
        }))}
        onChange={(value) => addChannel(Number(value))}
        optionFilterProp="label"
      />
      {targets.map((target) => {
        const channel = channels.find((item) => item.id === target.channelId);
        const mode = channel?.delivery_mode || target.deliveryMode;
        const recipientMode = channel?.recipient_mode || target.recipientMode;
        const copy = mode === 'alert_event_copy' || recipientMode === 'none';
        return (
          <div key={target.channelId} className="rounded-lg border border-[var(--color-border-2)] p-3">
            <div className="mb-2 flex items-center justify-between gap-2">
              <div className="flex min-w-0 flex-wrap items-center gap-2">
                <span className="truncate">{channel?.name || target.channelName || target.channelId}</span>
                <Tag bordered={false} color={copy ? 'purple' : 'blue'}>
                  {copy ? t('rum.monitors.alertCopy', '告警中心副本') : t('rum.monitors.plainNotice', '普通通知')}
                </Tag>
              </div>
              <Button
                type="text"
                danger
                icon={<DeleteOutlined />}
                aria-label={t('rum.monitors.removeChannel', '移除渠道')}
                onClick={() => onChange(targets.filter((item) => item.channelId !== target.channelId))}
              />
            </div>
            {copy ? (
              <p className="text-[var(--color-text-3)]">{t('rum.monitors.alertCopyNoRecipients', '该渠道接收告警事件副本，无需配置接收人。')}</p>
            ) : (
              <Select
                mode={recipientMode === 'system_user' ? 'multiple' : 'tags'}
                className="w-full"
                value={target.recipients}
                showSearch
                allowClear
                placeholder={recipientMode === 'system_user' ? t('rum.monitors.selectSystemUser', '请选择系统用户') : t('rum.monitors.notificationRecipients', '通知对象')}
                options={recipientMode === 'system_user' ? recipients.map((item) => ({
                  value: String(item.id),
                  label: item.display_name ? `${item.display_name} (${item.username})` : item.username,
                })) : undefined}
                filterOption={recipientMode === 'system_user' ? false : undefined}
                onSearch={recipientMode === 'system_user' ? onSearchRecipients : undefined}
                onChange={(values) => onChange(targets.map((item) => (
                  item.channelId === target.channelId ? { ...item, recipients: values } : item
                )))}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
