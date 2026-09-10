import { describe, expect, it } from 'vitest';
import {
  DEFAULT_ALERT_OPERATION_TEMPLATE_CONTENTS,
  DEFAULT_NOTIFICATION_TEMPLATE_CONTENTS,
  FORMATTED_ALERT_OPERATION_EMAIL_BODY,
  LEGACY_ALERT_OPERATION_EMAIL_BODY,
  formatLegacyAlertOperationContent,
} from '../defaultNotificationTemplateContents';

describe('通知模板组默认内容', () => {
  it('告警操作内置模板为六渠道提供待认领操作内容', () => {
    expect(DEFAULT_ALERT_OPERATION_TEMPLATE_CONTENTS.map((item) => item.channel_type)).toEqual([
      'email',
      'enterprise_wechat_bot',
      'dingtalk_bot',
      'feishu_bot',
      'custom_webhook',
      'nats',
    ]);
    for (const content of DEFAULT_ALERT_OPERATION_TEMPLATE_CONTENTS) {
      expect(content.body_template).toContain('{{ notification.action_summary }}');
      expect(content.body_template).toContain('{{ notification.actor_name }}');
      expect(content.body_template).toContain('{{ notification.action_time }}');
      expect(content.body_template).toContain('待响应');
      expect(content.body_template).toContain('请进入告警中心认领并处理该告警');
    }
    expect(DEFAULT_ALERT_OPERATION_TEMPLATE_CONTENTS.filter((item) => item.subject_template).map((item) => item.channel_type))
      .toEqual(['email', 'dingtalk_bot', 'feishu_bot']);
  });

  it('新建普通模板时提供评审确认的六渠道默认内容', () => {
    expect(DEFAULT_NOTIFICATION_TEMPLATE_CONTENTS.map((item) => item.channel_type)).toEqual([
      'email',
      'enterprise_wechat_bot',
      'dingtalk_bot',
      'feishu_bot',
      'custom_webhook',
      'nats',
    ]);

    expect(DEFAULT_NOTIFICATION_TEMPLATE_CONTENTS).toEqual([
      {
        channel_type: 'email',
        subject_template: '【{{ notification.scene_name }}·{{ alert.level }}】{{ alert.title }}（{{ alert.resource_name }}）',
        body_template: `<div style="font-family:Arial,sans-serif;color:#1f2937;line-height:1.6;">
  <div style="padding:16px;background:#f5f7fa;border-radius:6px;">
    <div style="font-size:13px;color:#6b7280;">{{ notification.scene_name }}</div>
    <h2 style="margin:4px 0 0;font-size:20px;">{{ alert.title }}</h2>
  </div>
  <table style="width:100%;margin-top:16px;border-collapse:collapse;">
    <tr><td style="width:96px;padding:8px;border:1px solid #e5e7eb;">告警级别</td><td style="padding:8px;border:1px solid #e5e7eb;"><strong>{{ alert.level }}</strong></td></tr>
    <tr><td style="padding:8px;border:1px solid #e5e7eb;">告警资源</td><td style="padding:8px;border:1px solid #e5e7eb;">{{ alert.resource_name }}（{{ alert.resource_type }}）</td></tr>
    <tr><td style="padding:8px;border:1px solid #e5e7eb;">资源 ID</td><td style="padding:8px;border:1px solid #e5e7eb;">{{ alert.resource_id }}</td></tr>
    <tr><td style="padding:8px;border:1px solid #e5e7eb;">监控来源</td><td style="padding:8px;border:1px solid #e5e7eb;">{{ alert.source_name }}</td></tr>
    <tr><td style="padding:8px;border:1px solid #e5e7eb;">监控指标</td><td style="padding:8px;border:1px solid #e5e7eb;">{{ alert.item }}</td></tr>
    <tr><td style="padding:8px;border:1px solid #e5e7eb;">发生时间</td><td style="padding:8px;border:1px solid #e5e7eb;">{{ alert.created_at }}</td></tr>
    <tr><td style="padding:8px;border:1px solid #e5e7eb;">本次接收人</td><td style="padding:8px;border:1px solid #e5e7eb;">{{ notification.receiver_names }}</td></tr>
  </table>
  <div style="margin-top:16px;padding:12px;background:#f9fafb;border-left:4px solid #9ca3af;">
    <strong>告警内容</strong><br>
    {{ alert.content }}
  </div>
  <p style="margin-top:12px;color:#6b7280;font-size:12px;">告警 ID：{{ alert.alert_id }}｜通知时间：{{ notification.generated_at }}</p>
</div>`,
      },
      {
        channel_type: 'enterprise_wechat_bot',
        subject_template: '',
        body_template: `### {{ notification.scene_name }}｜{{ alert.level }}

**{{ alert.title }}**

> {{ alert.content }}

- **告警资源：** {{ alert.resource_name }}（{{ alert.resource_type }}）
- **监控来源：** {{ alert.source_name }}
- **监控指标：** {{ alert.item }}
- **发生时间：** {{ alert.created_at }}
- **本次接收人：** {{ notification.receiver_names }}

告警 ID：{{ alert.alert_id }}
通知时间：{{ notification.generated_at }}`,
      },
      {
        channel_type: 'dingtalk_bot',
        subject_template: '【{{ notification.scene_name }}·{{ alert.level }}】{{ alert.title }}',
        body_template: `### {{ notification.scene_name }}｜{{ alert.title }}

> **{{ alert.level }}**｜{{ alert.resource_name }}（{{ alert.resource_type }}）

**告警内容**

> {{ alert.content }}

- **监控来源：** {{ alert.source_name }}
- **监控指标：** {{ alert.item }}
- **发生时间：** {{ alert.created_at }}
- **本次接收人：** {{ notification.receiver_names }}

告警 ID：{{ alert.alert_id }}
通知时间：{{ notification.generated_at }}`,
      },
      {
        channel_type: 'feishu_bot',
        subject_template: '【{{ notification.scene_name }}·{{ alert.level }}】{{ alert.title }}',
        body_template: `**{{ notification.scene_name }}｜{{ alert.title }}**

**告警级别：** {{ alert.level }}
**告警资源：** {{ alert.resource_name }}（{{ alert.resource_type }}）
**监控来源：** {{ alert.source_name }}
**监控指标：** {{ alert.item }}
**发生时间：** {{ alert.created_at }}
**本次接收人：** {{ notification.receiver_names }}

**告警内容**

> {{ alert.content }}

告警 ID：{{ alert.alert_id }}
通知时间：{{ notification.generated_at }}`,
      },
      {
        channel_type: 'custom_webhook',
        subject_template: '',
        body_template: `[告警通知]
通知场景：{{ notification.scene_name }}
告警级别：{{ alert.level }}
告警标题：{{ alert.title }}
告警 ID：{{ alert.alert_id }}
告警资源：{{ alert.resource_name }}（{{ alert.resource_type }}）
资源 ID：{{ alert.resource_id }}
监控来源：{{ alert.source_name }}
监控指标：{{ alert.item }}
发生时间：{{ alert.created_at }}
本次接收人：{{ notification.receiver_names }}
通知时间：{{ notification.generated_at }}

告警内容：
{{ alert.content }}`,
      },
      {
        channel_type: 'nats',
        subject_template: '',
        body_template: `[WeOps 告警通知]
通知场景：{{ notification.scene_name }}
告警级别：{{ alert.level }}
告警标题：{{ alert.title }}

定位信息：
- 告警 ID：{{ alert.alert_id }}
- 告警资源：{{ alert.resource_name }}（{{ alert.resource_type }}）
- 资源 ID：{{ alert.resource_id }}
- 监控来源：{{ alert.source_name }}
- 监控指标：{{ alert.item }}
- 发生时间：{{ alert.created_at }}
- 本次接收人：{{ notification.receiver_names }}

告警内容：
{{ alert.content }}`,
      },
    ]);
  });

  it('把旧版一行式告警操作邮件正文转换为可编辑的多行 HTML', () => {
    const formatted = formatLegacyAlertOperationContent({
      channel_type: 'email',
      subject_template: '告警操作通知',
      body_template: LEGACY_ALERT_OPERATION_EMAIL_BODY,
    });

    expect(formatted.body_template).toBe(FORMATTED_ALERT_OPERATION_EMAIL_BODY);
    expect(formatted.body_template.split('\n').length).toBeGreaterThan(10);
  });
});
