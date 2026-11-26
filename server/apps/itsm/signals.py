from uuid import uuid4

from django.db.models.signals import post_save
from django.dispatch import Signal, receiver

from apps.itsm.models import TicketComment, TicketLog
from apps.itsm.services.notify.service import ticket_notice_variables
from apps.itsm.services.trigger_delivery import queue_ticket_notice

itsm_event = Signal()


@receiver(itsm_event)
def send_itsm_notification(sender, event, receivers, variables, event_key="", **kwargs):
    queue_ticket_notice(
        event,
        variables or {},
        list(receivers or []),
        event_key or f"itsm-notify-{uuid4().hex}",
        site_only=bool(getattr(sender, "is_test", False)),
        domain=getattr(sender, "domain", ""),
    )


@receiver(post_save, sender=TicketLog)
@receiver(post_save, sender=TicketComment)
def notify_ticket_followers(sender, instance, created, **kwargs):
    """在业务事务内连同关注人快照一起写入投递记录。"""
    if not created or (sender is TicketLog and instance.action in {"create", "save", "survey_ready"}):
        return
    operator = instance.operator if sender is TicketLog else instance.created_by
    event_key = f"itsm-follow-{sender.__name__}-{instance.pk}"
    action = instance.action if sender is TicketLog else "comment"

    from apps.itsm.services.ticket.history import ACTION_LABELS

    ticket = instance.ticket
    receivers = list(ticket.followers.exclude(username=operator).values_list("username", flat=True).distinct())
    if not receivers:
        return
    label = "新评论" if action == "comment" else ACTION_LABELS.get(action, "流程更新")
    queue_ticket_notice(
        "ticket.followed",
        {
            **ticket_notice_variables(ticket, link_to_ticket=True),
            "title": f"关注工单更新：{ticket.title}",
            "content": f"{ticket.sn} · {label}",
            "action_label": label,
        },
        receivers,
        event_key,
        site_only=ticket.is_test,
        domain=ticket.domain,
    )
