import { describe, expect, it } from 'vitest';
import {
  activeNotificationTemplateScenes,
  buildChannelsWithTemplateBindings,
  getNotificationTemplateBindings,
} from '../notificationTemplateBinding';

const channels = [
  { id: 1, name: '邮件', channel_type: 'email' },
  { id: 2, name: '企业微信', channel_type: 'enterprise_wechat_bot' },
];

describe('分派策略按渠道和场景绑定通知模板组', () => {
  it('只把已开启的提醒、升级和恢复算作需要选择的场景', () => {
    expect(activeNotificationTemplateScenes({})).toEqual(['default']);
    expect(activeNotificationTemplateScenes({
      notificationFrequency: { '0': { interval_minutes: 0 }, '1': { interval_minutes: 15 } },
      escalationEnabled: true,
      notificationScenario: ['assignment', 'recovery'],
    })).toEqual(['default', 'reminder', 'escalation', 'recovery']);
  });

  it('为每个渠道保存各自的场景绑定，并忽略未选择的场景', () => {
    expect(buildChannelsWithTemplateBindings(['email:1', 'enterprise_wechat_bot:2'], channels, {
      'email:1': { default: 10, reminder: 11, escalation: undefined, recovery: 12 },
      'enterprise_wechat_bot:2': { default: 20, reminder: undefined, escalation: 21, recovery: undefined },
    })).toEqual([
      {
        id: 1,
        name: '邮件',
        channel_type: 'email',
        notification_templates: { default: 10, reminder: 11, recovery: 12 },
      },
      {
        id: 2,
        name: '企业微信',
        channel_type: 'enterprise_wechat_bot',
        notification_templates: { default: 20, escalation: 21 },
      },
    ]);
  });

  it('编辑策略时逐渠道回填已有场景绑定', () => {
    expect(getNotificationTemplateBindings([
      { ...channels[0], notification_templates: { default: 10, reminder: 10 } },
      { ...channels[1], notification_templates: { default: 20, recovery: 21 } },
    ])).toEqual({
      'email:1': { default: 10, reminder: 10 },
      'enterprise_wechat_bot:2': { default: 20, recovery: 21 },
    });
  });
});
