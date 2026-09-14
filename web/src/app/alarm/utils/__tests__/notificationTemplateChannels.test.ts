import { describe, expect, it } from 'vitest';
import {
  getNotificationTemplateChannel,
  NOTIFICATION_TEMPLATE_CHANNELS,
} from '../notificationTemplateChannels';

describe('notification template channel formats', () => {
  it('maps each supported channel to exactly one editor format', () => {
    const keys = NOTIFICATION_TEMPLATE_CHANNELS.map((item) => item.key);

    expect(new Set(keys).size).toBe(keys.length);
    expect(getNotificationTemplateChannel('email')).toMatchObject({ editorMode: 'html', hasSubject: true });
    expect(getNotificationTemplateChannel('enterprise_wechat_bot')).toMatchObject({
      editorMode: 'markdown',
      hasSubject: false,
    });
    expect(getNotificationTemplateChannel('dingtalk_bot')?.editorMode).toBe('markdown');
    expect(getNotificationTemplateChannel('feishu_bot')?.editorMode).toBe('markdown');
    expect(getNotificationTemplateChannel('custom_webhook')?.editorMode).toBe('text');
    expect(getNotificationTemplateChannel('nats')?.editorMode).toBe('text');
  });

  it('does not advertise unsupported channel types', () => {
    expect(getNotificationTemplateChannel('enterprise_wechat')).toBeUndefined();
  });
});
