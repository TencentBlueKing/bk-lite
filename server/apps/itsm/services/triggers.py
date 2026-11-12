from apps.core.logger import itsm_logger as logger
from apps.itsm.models import TicketTag
from apps.itsm.models.extend import Trigger, TriggerLog


def fire_triggers(ticket, action: str, operator: str) -> None:
    """按事件匹配已启用触发器。打标签直接生效，通知走现有通知发送。"""
    for trigger in Trigger.objects.filter(is_enabled=True, event=action):
        config = trigger.config or {}
        response = str(config.get("response") or config.get("name") or "").strip()
        message = trigger.action
        if trigger.action == "tag" and response:
            tag, _created = TicketTag.objects.get_or_create(
                domain=ticket.domain,
                name=response,
                defaults={"created_by": operator, "updated_by": operator},
            )
            ticket.tags.add(tag)
            message = f"tag:{response}"
        elif trigger.action == "notice" and ticket.created_by:
            from apps.itsm.services.notify.service import dispatch_notification

            try:
                dispatch_notification("trigger", {"title": trigger.name, "content": response or trigger.name}, [ticket.created_by])
                message = "notice:sent"
            except Exception as exc:
                logger.warning("触发器通知失败 error_type=%s", type(exc).__name__)
                message = "notice:failed"
        elif trigger.action == "status" and response:
            message = f"status:{response}"
        TriggerLog.objects.create(
            trigger=trigger,
            ticket_id=ticket.id,
            message=message,
            created_by=operator,
            updated_by=operator,
        )
