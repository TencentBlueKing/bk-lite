import { describe, expect, it } from 'vitest';
import { getChannelColorGuide } from '../notificationTemplateColorGuide';

describe('通知模板颜色参考', () => {
  it('按渠道给出可抄的颜色写法', () => {
    expect(getChannelColorGuide('enterprise_wechat_bot').choices.map((item) => item.token)).toEqual([
      'warning',
      'comment',
      'info',
    ]);
    expect(getChannelColorGuide('enterprise_wechat_bot').choices[0].snippet).toBe(
      '<font color="warning">{{ alert.level }}</font>',
    );
    expect(getChannelColorGuide('feishu_bot').choices.map((item) => item.token)).toEqual([
      'red',
      'orange',
      'yellow',
      'green',
    ]);
    expect(getChannelColorGuide('email').choices.map((item) => item.token)).toEqual([
      '{{ alert.level_color }}',
      '#F43B2C',
      '#D97007',
      '#FFAD42',
    ]);
  });

  it('不能上色的渠道没有可抄写法', () => {
    for (const channelType of ['dingtalk_bot', 'im_notification', 'enterprise_wechat', 'custom_webhook', 'nats']) {
      expect(getChannelColorGuide(channelType).choices).toEqual([]);
      expect(getChannelColorGuide(channelType).introKey).toBe('settings.notificationTemplate.colorTipUnsupported');
    }
  });
});
