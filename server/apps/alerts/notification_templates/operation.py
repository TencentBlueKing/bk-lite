from __future__ import annotations

from django.db import transaction

from apps.alerts.models.notification_template import NotificationTemplate, NotificationTemplateContent
from apps.alerts.utils.permission_scope import apply_team_scope_with_group_ids
from apps.core.models.maintainer_info import maintainer_kwargs
from apps.system_mgmt.models.channel import Channel, ChannelChoices

OPERATION_TEMPLATE_KEY_PREFIX = "alert_operation:"
SUPPORTED_CHANNEL_TYPES = {
    ChannelChoices.EMAIL,
    ChannelChoices.ENTERPRISE_WECHAT_BOT,
    ChannelChoices.DINGTALK_BOT,
    ChannelChoices.FEISHU_BOT,
    ChannelChoices.CUSTOM_WEBHOOK,
    ChannelChoices.NATS,
}


def is_supported_operation_channel(channel: Channel) -> bool:
    if channel.channel_type not in SUPPORTED_CHANNEL_TYPES:
        return False
    return channel.channel_type != ChannelChoices.NATS or (channel.config or {}).get("source") == "opspilot"


def _legacy_default_content(channel_type: str) -> tuple[str, str]:
    subject = "【{{ notification.scene_name }}】【{{ alert.level }}】{{ alert.title }}"
    if channel_type == ChannelChoices.EMAIL:
        return subject, (
            "<h2>{{ notification.scene_name }}｜{{ alert.title }}</h2>\n"
            '<table style="width:100%;border-collapse:collapse">\n'
            "  <tr>\n"
            "    <td>告警级别</td>\n"
            "    <td><strong>{{ alert.level }}</strong></td>\n"
            "  </tr>\n"
            "  <tr>\n"
            "    <td>告警资源</td>\n"
            "    <td>{{ alert.resource_name }}（{{ alert.resource_type }}）</td>\n"
            "  </tr>\n"
            "  <tr>\n"
            "    <td>监控来源</td>\n"
            "    <td>{{ alert.source_name }} / {{ alert.item }}</td>\n"
            "  </tr>\n"
            "  <tr>\n"
            "    <td>发生时间</td>\n"
            "    <td>{{ alert.created_at }}</td>\n"
            "  </tr>\n"
            "  <tr>\n"
            "    <td>本次接收人</td>\n"
            "    <td>{{ notification.receiver_names }}</td>\n"
            "  </tr>\n"
            "</table>\n"
            "<p>\n"
            "  <strong>告警内容</strong><br>\n"
            "  {{ alert.content }}\n"
            "</p>\n"
            "<p>告警 ID：{{ alert.alert_id }}</p>"
        )
    if channel_type in {
        ChannelChoices.ENTERPRISE_WECHAT_BOT,
        ChannelChoices.DINGTALK_BOT,
        ChannelChoices.FEISHU_BOT,
    }:
        channel_subject = subject if channel_type != ChannelChoices.ENTERPRISE_WECHAT_BOT else ""
        return channel_subject, (
            "### {{ notification.scene_name }}｜{{ alert.title }}\n"
            "> **告警级别**：{{ alert.level }}\n"
            "> **告警资源**：{{ alert.resource_name }}（{{ alert.resource_type }}）\n"
            "> **监控来源**：{{ alert.source_name }} / {{ alert.item }}\n"
            "> **发生时间**：{{ alert.created_at }}\n\n"
            "**告警内容**\n{{ alert.content }}\n\n"
            "告警 ID：{{ alert.alert_id }}  \n"
            "本次接收人：{{ notification.receiver_names }}"
        )
    return "", (
        "[{{ notification.scene_name }}][{{ alert.level }}] {{ alert.title }}\n"
        "资源：{{ alert.resource_name }}（{{ alert.resource_type }}）\n"
        "来源：{{ alert.source_name }} / {{ alert.item }}\n"
        "内容：{{ alert.content }}\n"
        "时间：{{ alert.created_at }}\n"
        "告警 ID：{{ alert.alert_id }}\n"
        "接收人：{{ notification.receiver_names }}"
    )


def _default_content(channel_type: str) -> tuple[str, str]:
    subject = "【{{ notification.scene_name }}】【待认领】【{{ alert.level }}】{{ alert.title }}"
    if channel_type == ChannelChoices.EMAIL:
        return (
            subject,
            """<div style="font-family:Arial,sans-serif;color:#1f2937;line-height:1.6;">
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
</div>""",
        )
    if channel_type in {
        ChannelChoices.ENTERPRISE_WECHAT_BOT,
        ChannelChoices.DINGTALK_BOT,
        ChannelChoices.FEISHU_BOT,
    }:
        channel_subject = subject if channel_type != ChannelChoices.ENTERPRISE_WECHAT_BOT else ""
        return (
            channel_subject,
            """### {{ notification.scene_name }}｜待认领｜{{ alert.level }}

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

**请进入告警中心认领并处理该告警。**""",
        )
    prefix = "[WeOps 告警操作通知]" if channel_type == ChannelChoices.NATS else "[告警操作通知]"
    return (
        "",
        f"""{prefix}
通知场景：{{{{ notification.scene_name }}}}
处理状态：待认领
告警级别：{{{{ alert.level }}}}
告警标题：{{{{ alert.title }}}}

{{{{ notification.action_summary }}}}

操作信息：
- 操作类型：{{{{ notification.scene_name }}}}
- 操作人：{{{{ notification.actor_name }}}}
- 当前处理人：{{{{ notification.receiver_names }}}}
- 操作时间：{{{{ notification.action_time }}}}
- 当前状态：待响应

告警信息：
- 告警资源：{{{{ alert.resource_name }}}}（{{{{ alert.resource_type }}}}）
- 监控来源：{{{{ alert.source_name }}}} / {{{{ alert.item }}}}
- 发生时间：{{{{ alert.created_at }}}}

告警内容：
{{{{ alert.content }}}}

告警 ID：{{{{ alert.alert_id }}}}

请进入告警中心认领并处理该告警。""",
    )


def _first_team_channel(team_id: int) -> Channel | None:
    queryset = apply_team_scope_with_group_ids(Channel.objects.all(), [team_id]).order_by("id")
    email = queryset.filter(channel_type=ChannelChoices.EMAIL).first()
    if email:
        return email
    for channel in queryset:
        if is_supported_operation_channel(channel):
            return channel
    return None


@transaction.atomic
def ensure_alert_operation_template(team_id: int, actor=None) -> NotificationTemplate:
    team_id = int(team_id)
    builtin_key = f"{OPERATION_TEMPLATE_KEY_PREFIX}{team_id}"
    channel = _first_team_channel(team_id)
    channel_type = channel.channel_type if channel else ChannelChoices.EMAIL
    actor_context = {
        "username": getattr(actor, "username", ""),
        "domain": getattr(actor, "domain", ""),
    }
    template, created = NotificationTemplate.objects.get_or_create(
        builtin_key=builtin_key,
        defaults={
            "name": "告警操作通知",
            "description": "用于人工分派和转派告警时通知新的处理人。",
            "team": [team_id],
            "scope": NotificationTemplate.SCOPE_ALERT_OPERATION,
            "channel_id": channel.id if channel else None,
            **maintainer_kwargs(actor_context),
        },
    )
    if created:
        subject, body = _default_content(channel_type)
        NotificationTemplateContent.objects.create(
            template=template,
            channel_type=channel_type,
            subject_template=subject,
            body_template=body,
        )
        return template

    # 与页面编辑使用同一主表行锁，避免默认内容升级覆盖并发提交的用户内容。
    template = NotificationTemplate.objects.select_for_update().get(pk=template.pk)
    selected_channel = Channel.objects.filter(pk=template.channel_id).first() if template.channel_id else None
    content = template.contents.first()
    existing_channel_type = selected_channel.channel_type if selected_channel else getattr(content, "channel_type", channel_type)
    if content and content.channel_type == existing_channel_type:
        legacy_subject, legacy_body = _legacy_default_content(existing_channel_type)
        if content.subject_template == legacy_subject and content.body_template == legacy_body:
            subject, body = _default_content(existing_channel_type)
            updated = NotificationTemplateContent.objects.filter(
                pk=content.pk,
                subject_template=legacy_subject,
                body_template=legacy_body,
            ).update(subject_template=subject, body_template=body)
            if updated:
                template.revision += 1
                template.save(update_fields=["revision", "updated_at"])
    return template


def get_alert_operation_channel(alert) -> dict | None:
    for raw_team_id in getattr(alert, "team", None) or []:
        try:
            team_id = int(raw_team_id)
        except (TypeError, ValueError):
            continue
        template = ensure_alert_operation_template(team_id)
        if not template.channel_id:
            continue
        channel = Channel.objects.filter(pk=template.channel_id).first()
        if not channel or not is_supported_operation_channel(channel):
            continue
        channel_teams = {str(item) for item in (channel.team or [])}
        if str(team_id) not in channel_teams:
            continue
        content = template.contents.filter(channel_type=channel.channel_type).first()
        if not content:
            continue
        return {
            "id": channel.id,
            "name": channel.name,
            "channel_type": channel.channel_type,
            "notification_templates": {"default": template.id},
        }
    return None
