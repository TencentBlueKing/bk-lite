from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import Signal, receiver

from apps.itsm.models import TicketComment, TicketLog
from apps.itsm.services.notify.service import deliver_with_retry, ticket_notice_variables

itsm_event = Signal()


@receiver(itsm_event)
def send_itsm_notification(sender, event, receivers, variables, event_key="", **kwargs):
    deliver_with_retry(
        event,
        variables or {},
        list(receivers or []),
        event_key or "",
        site_only=bool(getattr(sender, "is_test", False)),
        domain=getattr(sender, "domain", ""),
    )


@receiver(post_save, sender=TicketLog)
@receiver(post_save, sender=TicketComment)
def notify_ticket_followers(sender, instance, created, **kwargs):
    """事务提交后通知关注人，回滚操作不发送通知。"""
    if not created or (sender is TicketLog and instance.action in {"create", "save", "survey_ready"}):
        return
    ticket_id = instance.ticket_id
    operator = instance.operator if sender is TicketLog else instance.created_by
    event_key = f"itsm-follow-{sender.__name__}-{instance.pk}"
    action = instance.action if sender is TicketLog else "comment"

    def notify():
        from apps.itsm.models import Ticket
        from apps.itsm.services.ticket.history import ACTION_LABELS

        ticket = Ticket.objects.get(pk=ticket_id)
        receivers = list(ticket.followers.exclude(username=operator).values_list("username", flat=True).distinct())
        if not receivers:
            return
        label = "新评论" if action == "comment" else ACTION_LABELS.get(action, "流程更新")
        deliver_with_retry(
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

    transaction.on_commit(notify, robust=True)
