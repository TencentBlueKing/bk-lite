'use client';

import Link from 'next/link';
import { ReloadOutlined } from '@ant-design/icons';
import { Alert, Button, Form, InputNumber, Select } from 'antd';
import Icon from '@/components/icon';
import { useTranslation } from '@/utils/i18n';
import type {
  ApmNotificationChannel,
  ApmNotificationRecipient,
  ApmPolicyNotificationTarget,
} from '@/app/apm/types';

export type NotificationDirectoryState = 'loading' | 'ready' | 'empty' | 'forbidden' | 'error';

interface NotificationTargetFieldsProps {
  targets: ApmPolicyNotificationTarget[];
  channelById: Map<number, ApmNotificationChannel>;
  channelsToAdd: ApmNotificationChannel[];
  recipients: ApmNotificationRecipient[];
  channelState: NotificationDirectoryState;
  recipientState: NotificationDirectoryState;
  refreshing: boolean;
  onRetry: () => void;
  onSearchRecipients: (search: string) => void;
}

const CHANNEL_ICONS: Record<string, string> = {
  email: 'youjian',
  enterprise_wechat: 'qiwei2',
  enterprise_wechat_bot: 'qiwei2',
  feishu_bot: 'feishu',
  dingtalk_bot: 'dingding',
  nats: 'dongzuo1',
  custom_webhook: 'webhook',
};

function channelIcon(channelType?: string) {
  return CHANNEL_ICONS[channelType || ''] || 'jiqiren3';
}

export default function NotificationTargetFields({
  targets,
  channelById,
  channelsToAdd,
  recipients,
  channelState,
  recipientState,
  refreshing,
  onRetry,
  onSearchRecipients,
}: NotificationTargetFieldsProps) {
  const { t } = useTranslation();
  const hasSystemUserTarget = targets.some(
    (target) => channelById.get(target.channel_id)?.recipient_mode === 'system_user',
  );
  const recipientOptions = (selectedValues: string[] = []) => {
    const options: Array<{ value: string; label: string; disabled?: boolean }> = recipients.map((recipient) => ({
      value: String(recipient.id),
      label: recipient.display_name
        ? `${recipient.display_name} (${recipient.username})`
        : recipient.username,
    }));
    for (const recipientId of selectedValues) {
      if (options.some((option) => option.value === recipientId)) continue;
      const unavailable = recipientState === 'error' || recipientState === 'forbidden';
      options.push({
        value: recipientId,
        label: unavailable
          ? t('apm.policies.userUnavailable', '用户 {id}（当前不可用）', { id: recipientId })
          : t('apm.policies.userIdValue', '用户 {id}', { id: recipientId }),
        disabled: unavailable,
      });
    }
    return options;
  };
  const visibleChannels = [...channelById.values()].filter((channel) => {
    const selected = targets.some((target) => target.channel_id === channel.id);
    if (selected) return true;
    if (channelState === 'error' || channelState === 'forbidden') return false;
    return channel.availability !== 'unavailable' && channelsToAdd.some((item) => item.id === channel.id);
  });

  return (
    <>
      {channelState === 'error' || channelState === 'forbidden' ? (
        <Alert
          showIcon
          type="warning"
          className="mb-4"
          message={t(
            channelState === 'forbidden'
              ? 'apm.policies.channelsForbidden'
              : 'apm.policies.channelsUnavailable',
            channelState === 'forbidden'
              ? '无权读取当前组织的系统通知渠道'
              : '暂时无法读取系统通知渠道',
          )}
          description={t('apm.policies.retryChannels', '可以稍后重试，或前往系统管理检查渠道配置。')}
          action={(
            <Button icon={<ReloadOutlined />} loading={refreshing} disabled={refreshing} onClick={onRetry}>
              {t('apm.common.retry', '重试')}
            </Button>
          )}
        />
      ) : null}
      {channelState === 'empty' ? (
        <Alert
          showIcon
          type="info"
          className="mb-4"
          message={t('apm.policies.noOrgChannels', '当前组织没有可用通知渠道')}
          action={(
            <Link href="/system-manager/channel">
              <Button type="link">{t('apm.policies.goConfigureChannels', '前往系统管理配置渠道')}</Button>
            </Link>
          )}
        />
      ) : null}
      {hasSystemUserTarget && (recipientState === 'error' || recipientState === 'forbidden') ? (
        <Alert
          showIcon
          type="warning"
          className="mb-4"
          message={t('apm.policies.userDirectoryDown', '系统用户目录暂不可用')}
          action={(
            <Button icon={<ReloadOutlined />} loading={refreshing} disabled={refreshing} onClick={onRetry}>
              {t('apm.common.retry', '重试')}
            </Button>
          )}
        />
      ) : null}
      <Form.List name="notification_targets"
        rules={[
          {
            validator: async (_, values) => {
              if (values?.length) return;
              throw new Error(t('apm.policies.notificationChannelRequired', '请选择通知通道'));
            },
          },
        ]}
      >
        {(fields, { add, remove }, { errors }) => (
          <>
            <Form.Item label={t('apm.policies.notificationChannels', '通知渠道')} required>
              {visibleChannels.length ? (
                <div className="grid grid-cols-3 gap-4" style={{ gridAutoRows: '1fr' }}>
                  {visibleChannels.map((channel) => {
                    const field = fields.find((item) => targets[item.name]?.channel_id === channel.id);
                    const selected = Boolean(field);
                    const copy = channel.delivery_mode === 'alert_event_copy' || channel.recipient_mode === 'none';
                    const unavailable = (channelState === 'ready' || channelState === 'empty')
                      && channel.availability !== 'available';
                    return (
                      <button
                        key={channel.id}
                        type="button"
                        aria-pressed={selected}
                        onClick={() => {
                          if (field) {
                            remove(field.name);
                            return;
                          }
                          add({ channel_id: channel.id, recipients: [] });
                        }}
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
                                ? t('apm.policies.alertCopyShort', '告警中心副本')
                                : t('apm.alerts.plainNotice', '普通通知')}
                            </span>
                            <span className="mt-1 line-clamp-2 flex-1 text-xs text-[var(--color-text-3)]" title={channel.description || '--'}>
                              {channel.description || '--'}
                            </span>
                            {unavailable ? (
                              <span className="mt-1 text-xs text-[var(--color-fail)]">
                                {t('apm.policies.invalidRemove', '已失效，保存前请移除')}
                              </span>
                            ) : null}
                          </div>
                        </div>
                      </button>
                    );
                  })}
                </div>
              ) : channelState === 'ready' ? (
                <span className="text-[var(--color-text-3)]">
                  {t('apm.policies.noOrgChannels', '当前组织没有可用通知渠道')}
                  <Link href="/system-manager/channel">
                    <Button type="link" className="!px-1">{t('apm.policies.goConfigureChannels', '前往系统管理配置渠道')}</Button>
                  </Link>
                </span>
              ) : null}
              <Form.ErrorList errors={errors} />
              {fields.map((field) => {
                const target = targets[field.name];
                const channel = target ? channelById.get(target.channel_id) : undefined;
                if (channel?.recipient_mode !== 'none') return null;
                return (
                  <span key={field.key} className="mt-3 block text-xs text-[var(--color-text-3)]">
                    {t('apm.policies.alertCopyNoRecipients', '该渠道接收告警事件副本，无需配置接收人。')}
                  </span>
                );
              })}
            </Form.Item>
            {fields.map((field) => {
              const target = targets[field.name];
              const channel = target ? channelById.get(target.channel_id) : undefined;
              const recipientMode = channel?.recipient_mode;
              if (recipientMode === 'none') {
                return <Form.Item key={field.key} name={[field.name, 'channel_id']} hidden><InputNumber /></Form.Item>;
              }
              return (
                  <div key={field.key}>
                    <Form.Item name={[field.name, 'channel_id']} hidden><InputNumber /></Form.Item>
                    <Form.Item
                        name={[field.name, 'recipients']}
                        label={recipientMode === 'system_user'
                          ? t('apm.policies.userId', '系统用户 ID')
                          : t('apm.policies.notificationRecipients', '通知对象')}
                        extra={recipientMode === 'system_user' && (recipientState === 'error' || recipientState === 'forbidden')
                          ? t('apm.policies.userDirectoryUnavailable', '系统用户目录暂不可用，已有配置可查看但暂不能新增接收人。')
                          : undefined}
                        rules={[{ required: true, message: t('apm.policies.recipientsAtLeastOne', '请填写至少一个接收人') }]}
                      >
                        <Select
                          mode={recipientMode === 'system_user' ? 'multiple' : 'tags'}
                          showSearch
                          allowClear
                          options={recipientMode === 'system_user' ? recipientOptions(target?.recipients) : undefined}
                          filterOption={recipientMode === 'system_user' ? false : undefined}
                          onSearch={recipientMode === 'system_user' ? onSearchRecipients : undefined}
                          loading={recipientMode === 'system_user' && recipientState === 'loading'}
                          disabled={recipientMode === 'system_user'
                            && (recipientState === 'error' || recipientState === 'forbidden')}
                          placeholder={recipientMode === 'system_user'
                            ? t('apm.policies.selectSystemUser', '请选择系统用户')
                            : t('apm.policies.recipientsPlaceholder', '输入接收人后回车')}
                        />
                      </Form.Item>
                  </div>
              );
            })}
          </>
        )}
      </Form.List>
    </>
  );
}
