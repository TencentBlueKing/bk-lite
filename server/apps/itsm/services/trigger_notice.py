from collections import defaultdict
from string import Template
from typing import Annotated, Literal

from django.conf import settings
from django.db import DatabaseError
from jinja2 import TemplateError
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from apps.core.logger import itsm_logger as logger
from apps.core.logger import safe_exception_info
from apps.itsm.models import HandlerGroup, NotifyTemplate, TicketTask
from apps.itsm.services.notify.service import (
    render_notification_template,
    render_template,
    send_site_notification,
    ticket_notice_variables,
)
from apps.itsm.services.trigger_fields import person_field_catalog, person_form_fields
from apps.system_mgmt.models import IMNotificationChannel, IMNotificationUserMapping, User
from apps.system_mgmt.models.im_notification_channel import IMNotificationChannelStatusChoices
from apps.system_mgmt.services.capability_contract_service import get_integration_capability_availability
from apps.system_mgmt.services.im_channel_access import filter_accessible_im_channels

IM_BATCH_SIZE = 100
CUSTOM_NOTICE_FIELDS = ("ticket_title", "sn", "workflow", "node", "ticket_link", "creator")
ResourceId = Annotated[int, Field(gt=0, le=2**63 - 1)]
Key = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]
Username = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Role = Literal["creator", "current_assignees"]


class NoticeRecipients(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    roles: list[Role] = Field(default_factory=list, max_length=2)
    users: list[Username] = Field(default_factory=list)
    group_ids: list[ResourceId] = Field(default_factory=list)
    field_keys: list[Key] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_recipients(self):
        if not (self.roles or self.users or self.group_ids or self.field_keys):
            raise ValueError("请选择通知人")
        return self


class SiteRoute(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    type: Literal["site"]
    template_id: ResourceId | None = None


class IMRoute(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    type: Literal["im"]
    channel_id: ResourceId
    template_id: ResourceId | None = None


Route = Annotated[SiteRoute | IMRoute, Field(discriminator="type")]


class TriggerNotice(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    recipients: NoticeRecipients
    channels: list[Route] = Field(min_length=1)
    content_mode: Literal["template", "custom"] | None = None

    @model_validator(mode="after")
    def reject_duplicate_routes(self):
        destinations = {route.channel_id if isinstance(route, IMRoute) else "site" for route in self.channels}
        if len(destinations) != len(self.channels):
            raise ValueError("通知渠道不能重复")
        return self


class NoticeConfigError(ValueError):
    pass


class NoticeClaimLost(Exception):
    pass


def _ready_channels(domain, *, user=None, ids=None):
    queryset = IMNotificationChannel.objects.select_related("integration_instance").filter(
        domain=domain, integration_instance__domain=domain, enabled=True, status=IMNotificationChannelStatusChoices.READY
    )
    if ids is not None:
        queryset = queryset.filter(id__in=ids)
    if user is not None:
        queryset = filter_accessible_im_channels(queryset, user)
    return {
        channel.pk: channel
        for channel in queryset
        if get_integration_capability_availability(channel.integration_instance, "im_notification")["available"]
    }


def _active_users(domain, names):
    return User.objects.filter(domain=domain, disabled=False, username__in=names).order_by("username")


def _notice_templates(domain, routes):
    return NotifyTemplate.objects.filter(domain=domain).in_bulk([route.template_id for route in routes if route.template_id is not None])


def _matches_form_scope(group, scope):
    if scope["mode"] != "include":
        return True
    return (
        ("workflow_ids" not in scope or group.get("workflow_id") in scope["workflow_ids"])
        and ("form_ids" not in scope or group.get("form_id") in scope["form_ids"])
        and ("service_ids" not in scope or set(group.get("service_ids", [])).intersection(scope["service_ids"]))
    )


def validate_notice_references(notice: TriggerNotice, domain, user, scope):
    recipients = notice.recipients
    names, groups = set(recipients.users), set(recipients.group_ids)
    channel_ids = {route.channel_id for route in notice.channels if isinstance(route, IMRoute)}
    if names and _active_users(domain, names).count() != len(names):
        raise NoticeConfigError("请选择本组织有效的通知人员")
    if groups and HandlerGroup.objects.filter(domain=domain, id__in=groups).count() != len(groups):
        raise NoticeConfigError("请选择本组织有效的用户组")
    if channel_ids and _ready_channels(domain, user=user, ids=channel_ids).keys() != channel_ids:
        raise NoticeConfigError("请选择当前有权限且可用的通知渠道")
    if recipients.field_keys:
        fields = {field["key"] for group in person_field_catalog(domain) if _matches_form_scope(group, scope) for field in group["fields"]}
        if not fields.issuperset(recipients.field_keys):
            raise NoticeConfigError("请选择生效范围内的表单人员字段")
    templates = _notice_templates(domain, notice.channels)
    for route in notice.channels:
        if route.template_id is None:
            continue
        template = templates.get(route.template_id)
        if template is None:
            raise NoticeConfigError("所选通知模板不存在")
        if template.channel_type != route.type:
            raise NoticeConfigError("所选通知模板与渠道类型不一致")


def _usernames(raw):
    items = [raw] if isinstance(raw, str) else raw
    return {item.strip() for item in items if isinstance(item, str) and item.strip()} if isinstance(items, list) else set()


def resolve_notice(ticket, notice, *, current_tasks=None):
    from apps.itsm.services.ticket.service import ticket_schema

    if current_tasks is None:
        current_tasks = list(
            ticket.tasks.filter(status__in=(TicketTask.TaskStatus.PENDING, TicketTask.TaskStatus.CLAIMED))
            .order_by("id")
            .values_list("assignee", "node_name")
        )
    names = set(notice.recipients.users)
    if "creator" in notice.recipients.roles:
        names.add(ticket.creator)
    if "current_assignees" in notice.recipients.roles:
        names.update(assignee for assignee, _ in current_tasks if assignee)
    if notice.recipients.group_ids:
        memberships = HandlerGroup.objects.filter(domain=ticket.domain, id__in=notice.recipients.group_ids).values_list("members", flat=True)
        names.update(username for members in memberships for username in _usernames(members))
    if notice.recipients.field_keys:
        requested_fields = set(notice.recipients.field_keys)
        fields = (field["key"] for field in person_form_fields(ticket_schema(ticket)) if field["key"] in requested_fields)
        names.update(username for key in fields for username in _usernames((ticket.form_data or {}).get(key)))
    receivers = list(_active_users(ticket.domain, names).values_list("id", "username")) if names else []
    variables = ticket_notice_variables(ticket, link_to_ticket=True)
    base = (getattr(settings, "WEB_BASE_URL", "") or "").rstrip("/")
    variables["ticket_link"] = f"{base}{variables['ticket_path']}"
    variables["node"] = "、".join(dict.fromkeys(node for _, node in current_tasks if node))
    if notice.content_mode == "custom":
        variables["creator"] = ticket.creator
    return receivers, variables


def deliver_configured_notice(notice, variables, receivers, *, domain, event_key, is_test, im_sender):
    channel_ids = [route.channel_id for route in notice.channels if isinstance(route, IMRoute)]
    channels = _ready_channels(domain, ids=channel_ids)
    templates = _notice_templates(domain, notice.channels)
    mapped = _mapped_notice_users(channels, receivers) if not is_test else {}
    custom_message = None
    if notice.content_mode == "custom":
        title = variables["title"]
        fields = {key: variables[key] for key in CUSTOM_NOTICE_FIELDS}
        content = Template(variables["content"]).safe_substitute(fields, trigger_name=title)
        custom_message = title, content
    results, failures = [], 0
    for route in notice.channels:
        channel_id = route.channel_id if isinstance(route, IMRoute) else None
        target = channels.get(channel_id)
        label = "站内通知" if channel_id is None else target.name[:35] if target else f"即时消息渠道 {channel_id}"
        if channel_id is not None and is_test:
            ok, outcome = True, "测试工单已跳过即时消息"
        elif channel_id is not None and target is None:
            ok, outcome = False, "渠道不可用"
        elif not receivers:
            ok, outcome = False, "无有效通知人"
        else:
            try:
                ok, outcome = _deliver_route(
                    route,
                    variables,
                    receivers,
                    templates.get(route.template_id),
                    mapped.get(channel_id, []),
                    domain=domain,
                    event_key=event_key,
                    custom_message=custom_message,
                    im_sender=im_sender,
                )
            except (DatabaseError, NoticeClaimLost):
                raise
            except Exception as error:
                ok, outcome = False, "发送失败"
                logger.error(
                    "触发器渠道投递失败 event_key=%s channel_id=%s failed_stage=%s error_type=%s",
                    event_key,
                    channel_id,
                    "dispatch_site" if channel_id is None else "dispatch_im",
                    type(error).__name__,
                    exc_info=safe_exception_info(error),
                )
        results.append(f"{label} {outcome}")
        failures += not ok
    message = "；".join(results)
    return failures == 0, (f"{failures} 个渠道未完整投递。{message}" if failures else message)[:200]


def _mapped_notice_users(channels, receivers):
    result = defaultdict(list)
    mappings = IMNotificationUserMapping.objects.filter(channel_id__in=channels, user_id__in=[user_id for user_id, _ in receivers])
    for channel_id, user_id, key, snapshot in mappings.values_list("channel_id", "user_id", "external_receive_key", "external_snapshot"):
        if str((snapshot or {}).get(key) or "").strip():
            result[channel_id].append(user_id)
    return result


def _deliver_route(route, variables, receivers, template, mapped_user_ids, *, domain, event_key, custom_message, im_sender):
    if custom_message is not None:
        title, content = custom_message
    elif route.template_id is None:
        title, content = render_template("trigger", variables, domain=domain, channel_type=route.type)
    else:
        if not template or template.channel_type != route.type:
            return False, "模板不可用"
        try:
            title, content = render_notification_template(template, variables)
        except TemplateError as error:
            logger.error(
                "触发器模板渲染失败 event_key=%s template_id=%s failed_stage=render error_type=%s",
                event_key,
                template.pk,
                type(error).__name__,
                exc_info=safe_exception_info(error),
            )
            return False, "模板渲染失败"
    if isinstance(route, SiteRoute):
        sent = send_site_notification(f"{title}\n{content}".strip(), [username for _, username in receivers], domain, variables["url"], event_key)
        return (True, f"已发送 {len(receivers)} 人") if sent.get("result") else (False, "发送失败")
    if not mapped_user_ids:
        return False, f"{len(receivers)} 人无有效映射"
    link = variables["ticket_link"]
    body = content if link in content else f"{content}\n工单详情：{link}"
    results = [
        im_sender(route.channel_id, title, body, mapped_user_ids[start : start + IM_BATCH_SIZE])
        for start in range(0, len(mapped_user_ids), IM_BATCH_SIZE)
    ]
    if any(result.get("unknown") for result in results):
        return False, "有通知投递结果未知，请核对"
    if any(not result.get("result") or (result.get("data") or {}).get("partial_success") for result in results):
        return False, "有通知未发送成功"
    skipped = len(receivers) - len(mapped_user_ids)
    if skipped:
        return False, f"已发送 {len(mapped_user_ids)} 人，{skipped} 人无有效映射"
    return True, f"已发送 {len(mapped_user_ids)} 人"
