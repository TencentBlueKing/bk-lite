from apps.core.logger import itsm_logger as logger
from apps.itsm.models import TicketTag
from apps.itsm.models.extend import Trigger, TriggerLog
from apps.itsm.services.form.rules import match_when


def fire_triggers(ticket, action: str, operator: str) -> None:
    """按事件匹配已启用触发器。打标签直接生效，通知走现有通知发送。"""
    aliases = {
        "save": "ticket_update",
        "return": "ticket_back",
        "urge": "ticket_urging",
        "finish": "ticket_finish",
        "create": "ticket_create",
        "suspend": "ticket_suspend",
        "resume": "ticket_recovery",
        "withdraw": "ticket_withdraw",
        "close": "ticket_close",
        "terminate": "ticket_terminate",
        "reopen": "ticket_reopen",
        "task_enter": "activity_into",
    }
    event = aliases.get(action, action)
    for trigger in Trigger.objects.filter(domain=ticket.domain, is_enabled=True, event__in={event, action}):
        config = trigger.config or {}
        if not match_when(config.get("when"), {**(ticket.form_data or {}), "status": ticket.status.key if ticket.status_id else ""}):
            continue
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
            from apps.itsm.services.notify.service import dispatch_notification, ticket_notice_variables

            try:
                dispatch_notification(
                    "trigger",
                    {**ticket_notice_variables(ticket), "title": trigger.name, "content": response or trigger.name},
                    [ticket.created_by],
                    site_only=ticket.is_test,
                    domain=ticket.domain,
                )
                message = "notice:sent"
            except Exception as exc:
                logger.warning("触发器通知失败 error_type=%s", type(exc).__name__)
                message = "notice:failed"
        elif trigger.action == "status" and response:
            from apps.itsm.services.ticket.service import TicketService

            TicketService()._set_status(ticket, response)
            message = f"status:{response}"
        TriggerLog.objects.create(
            trigger=trigger,
            ticket_id=ticket.id,
            message=message,
            created_by=operator,
            updated_by=operator,
        )
