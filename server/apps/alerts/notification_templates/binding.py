from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rest_framework import serializers

from apps.alerts.constants.constants import LevelType
from apps.alerts.models.models import Level
from apps.alerts.models.notification_template import NotificationTemplate, NotificationTemplateContent, NotificationTemplateReference
from apps.alerts.notification_templates.renderer import build_alert_context, render_source
from apps.alerts.utils.permission_scope import apply_team_scope_with_group_ids, get_authorized_group_ids
from apps.system_mgmt.models.channel import Channel

SCENES = {"assignment", "reminder", "escalation", "recovery"}


class TemplateBindingError(ValueError):
    pass


@dataclass(frozen=True)
class BoundTemplateResult:
    title: str
    content: str
    template_id: int
    revision: int
    missing_fields: list[str]


def select_template_id(channel: dict[str, Any], scene: str):
    bindings = channel.get("notification_templates")
    if not isinstance(bindings, dict):
        return None
    if scene in bindings:
        return bindings[scene]
    return bindings.get("default")


def merge_channel_template_bindings(channels, fallback_channels):
    """把策略默认绑定补到层级渠道，层级显式值优先。"""
    fallback_by_id = {str(item.get("id")): item for item in (fallback_channels or []) if isinstance(item, dict) and item.get("id") is not None}
    merged = []
    for channel in channels or []:
        if not isinstance(channel, dict):
            merged.append(channel)
            continue
        fallback = fallback_by_id.get(str(channel.get("id")), {})
        inherited = fallback.get("notification_templates") if isinstance(fallback, dict) else None
        current = channel.get("notification_templates")
        if isinstance(inherited, dict) or isinstance(current, dict):
            merged.append(
                {
                    **channel,
                    "notification_templates": {
                        **(inherited if isinstance(inherited, dict) else {}),
                        **(current if isinstance(current, dict) else {}),
                    },
                }
            )
        else:
            merged.append(channel)
    return merged


def build_runtime_alert_context(alert, receivers, scene, notification_context=None):
    """使用运行时告警和级别配置构造模板上下文。"""
    try:
        raw_level = int(getattr(alert, "level", ""))
    except (TypeError, ValueError):
        level_display_name = str(getattr(alert, "level", "") or "")
    else:
        level_display_name = Level.objects.filter(level_type=LevelType.ALERT, level_id=raw_level).values_list(
            "level_display_name", flat=True
        ).first() or str(raw_level)
    return build_alert_context(
        alert,
        receivers,
        scene,
        level_display_name=level_display_name,
        notification_context=notification_context,
    )


def render_bound_template(template_id, channel_type, alert, receivers, scene, notification_context=None):
    try:
        template = NotificationTemplate.objects.get(pk=int(template_id))
        content = NotificationTemplateContent.objects.get(template=template, channel_type=channel_type)
    except (TypeError, ValueError, NotificationTemplate.DoesNotExist, NotificationTemplateContent.DoesNotExist) as exc:
        raise TemplateBindingError("模板不存在或未配置该通知方式") from exc
    if template.scope not in {
        NotificationTemplate.SCOPE_SINGLE_ALERT,
        NotificationTemplate.SCOPE_ALERT_OPERATION,
    }:
        raise TemplateBindingError("该模板不是单告警模板")
    template_teams = {str(item) for item in (template.team or [])}
    alert_teams = {str(item) for item in (getattr(alert, "team", None) or [])}
    if not template.is_global and (not template_teams or not template_teams.intersection(alert_teams)):
        raise TemplateBindingError("模板与告警不属于同一团队")

    context = build_runtime_alert_context(alert, receivers, scene, notification_context)
    subject = render_source(
        content.subject_template,
        context,
        channel_type=channel_type,
        is_subject=True,
        scope=template.scope,
    )
    body = render_source(content.body_template, context, channel_type=channel_type, scope=template.scope)
    return BoundTemplateResult(
        title=subject.value,
        content=body.value,
        template_id=template.id,
        revision=template.revision,
        missing_fields=list(dict.fromkeys(subject.missing_fields + body.missing_fields)),
    )


def _iter_bound_channels(notify_channels, config):
    for index, channel in enumerate(notify_channels or []):
        yield channel, f"notify_channels.{index}", "assignment"
    escalation = (config or {}).get("escalation") if isinstance(config, dict) else None
    for layer_index, layer in enumerate((escalation or {}).get("layers") or []):
        for channel_index, channel in enumerate(layer.get("notify_channels") or []):
            yield channel, f"config.escalation.layers.{layer_index}.notify_channels.{channel_index}", "escalation"


def validate_assignment_template_bindings(notify_channels, config, request=None):
    bound_channels = list(_iter_bound_channels(notify_channels, config))
    if not any(isinstance(channel, dict) and channel.get("notification_templates") is not None for channel, _locator, _scene in bound_channels):
        return
    authorized = set(get_authorized_group_ids(request)) if request and not getattr(request.user, "is_superuser", False) else None
    channel_ids = {
        channel.get("id")
        for channel, _locator, _scene in bound_channels
        if isinstance(channel, dict) and isinstance(channel.get("notification_templates"), dict) and channel.get("id") is not None
    }
    channel_queryset = Channel.objects.filter(pk__in=channel_ids)
    if authorized is not None:
        channel_queryset = apply_team_scope_with_group_ids(channel_queryset, authorized)
    trusted_channels = {str(channel.pk): channel for channel in channel_queryset}
    errors = []
    for channel, locator, _default_scene in bound_channels:
        if not isinstance(channel, dict):
            errors.append({"locator": locator, "detail": "通知渠道配置必须是对象"})
            continue
        bindings = channel.get("notification_templates")
        if bindings is None:
            continue
        if not isinstance(bindings, dict):
            errors.append({"locator": locator, "detail": "notification_templates 必须是对象"})
            continue
        trusted_channel = trusted_channels.get(str(channel.get("id")))
        if trusted_channel is None:
            errors.append({"locator": locator, "detail": "通知渠道不存在或无权使用"})
            continue
        if channel.get("channel_type") != trusted_channel.channel_type:
            errors.append({"locator": locator, "detail": "通知渠道类型与系统配置不一致"})
            continue
        if trusted_channel.channel_type == "nats" and (trusted_channel.config or {}).get("source") != "opspilot":
            errors.append({"locator": locator, "detail": "仅 OpsPilot 托管的 NATS 渠道支持通知模板"})
            continue
        for scene, template_id in bindings.items():
            if scene != "default" and scene not in SCENES:
                errors.append({"locator": locator, "detail": f"不支持的通知场景: {scene}"})
                continue
            if template_id is None:
                continue
            try:
                template = NotificationTemplate.objects.get(pk=int(template_id))
            except (TypeError, ValueError, NotificationTemplate.DoesNotExist):
                errors.append({"locator": locator, "detail": f"模板不存在: {template_id}"})
                continue
            if template.scope != NotificationTemplate.SCOPE_SINGLE_ALERT:
                errors.append({"locator": locator, "detail": "告警操作内置模板不能绑定到分派策略"})
                continue
            if not template.contents.filter(channel_type=trusted_channel.channel_type).exists():
                errors.append({"locator": locator, "detail": "模板未配置当前渠道类型"})
            if not template.is_global:
                template_teams = {int(item) for item in template.team or []}
                channel_teams = {int(item) for item in trusted_channel.team or []}
                if not template_teams.intersection(channel_teams):
                    errors.append({"locator": locator, "detail": "模板与通知渠道不属于同一团队"})
            if authorized is not None and not template.is_global:
                template_teams = {int(item) for item in template.team or []}
                if not template_teams.intersection(authorized):
                    errors.append({"locator": locator, "detail": "无权使用该模板"})
    if errors:
        raise serializers.ValidationError({"notify_channels": errors})


def sync_assignment_template_references(assignment):
    source_id = str(assignment.pk)
    NotificationTemplateReference.objects.filter(source_type="assignment", source_id=source_id).delete()
    references = []
    for channel, locator, default_scene in _iter_bound_channels(assignment.notify_channels, assignment.config):
        bindings = channel.get("notification_templates") if isinstance(channel, dict) else None
        if not isinstance(bindings, dict):
            continue
        for scene, template_id in bindings.items():
            if template_id is None:
                continue
            references.append(
                NotificationTemplateReference(
                    template_id=int(template_id),
                    source_type="assignment",
                    source_id=source_id,
                    scene=scene,
                    channel_id=channel.get("id"),
                    locator=locator,
                )
            )
    NotificationTemplateReference.objects.bulk_create(references)


def sync_escalation_template_references(task):
    """为活动升级任务保存渠道绑定快照引用，防止策略更新后模板被提前删除。"""
    source_id = str(task.alert.alert_id)
    NotificationTemplateReference.objects.filter(source_type="escalation_task", source_id=source_id).delete()
    if not task.is_active:
        return
    references = []
    for layer_index, layer in enumerate(task.layers or []):
        for channel_index, channel in enumerate(layer.get("notify_channels") or []):
            bindings = channel.get("notification_templates") if isinstance(channel, dict) else None
            if not isinstance(bindings, dict):
                continue
            for scene, template_id in bindings.items():
                if template_id is None:
                    continue
                references.append(
                    NotificationTemplateReference(
                        template_id=int(template_id),
                        source_type="escalation_task",
                        source_id=source_id,
                        scene=scene,
                        channel_id=channel.get("id"),
                        locator=f"layers.{layer_index}.notify_channels.{channel_index}",
                        is_snapshot=True,
                    )
                )
    NotificationTemplateReference.objects.bulk_create(references)


def release_escalation_template_references(alert_id):
    NotificationTemplateReference.objects.filter(source_type="escalation_task", source_id=str(alert_id)).delete()
