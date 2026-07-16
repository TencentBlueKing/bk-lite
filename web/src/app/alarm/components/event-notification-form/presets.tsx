import type { EventNotificationFormCopy, EventNotificationFormProps } from './index';

type TranslateFn = (key: string) => string;

type EventNotificationPreset = Pick<
  EventNotificationFormProps,
  | 'copy'
  | 'getChannelTagLabel'
  | 'resolveNotifierMode'
  | 'clearNotifierOnChannelChange'
>;

const createChannelTagLabelResolver = (
  t: TranslateFn,
  keyMap: Record<string, string>,
) => {
  return (channelType: string) => {
    const key = keyMap[channelType];
    return key ? t(key) : channelType;
  };
};

export const createMonitorEventNotificationCopy = (
  t: TranslateFn,
): EventNotificationFormCopy => ({
  configLabel: (
    <span className="w-[100px]">{t('monitor.events.notificationConfig')}</span>
  ),
  configDescription: t('monitor.events.notificationDesc'),
  channelLabel: (
    <span className="w-[100px]">{t('monitor.events.notificationChannel')}</span>
  ),
  notifierLabel: (
    <span className="w-[100px]">{t('monitor.events.notifier')}</span>
  ),
  emptyStatePrefix: t('monitor.events.noticeWay'),
  emptyStateLinkLabel: t('monitor.events.systemManage'),
  emptyStateSuffix: t('monitor.events.config'),
  notifierPlaceholder: t('monitor.events.notifier'),
  requiredMessage: t('common.required'),
});

export const createLogEventNotificationCopy = (
  t: TranslateFn,
): EventNotificationFormCopy => ({
  configLabel: (
    <span className="w-[100px]">{t('log.event.notificationConfig')}</span>
  ),
  configDescription: t('log.event.notificationDesc'),
  channelLabel: (
    <span className="w-[100px]">{t('log.event.notificationChannel')}</span>
  ),
  notifierLabel: (
    <span className="w-[100px]">{t('log.event.notifier')}</span>
  ),
  emptyStatePrefix: t('log.event.noticeWay'),
  emptyStateLinkLabel: t('log.event.systemManage'),
  emptyStateSuffix: t('log.event.config'),
  notifierPlaceholder: t('log.event.notifier'),
  notifierTagsPlaceholder: t('log.event.notifierTagsPlaceholder'),
  requiredMessage: t('common.required'),
});

export const createMonitorEventNotificationPreset = (
  t: TranslateFn,
): EventNotificationPreset => ({
  copy: createMonitorEventNotificationCopy(t),
  getChannelTagLabel: createChannelTagLabelResolver(t, {
    email: 'monitor.events.channelTypeEmail',
    enterprise_wechat_bot: 'monitor.events.channelTypeWechatBot',
    feishu_bot: 'monitor.events.channelTypeFeishuBot',
    dingtalk_bot: 'monitor.events.channelTypeDingtalkBot',
    custom_webhook: 'monitor.events.channelTypeCustomWebhook',
    nats: 'monitor.events.channelTypeNats',
  }),
  resolveNotifierMode: (channelTypes) => {
    if (
      !channelTypes.length ||
      channelTypes.every((channelType) => channelType === 'nats')
    ) {
      return 'none';
    }

    return 'users';
  },
  clearNotifierOnChannelChange: 'when-hidden',
});

export const createLogEventNotificationPreset = (
  t: TranslateFn,
): EventNotificationPreset => ({
  copy: createLogEventNotificationCopy(t),
  getChannelTagLabel: createChannelTagLabelResolver(t, {
    email: 'log.event.channelTypeEmail',
    enterprise_wechat_bot: 'log.event.channelTypeWechatBot',
    feishu_bot: 'log.event.channelTypeFeishuBot',
    dingtalk_bot: 'log.event.channelTypeDingtalkBot',
    custom_webhook: 'log.event.channelTypeCustomWebhook',
    nats: 'log.event.channelTypeNats',
  }),
  resolveNotifierMode: (channelTypes) => {
    const channelType = channelTypes[0];
    if (!channelType || channelType === 'nats') return 'none';
    if (channelType === 'email') return 'users';
    return 'tags';
  },
  clearNotifierOnChannelChange: 'always',
});
