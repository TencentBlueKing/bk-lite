'use client';

import { useEffect, useRef } from 'react';
import Link from 'next/link';
import { Button, Form, Select } from 'antd';

import type { RumNotificationChannel, RumNotificationRecipient, RumNotificationTarget } from '@/app/rum/api';
import Icon from '@/components/icon';
import { useTranslation } from '@/utils/i18n';

const CHANNEL_ICONS: Record<string, string> = {
  email: 'youjian',
  enterprise_wechat_bot: 'qiwei2',
  feishu_bot: 'feishu',
  dingtalk_bot: 'dingding',
  custom_webhook: 'webhook',
  nats: 'dongzuo1',
};

function channelIcon(channelType?: string) {
  return CHANNEL_ICONS[channelType || ''] || 'jiqiren3';
}

function needsRecipients(channel: { recipientMode?: string; deliveryMode?: string }) {
  return channel.recipientMode !== 'none' && channel.deliveryMode !== 'alert_event_copy';
}

function toTarget(channel: RumNotificationChannel, recipients: string[]): RumNotificationTarget {
  return {
    channelId: channel.id,
    channelName: channel.name,
    channelType: channel.channel_type,
    deliveryMode: channel.delivery_mode,
    recipientMode: channel.recipient_mode,
    recipients: needsRecipients({
      recipientMode: channel.recipient_mode,
      deliveryMode: channel.delivery_mode,
    }) ? recipients : [],
  };
}

export default function NotificationTargetFields({
  targets,
  channels,
  recipients,
  handlers,
  organizationsReady,
  onChange,
  onSearchRecipients,
}: {
  targets: RumNotificationTarget[];
  channels: RumNotificationChannel[];
  recipients: RumNotificationRecipient[];
  handlers: string[];
  organizationsReady: boolean;
  onChange: (next: RumNotificationTarget[]) => void;
  onSearchRecipients: (search: string) => void;
}) {
  const { t } = useTranslation();
  const seededRecipients = useRef(false);
  const visibleChannels = channels.filter((channel) => (
    channel.availability !== 'unavailable' || targets.some((target) => target.channelId === channel.id)
  ));
  const selectedIds = new Set(targets.map((target) => target.channelId));
  const sharedRecipients = [...new Set(
    targets.filter((target) => needsRecipients(target)).flatMap((target) => target.recipients),
  )];
  const selectedNeedRecipients = targets.some((target) => needsRecipients(target));
  const freeText = targets.some((target) => needsRecipients(target) && target.recipientMode !== 'system_user');

  useEffect(() => {
    if (!selectedNeedRecipients) {
      seededRecipients.current = false;
      return;
    }
    if (seededRecipients.current || sharedRecipients.length || handlers.length === 0) return;
    seededRecipients.current = true;
    onChange(targets.map((target) => (
      needsRecipients(target) ? { ...target, recipients: [...handlers] } : target
    )));
  }, [handlers, onChange, selectedNeedRecipients, sharedRecipients.length, targets]);

  function toggle(channel: RumNotificationChannel) {
    if (selectedIds.has(channel.id)) {
      onChange(targets.filter((target) => target.channelId !== channel.id));
      return;
    }
    onChange([...targets, toTarget(channel, sharedRecipients)]);
  }

  function changeRecipients(values: string[]) {
    onChange(targets.map((target) => (
      needsRecipients(target) ? { ...target, recipients: values } : target
    )));
  }

  return (
    <>
      <Form.Item label={t('rum.monitors.methods', '通知渠道')}>
        {!organizationsReady ? (
          <span className="text-[var(--color-text-3)]">{t('rum.monitors.selectOrganizationFirst', '请先选择所属组织')}</span>
        ) : visibleChannels.length ? (
          <div className="grid grid-cols-3 gap-4">
            {visibleChannels.map((channel) => {
              const selected = selectedIds.has(channel.id);
              const recipientMode = channel.recipient_mode;
              const copy = channel.delivery_mode === 'alert_event_copy' || recipientMode === 'none';
              return (
                <button
                  key={channel.id}
                  type="button"
                  onClick={() => toggle(channel)}
                  style={{
                    backgroundColor: selected
                      ? 'color-mix(in srgb, var(--color-primary) 4%, transparent)'
                      : undefined,
                    boxShadow: selected
                      ? '0 8px 24px color-mix(in srgb, var(--color-primary) 20%, transparent)'
                      : undefined,
                  }}
                  className={`relative cursor-pointer rounded-lg border-2 bg-[var(--color-bg-1)] p-3 text-left shadow-md transition-all duration-300 hover:shadow-lg ${
                    selected ? 'border-[var(--color-primary)]' : 'border-transparent'
                  }`}
                >
                  <div className="flex h-full gap-3">
                    <Icon type={channelIcon(channel.channel_type)} className="mt-1 shrink-0 text-2xl" />
                    <div className="flex min-w-0 flex-1 flex-col">
                      <span className="truncate text-sm font-bold" title={channel.name}>{channel.name}</span>
                      <span className="mt-1 inline-flex w-fit rounded bg-[var(--color-primary-bg)] px-1.5 py-0.5 text-xs text-[var(--color-primary)]">
                        {copy
                          ? t('rum.monitors.alertCopy', '告警中心副本')
                          : t('rum.monitors.plainNotice', '普通通知')}
                      </span>
                      <span className="mt-1 line-clamp-2 flex-1 text-xs text-[var(--color-text-3)]" title={channel.description || '--'}>
                        {channel.description || '--'}
                      </span>
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        ) : (
          <span className="text-[var(--color-text-3)]">
            {t('rum.monitors.noChannels', '暂无通知渠道，可去')}
            <Link href="/system-manager/channel">
              <Button type="link" className="!px-1">{t('rum.monitors.systemManage', '系统管理')}</Button>
            </Link>
            {t('rum.monitors.configureChannels', '配置。')}
          </span>
        )}
      </Form.Item>
      {selectedNeedRecipients ? (
        <Form.Item label={t('rum.monitors.notifier', '通知者')}>
          <Select
            mode={freeText ? 'tags' : 'multiple'}
            allowClear
            showSearch
            className="w-full"
            maxTagCount="responsive"
            value={sharedRecipients}
            placeholder={freeText
              ? t('rum.monitors.notifierTagsPlaceholder', '请输入通知者，按回车键添加')
              : t('rum.monitors.notifier', '通知者')}
            options={freeText ? undefined : recipients.map((item) => ({
              value: String(item.id),
              label: item.display_name ? `${item.display_name} (${item.username})` : item.username,
            }))}
            optionFilterProp="label"
            filterOption={freeText ? undefined : false}
            onSearch={freeText ? undefined : onSearchRecipients}
            onChange={changeRecipients}
          />
        </Form.Item>
      ) : null}
    </>
  );
}
