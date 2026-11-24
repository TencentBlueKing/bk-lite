from collections import defaultdict
from uuid import uuid4

from django.db import transaction
from jinja2 import TemplateError
from jinja2.sandbox import SandboxedEnvironment

from apps.console_mgmt.services.notifications import create_targeted_notification
from apps.core.logger import itsm_logger
from apps.itsm.models import NotifyTemplate, Ticket
from apps.rpc.system_mgmt import SystemMgmt
from apps.system_mgmt.models.im_notification_channel import IMNotificationChannel, IMNotificationChannelStatusChoices, IMNotificationUserMapping
from apps.system_mgmt.services.capability_contract_service import get_integration_capability_availability

template_environment = SandboxedEnvironment()


def ticket_notice_variables(ticket: Ticket, *, link_to_ticket: bool = False) -> dict[str, str]:
    path = f"/itsm/tickets/{ticket.pk}"
    variables = {"ticket_title": ticket.title, "sn": ticket.sn, "workflow": ticket.workflow.name, "ticket_path": path}
    if link_to_ticket:
        variables["url"] = path
    return variables


def render_template(event: str, variables: dict, *, domain: str, channel_type: str, fallback: tuple[str, str] | None = None) -> tuple[str, str]:
    if domain:
        template = NotifyTemplate.objects.filter(domain=domain, event=event, channel_type=channel_type).first()
        if template is not None:
            try:
                return render_notification_template(template, variables)
            except TemplateError:
                itsm_logger.warning("ITSM 通知模板渲染失败 event=%s channel=%s", event, channel_type)
    if fallback is not None:
        return fallback
    title = variables.get("title") or event
    return str(title), str(variables.get("content") or title)


def render_notification_template(template: NotifyTemplate, variables: dict) -> tuple[str, str]:
    title = template_environment.from_string(template.title_tpl).render(**variables)
    content = template_environment.from_string(template.content_tpl).render(**variables)
    return title, content


def send_site_notification(content: str, receivers: list[str], domain: str, url: str, event_key: str) -> dict:
    if not domain or not receivers:
        return {"result": False, "skipped": True, "message": "缺少通知组织或收件人"}
    key = event_key or f"itsm-notify-{uuid4().hex}"
    with transaction.atomic():
        for offset in range(0, len(receivers), 20):
            suffix = f":{offset // 20}" if offset else ""
            create_targeted_notification(
                app_module="itsm",
                source="itsm",
                content=content,
                recipient_domain=domain,
                recipient_usernames=receivers[offset : offset + 20],
                target_url=url,
                event_key=key[: 200 - len(suffix)] + suffix,
            )
    return {"result": True}


def dispatch_notification(
    event: str,
    variables: dict,
    receivers: list[str],
    event_key: str = "",
    site_only: bool = False,
    *,
    domain: str = "",
    im_link: str = "",
    im_sender=None,
) -> dict:
    receivers = list(dict.fromkeys(name.strip() for name in receivers if isinstance(name, str) and name.strip()))
    title, content = render_template(event, variables, domain=domain, channel_type="site")
    site = send_site_notification(f"{title}\n{content}".strip(), receivers, domain, variables.get("url") or "", event_key)
    im = {"skipped": True}
    if not site_only and domain and receivers:
        im_title, im_content = render_template(event, variables, domain=domain, channel_type="im", fallback=(title, content))
        if im_link and im_link not in im_content:
            im_content = f"{im_content}\n工单详情：{im_link}"
        options = {"im_sender": im_sender} if im_sender is not None else {}
        im = _send_im_if_configured(im_title, im_content, receivers, domain=domain, **options)
    itsm_logger.info("ITSM 通知 %s site=%s im=%s", event, site.get("result"), im.get("result"))
    return {"title": title, "content": content, "receivers": receivers, "site": site, "im": im}


def _send_im_if_configured(title: str, content: str, receivers: list[str], *, domain: str, im_sender=None) -> dict:
    candidates = (
        IMNotificationUserMapping.objects.filter(
            user__domain=domain,
            user__username__in=receivers,
            user__disabled=False,
            channel__enabled=True,
            channel__status=IMNotificationChannelStatusChoices.READY,
        )
        .select_related("channel__integration_instance")
        .order_by("channel_id", "user_id")
    )
    assigned = set()
    batches = defaultdict(list)
    for mapping in candidates:
        if mapping.user_id in assigned or not str((mapping.external_snapshot or {}).get(mapping.external_receive_key) or "").strip():
            continue
        if not get_integration_capability_availability(mapping.channel.integration_instance, "im_notification")["available"]:
            continue
        batches[mapping.channel_id].append(mapping.user_id)
        assigned.add(mapping.user_id)

    if not batches:
        return {"result": False, "skipped": True, "message": "no_im_channel"}

    sender = im_sender or send_im_channel
    results = [sender(channel_id, title, content, user_ids) for channel_id, user_ids in batches.items()]

    succeeded = any(result.get("result") for result in results)
    partial = any(not result.get("result") or (result.get("data") or {}).get("partial_success") for result in results)
    result = {"result": succeeded, "partial_success": succeeded and partial}
    if im_sender is not None:
        result["unknown"] = any(response.get("unknown") for response in results)
    return result


def send_im_channel(channel_id: int, title: str, content: str, user_ids: list[int], *, raise_on_error: bool = False) -> dict:
    try:
        return SystemMgmt().send_msg_with_channel(channel_id, title, content, user_ids, channel_type=IMNotificationChannel.CHANNEL_TYPE)
    except Exception as exc:
        if raise_on_error:
            raise
        itsm_logger.warning("ITSM 即时通知发送结果未知 channel_id=%s error=%s", channel_id, type(exc).__name__)
        return {"result": False}


def deliver_with_retry(
    event: str, variables: dict, receivers: list[str], event_key: str = "", attempts: int = 3, site_only: bool = False, *, domain: str = ""
) -> dict:
    last_error = None
    for _ in range(attempts):
        try:
            return dispatch_notification(event, variables, receivers, event_key, site_only=site_only, domain=domain)
        except Exception as exc:
            last_error = exc
            itsm_logger.warning("ITSM 通知发送失败，准备重试: %s", type(exc).__name__)
    raise RuntimeError("通知发送失败") from last_error
