from jinja2 import Template

from apps.core.logger import itsm_logger
from apps.itsm.models import NotifyTemplate
from apps.rpc.console_mgmt import ConsoleMgmt
from apps.rpc.system_mgmt import SystemMgmt
from apps.system_mgmt.models.channel import Channel, ChannelChoices
from apps.system_mgmt.models.im_notification_channel import IMNotificationChannel, IMNotificationChannelStatusChoices


def render_template(event: str, variables: dict) -> tuple[str, str]:
    template = NotifyTemplate.objects.filter(event=event).first()
    if template is None:
        title = variables.get("title") or event
        return str(title), str(variables.get("content") or title)
    return Template(template.title_tpl).render(**variables), Template(template.content_tpl).render(**variables)


def dispatch_notification(event: str, variables: dict, receivers: list[str], event_key: str = "", site_only: bool = False) -> dict:
    """站内通知走控制台。外部消息优先走飞书/企微 IM 应用通知，否则走飞书或钉钉机器人。"""
    title, content = render_template(event, variables)
    message = f"{title}\n{content}".strip()
    site = ConsoleMgmt(is_local_client=True).create_notification(
        "itsm",
        message,
        recipient_usernames=receivers,
        target_url=variables.get("url") or "",
        event_key=event_key or None,
    )
    im = {"skipped": True} if site_only else _send_im_if_configured(title, content, receivers)
    itsm_logger.info("ITSM 通知 %s site=%s im=%s", event, site.get("result"), im.get("result"))
    return {"title": title, "content": content, "receivers": receivers, "site": site, "im": im}


def _send_im_if_configured(title: str, content: str, receivers: list[str]) -> dict:
    im_channel = (
        IMNotificationChannel.objects.select_related("integration_instance")
        .filter(enabled=True, status=IMNotificationChannelStatusChoices.READY)
        .order_by("id")
        .first()
    )
    if im_channel is not None:
        return SystemMgmt().send_msg_with_channel(
            im_channel.id,
            title,
            content,
            receivers,
            channel_type=IMNotificationChannel.CHANNEL_TYPE,
        )
    bot = Channel.objects.filter(channel_type__in=[ChannelChoices.FEISHU_BOT, ChannelChoices.DINGTALK_BOT]).order_by("id").first()
    if bot is None:
        return {"result": False, "skipped": True, "message": "no_im_channel"}
    return SystemMgmt().send_msg_with_channel(bot.id, title, content, receivers, channel_type=bot.channel_type)


def deliver_with_retry(event: str, variables: dict, receivers: list[str], event_key: str = "", attempts: int = 3, site_only: bool = False) -> dict:
    last_error = None
    for _ in range(attempts):
        try:
            return dispatch_notification(event, variables, receivers, event_key, site_only=site_only)
        except Exception as exc:
            last_error = exc
            itsm_logger.warning("ITSM 通知发送失败，准备重试: %s", type(exc).__name__)
    raise RuntimeError("通知发送失败") from last_error
