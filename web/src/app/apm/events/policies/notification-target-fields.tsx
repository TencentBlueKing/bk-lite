'use client';

import Link from 'next/link';
import { DeleteOutlined, ReloadOutlined } from '@ant-design/icons';
import { Alert, Button, Form, InputNumber, Select, Tag, Typography } from 'antd';
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
  defaultSystemUserRecipients: string[];
  onRetry: () => void;
  onSearchRecipients: (search: string) => void;
}

const CHANNEL_ICONS: Record<string, string> = {
  email: 'youjian',
  enterprise_wechat: 'weixin',
  enterprise_wechat_bot: 'weixin',
  feishu_bot: 'feishu',
  dingtalk_bot: 'dingding',
  nats: 'gaojing',
  custom_webhook: 'lianjie',
};

function channelIcon(channelType?: string) {
  return CHANNEL_ICONS[channelType || ''] || 'tongzhi';
}

export default function NotificationTargetFields({
  targets,
  channelById,
  channelsToAdd,
  recipients,
  channelState,
  recipientState,
  refreshing,
  defaultSystemUserRecipients,
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

  return (
    <div className="space-y-4">
      {channelState === 'error' || channelState === 'forbidden' ? (
        <Alert
          showIcon
          type="warning"
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
            <Button
              icon={<ReloadOutlined aria-hidden="true" />}
              loading={refreshing}
              disabled={refreshing}
              onClick={onRetry}
            >
              {t('apm.common.retry', '重试')}
            </Button>
          )}
        />
      ) : null}
      {channelState === 'empty' ? (
        <Alert
          showIcon
          type="info"
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
          message={t('apm.policies.userDirectoryDown', '系统用户目录暂不可用')}
          action={(
            <Button
              icon={<ReloadOutlined aria-hidden="true" />}
              loading={refreshing}
              disabled={refreshing}
              onClick={onRetry}
            >
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
          <div className="space-y-4">
            {fields.map((field) => {
              const target = targets[field.name];
              const channel = target ? channelById.get(target.channel_id) : undefined;
              const recipientMode = channel?.recipient_mode;
              const unavailable = (channelState === 'ready' || channelState === 'empty')
                && channel?.availability !== 'available';
              return (
                <div
                  key={field.key}
                  className="border-b border-[var(--color-border)] pb-4 last:border-b-0 last:pb-0"
                >
                  <Form.Item name={[field.name, 'channel_id']} hidden><InputNumber /></Form.Item>
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex min-w-0 items-start gap-2">
                      <Icon
                        type={channelIcon(channel?.channel_type)}
                        className="mt-0.5 text-xl"
                        aria-hidden="true"
                      />
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <Typography.Text strong>{channel?.name || t('apm.alerts.channel', '渠道')}</Typography.Text>
                          {channel?.channel_type ? <Tag className="!m-0">{channel.channel_type}</Tag> : null}
                          {unavailable ? <Tag color="error" className="!m-0">{t('apm.policies.invalidRemove', '已失效，保存前请移除')}</Tag> : null}
                        </div>
                        {channel?.description ? (
                          <Typography.Text type="secondary" className="block break-words">
                            {channel.description}
                          </Typography.Text>
                        ) : null}
                      </div>
                    </div>
                    <Button
                      type="link"
                      size="small"
                      danger
                      icon={<DeleteOutlined aria-hidden="true" />}
                      aria-label={t('apm.policies.removeChannel', '移除 {name}', { name: channel?.name || '' })}
                      onClick={() => remove(field.name)}
                    />
                  </div>
                  {recipientMode === 'none' ? (
                    <Typography.Text type="secondary">
                      {t('apm.policies.alertCopyNoRecipients', '该渠道接收告警事件副本，无需配置接收人。')}
                    </Typography.Text>
                  ) : (
                    <Form.Item
                      name={[field.name, 'recipients']}
                      className="!mb-0 !mt-3"
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
                  )}
                </div>
              );
            })}
            <Form.ErrorList errors={errors} />
            {channelState === 'loading' || channelsToAdd.length ? (
              <Form.Item
                label={t('apm.policies.addChannel', '添加通知渠道')}
                className="!mb-0"
              >
                <Select<number>
                  value={undefined}
                  aria-label={t('apm.policies.addChannel', '添加通知渠道')}
                  loading={channelState === 'loading'}
                  disabled={channelState === 'loading'}
                  placeholder={channelState === 'loading'
                    ? t('apm.policies.loadingChannels', '正在加载通知渠道')
                    : t('apm.policies.notificationChannelPlaceholder', '选择通知渠道')}
                  options={channelsToAdd.map((channel) => ({
                    value: channel.id,
                    label: `${channel.name}（${channel.channel_type}）`,
                  }))}
                  onChange={(channelId) => {
                    const channel = channelById.get(channelId);
                    add({
                      channel_id: channelId,
                      recipients: channel?.recipient_mode === 'system_user'
                        ? defaultSystemUserRecipients
                        : [],
                    });
                  }}
                />
              </Form.Item>
            ) : null}
          </div>
        )}
      </Form.List>
    </div>
  );
}
