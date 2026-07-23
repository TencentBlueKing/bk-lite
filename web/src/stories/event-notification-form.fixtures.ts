export const eventNotificationChannels = [
  {
    id: 1,
    name: 'Email',
    description: 'Send alert notifications to selected users.',
    channel_type: 'email',
  },
  {
    id: 2,
    name: 'Enterprise WeChat',
    description: 'Deliver alerts to configured chatbot endpoints.',
    channel_type: 'enterprise_wechat_bot',
  },
  {
    id: 3,
    name: 'NATS',
    description: 'Forward events to the internal message bus.',
    channel_type: 'nats',
  },
];

export const eventNotificationUsers = [
  { id: 101, display_name: 'Alice Wang' },
  { id: 102, display_name: 'Brandon Li' },
  { id: 103, display_name: 'Carol Zhang' },
];

const eventNotificationTranslations: Record<string, string> = {
  'monitor.events.notificationConfig': 'Notification',
  'monitor.events.notificationDesc':
    'Turn on outbound notifications for this event strategy.',
  'monitor.events.notificationChannel': 'Channels',
  'monitor.events.notifier': 'Recipients',
  'monitor.events.noticeWay': 'No channel is configured yet.',
  'monitor.events.systemManage': 'System manager',
  'monitor.events.config': ' can be used to add one.',
  'log.event.notificationConfig': 'Notification',
  'log.event.notificationDesc':
    'Turn on outbound notifications for this event strategy.',
  'log.event.notificationChannel': 'Channels',
  'log.event.notifier': 'Recipients',
  'log.event.noticeWay': 'No channel is configured yet.',
  'log.event.systemManage': 'System manager',
  'log.event.config': ' can be used to add one.',
  'log.event.notifierTagsPlaceholder': 'Enter recipient tokens',
  'monitor.events.channelTypeEmail': 'Email',
  'monitor.events.channelTypeWechatBot': 'WeChat Bot',
  'monitor.events.channelTypeFeishuBot': 'Feishu Bot',
  'monitor.events.channelTypeDingtalkBot': 'DingTalk Bot',
  'monitor.events.channelTypeCustomWebhook': 'Webhook',
  'monitor.events.channelTypeNats': 'NATS',
  'log.event.channelTypeEmail': 'Email',
  'log.event.channelTypeWechatBot': 'WeChat Bot',
  'log.event.channelTypeFeishuBot': 'Feishu Bot',
  'log.event.channelTypeDingtalkBot': 'DingTalk Bot',
  'log.event.channelTypeCustomWebhook': 'Webhook',
  'log.event.channelTypeNats': 'NATS',
  'common.required': 'Required',
};

export const eventNotificationStoryT = (key: string) =>
  eventNotificationTranslations[key] || key;
