export interface NotificationTemplateChannelFormat {
  key: string;
  labelKey: string;
  editorMode: 'html' | 'markdown' | 'text';
  previewMode: 'html' | 'markdown' | 'text';
  hasSubject: boolean;
}

export const NOTIFICATION_TEMPLATE_CHANNELS: NotificationTemplateChannelFormat[] = [
  { key: 'email', labelKey: 'settings.notificationTemplate.email', editorMode: 'html', previewMode: 'html', hasSubject: true },
  { key: 'enterprise_wechat_bot', labelKey: 'settings.notificationTemplate.wecom', editorMode: 'markdown', previewMode: 'markdown', hasSubject: false },
  { key: 'dingtalk_bot', labelKey: 'settings.notificationTemplate.dingtalk', editorMode: 'markdown', previewMode: 'markdown', hasSubject: true },
  { key: 'feishu_bot', labelKey: 'settings.notificationTemplate.feishu', editorMode: 'markdown', previewMode: 'markdown', hasSubject: true },
  { key: 'custom_webhook', labelKey: 'settings.notificationTemplate.webhook', editorMode: 'text', previewMode: 'text', hasSubject: false },
  { key: 'nats', labelKey: 'settings.notificationTemplate.opspilot', editorMode: 'text', previewMode: 'text', hasSubject: false },
];

export const getNotificationTemplateChannel = (channelType: string) => (
  NOTIFICATION_TEMPLATE_CHANNELS.find((item) => item.key === channelType)
);
