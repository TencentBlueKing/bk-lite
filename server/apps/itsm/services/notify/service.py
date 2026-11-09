from jinja2 import Template

from apps.core.logger import itsm_logger
from apps.itsm.models import NotifyTemplate
from apps.rpc.console_mgmt import ConsoleMgmt
from apps.rpc.system_mgmt import SystemMgmt
from apps.system_mgmt.models.channel import Channel, ChannelChoices


def render_template(event: str, variables: dict) -> tuple[str, str]:
    template = NotifyTemplate.objects.filter(event=event).first()
    if template is None:
        title = variables.get("title") or event
        return str(title), str(variables.get("content") or title)
    return Template(template.title_tpl).render(**variables), Template(template.content_tpl).render(**variables)


def dispatch_notification(event: str, variables: dict, receivers: list[str], event_key: str = "") -> dict:
    """站内通知走控制台，邮件走系统管理里已配置的 email 通道。"""
    title, content = render_template(event, variables)
    message = f"{title}\n{content}".strip()
    site = ConsoleMgmt(is_local_client=True).create_notification(
        "itsm",
        message,
        recipient_usernames=receivers,
        target_url=variables.get("url") or "",
        event_key=event_key or None,
    )
    email = _send_email_if_configured(title, content, receivers)
    itsm_logger.info("ITSM 通知 %s site=%s email=%s", event, site.get("result"), email.get("result"))
    return {"title": title, "content": content, "receivers": receivers, "site": site, "email": email}


def _send_email_if_configured(title: str, content: str, receivers: list[str]) -> dict:
    channel = Channel.objects.filter(channel_type=ChannelChoices.EMAIL).order_by("id").first()
    if channel is None:
        return {"result": False, "skipped": True, "message": "no_email_channel"}
    return SystemMgmt(is_local_client=True).send_msg_with_channel(channel.id, title, content, receivers, channel_type=ChannelChoices.EMAIL)


def deliver_with_retry(event: str, variables: dict, receivers: list[str], event_key: str = "", attempts: int = 3) -> dict:
    last_error = None
    for _ in range(attempts):
        try:
            return dispatch_notification(event, variables, receivers, event_key)
        except Exception as exc:
            last_error = exc
            itsm_logger.warning("ITSM 通知发送失败，准备重试: %s", type(exc).__name__)
    raise RuntimeError("通知发送失败") from last_error
