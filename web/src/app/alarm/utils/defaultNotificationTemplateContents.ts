import { NotificationTemplateContent } from '@/app/alarm/types/settings';

export const LEGACY_ALERT_OPERATION_EMAIL_BODY = '<h2>{{ notification.scene_name }}｜{{ alert.title }}</h2><table style="width:100%;border-collapse:collapse"><tr><td>告警级别</td><td><strong>{{ alert.level }}</strong></td></tr><tr><td>告警资源</td><td>{{ alert.resource_name }}（{{ alert.resource_type }}）</td></tr><tr><td>监控来源</td><td>{{ alert.source_name }} / {{ alert.item }}</td></tr><tr><td>发生时间</td><td>{{ alert.created_at }}</td></tr><tr><td>本次接收人</td><td>{{ notification.receiver_names }}</td></tr></table><p><strong>告警内容</strong><br>{{ alert.content }}</p><p>告警 ID：{{ alert.alert_id }}</p>';

export const FORMATTED_ALERT_OPERATION_EMAIL_BODY = `<h2>{{ notification.scene_name }}｜{{ alert.title }}</h2>
<table style="width:100%;border-collapse:collapse">
  <tr>
    <td>告警级别</td>
    <td><strong>{{ alert.level }}</strong></td>
  </tr>
  <tr>
    <td>告警资源</td>
    <td>{{ alert.resource_name }}（{{ alert.resource_type }}）</td>
  </tr>
  <tr>
    <td>监控来源</td>
    <td>{{ alert.source_name }} / {{ alert.item }}</td>
  </tr>
  <tr>
    <td>发生时间</td>
    <td>{{ alert.created_at }}</td>
  </tr>
  <tr>
    <td>本次接收人</td>
    <td>{{ notification.receiver_names }}</td>
  </tr>
</table>
<p>
  <strong>告警内容</strong><br>
  {{ alert.content }}
</p>
<p>告警 ID：{{ alert.alert_id }}</p>`;

export const formatLegacyAlertOperationContent = (
  content: NotificationTemplateContent,
): NotificationTemplateContent => content.channel_type === 'email'
  && content.body_template === LEGACY_ALERT_OPERATION_EMAIL_BODY
  ? { ...content, body_template: FORMATTED_ALERT_OPERATION_EMAIL_BODY }
  : content;

const ALERT_OPERATION_SUBJECT = '【{{ notification.scene_name }}】【待认领】【{{ alert.level }}】{{ alert.title }}';
const ALERT_OPERATION_MARKDOWN_BODY = `### {{ notification.scene_name }}｜待认领｜{{ alert.level }}

**{{ alert.title }}**

> {{ notification.action_summary }}

#### 操作信息

- **操作类型：** {{ notification.scene_name }}
- **操作人：** {{ notification.actor_name }}
- **当前处理人：** {{ notification.receiver_names }}
- **操作时间：** {{ notification.action_time }}
- **当前状态：** 待响应

#### 告警信息

- **告警资源：** {{ alert.resource_name }}（{{ alert.resource_type }}）
- **监控来源：** {{ alert.source_name }} / {{ alert.item }}
- **发生时间：** {{ alert.created_at }}

**告警内容**

> {{ alert.content }}

告警 ID：{{ alert.alert_id }}

**请进入告警中心认领并处理该告警。**`;
const alertOperationTextBody = (prefix: string) => `${prefix}
通知场景：{{ notification.scene_name }}
处理状态：待认领
告警级别：{{ alert.level }}
告警标题：{{ alert.title }}

{{ notification.action_summary }}

操作信息：
- 操作类型：{{ notification.scene_name }}
- 操作人：{{ notification.actor_name }}
- 当前处理人：{{ notification.receiver_names }}
- 操作时间：{{ notification.action_time }}
- 当前状态：待响应

告警信息：
- 告警资源：{{ alert.resource_name }}（{{ alert.resource_type }}）
- 监控来源：{{ alert.source_name }} / {{ alert.item }}
- 发生时间：{{ alert.created_at }}

告警内容：
{{ alert.content }}

告警 ID：{{ alert.alert_id }}

请进入告警中心认领并处理该告警。`;

export const DEFAULT_ALERT_OPERATION_TEMPLATE_CONTENTS: NotificationTemplateContent[] = [
  {
    channel_type: 'email',
    subject_template: ALERT_OPERATION_SUBJECT,
    body_template: `<div style="font-family:Arial,sans-serif;color:#1f2937;line-height:1.6;">
  <div style="padding:16px;background:#f5f7fa;border-radius:6px;">
    <div style="font-size:13px;color:#6b7280;">{{ notification.scene_name }} · 待认领</div>
    <h2 style="margin:4px 0 0;font-size:20px;">{{ alert.title }}</h2>
  </div>
  <p style="margin:16px 0;padding:12px;background:#fff7e6;border-left:4px solid #faad14;">
    {{ notification.action_summary }}
  </p>
  <h3 style="margin:16px 0 8px;">操作信息</h3>
  <table style="width:100%;border-collapse:collapse;">
    <tr>
      <td style="width:96px;padding:8px;border:1px solid #e5e7eb;">操作类型</td>
      <td style="padding:8px;border:1px solid #e5e7eb;">{{ notification.scene_name }}</td>
    </tr>
    <tr>
      <td style="padding:8px;border:1px solid #e5e7eb;">操作人</td>
      <td style="padding:8px;border:1px solid #e5e7eb;">{{ notification.actor_name }}</td>
    </tr>
    <tr>
      <td style="padding:8px;border:1px solid #e5e7eb;">当前处理人</td>
      <td style="padding:8px;border:1px solid #e5e7eb;">{{ notification.receiver_names }}</td>
    </tr>
    <tr>
      <td style="padding:8px;border:1px solid #e5e7eb;">操作时间</td>
      <td style="padding:8px;border:1px solid #e5e7eb;">{{ notification.action_time }}</td>
    </tr>
    <tr>
      <td style="padding:8px;border:1px solid #e5e7eb;">当前状态</td>
      <td style="padding:8px;border:1px solid #e5e7eb;"><strong>待响应</strong></td>
    </tr>
  </table>
  <h3 style="margin:16px 0 8px;">告警信息</h3>
  <table style="width:100%;border-collapse:collapse;">
    <tr>
      <td style="width:96px;padding:8px;border:1px solid #e5e7eb;">告警级别</td>
      <td style="padding:8px;border:1px solid #e5e7eb;"><strong>{{ alert.level }}</strong></td>
    </tr>
    <tr>
      <td style="padding:8px;border:1px solid #e5e7eb;">告警资源</td>
      <td style="padding:8px;border:1px solid #e5e7eb;">{{ alert.resource_name }}（{{ alert.resource_type }}）</td>
    </tr>
    <tr>
      <td style="padding:8px;border:1px solid #e5e7eb;">监控来源</td>
      <td style="padding:8px;border:1px solid #e5e7eb;">{{ alert.source_name }} / {{ alert.item }}</td>
    </tr>
    <tr>
      <td style="padding:8px;border:1px solid #e5e7eb;">发生时间</td>
      <td style="padding:8px;border:1px solid #e5e7eb;">{{ alert.created_at }}</td>
    </tr>
  </table>
  <div style="margin-top:16px;padding:12px;background:#f9fafb;border-left:4px solid #9ca3af;">
    <strong>告警内容</strong><br>
    {{ alert.content }}
  </div>
  <p style="margin-top:12px;color:#6b7280;font-size:12px;">告警 ID：{{ alert.alert_id }}</p>
  <p style="margin-top:16px;"><strong>请进入告警中心认领并处理该告警。</strong></p>
</div>`,
  },
  {
    channel_type: 'enterprise_wechat_bot',
    subject_template: '',
    body_template: ALERT_OPERATION_MARKDOWN_BODY,
  },
  {
    channel_type: 'dingtalk_bot',
    subject_template: ALERT_OPERATION_SUBJECT,
    body_template: ALERT_OPERATION_MARKDOWN_BODY,
  },
  {
    channel_type: 'feishu_bot',
    subject_template: ALERT_OPERATION_SUBJECT,
    body_template: ALERT_OPERATION_MARKDOWN_BODY,
  },
  {
    channel_type: 'custom_webhook',
    subject_template: '',
    body_template: alertOperationTextBody('[告警操作通知]'),
  },
  {
    channel_type: 'nats',
    subject_template: '',
    body_template: alertOperationTextBody('[WeOps 告警操作通知]'),
  },
];

export const DEFAULT_NOTIFICATION_TEMPLATE_CONTENTS: NotificationTemplateContent[] = [
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
];
