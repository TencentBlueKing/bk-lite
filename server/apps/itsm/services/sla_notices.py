from django.db import DatabaseError, transaction
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from apps.console_mgmt.services.notifications import create_targeted_notification
from apps.core.logger import itsm_logger as logger
from apps.itsm.models import Ticket, TicketSLARecord, TicketTask
from apps.itsm.models.sla import SLANotice
from apps.system_mgmt.models import User

INACTIVE = {"suspended", "finished", "terminated", "cancelled"}


def active_recipients(domain, names, now):
    valid = set(
        User.objects.filter(domain=domain, username__in=names, disabled=False)
        .filter(Q(account_expires_at__isnull=True) | Q(account_expires_at__gt=now))
        .values_list("username", flat=True)
    )
    return list(dict.fromkeys(name for name in names if name in valid))


def _notify(record, ticket, kind, now):
    if record.notices.filter(kind=kind).exists():
        return False
    if kind == SLANotice.Kind.WARNING:
        names = list(
            ticket.tasks.filter(status__in=[TicketTask.TaskStatus.PENDING, TicketTask.TaskStatus.CLAIMED])
            .exclude(assignee="")
            .order_by("id")
            .values_list("assignee", flat=True)
        )
        missing = "当前没有可通知的处理人"
    else:
        names = record.escalation_users
        missing = "配置的升级对象均不可用"
    recipients = active_recipients(ticket.domain, names, now)
    notice = SLANotice(
        record=record,
        kind=kind,
        domain=ticket.domain,
        triggered_at=now,
        recipients=recipients,
        status=SLANotice.Status.SKIPPED,
        message=missing,
    )
    if recipients:
        title = SLANotice.Kind(kind).label
        target = "响应" if record.target == "response" else "解决"
        try:
            # 控制台通知和执行记录使用同一数据库。失败回滚本次投递，重复扫描由唯一键保护。
            with transaction.atomic():
                for offset in range(0, len(recipients), 20):
                    notification = create_targeted_notification(
                        app_module="itsm",
                        source="itsm",
                        recipient_domain=ticket.domain,
                        content=f"SLA {title}\n{ticket.sn} · {ticket.title}（{target}时限）",
                        target_url=f"/itsm/tickets/{ticket.id}",
                        event_key=f"itsm-sla-{record.id}-{kind}-{offset // 20}",
                        recipient_usernames=recipients[offset : offset + 20],
                    )
                    if offset == 0:
                        notice.notification = notification
            notice.status = SLANotice.Status.SENT
            notice.message = ""
        except DatabaseError as exc:
            logger.warning("SLA 站内通知未写入 sla_record_id=%s kind=%s error_type=%s", record.id, kind, type(exc).__name__)
            notice.notification = None
            notice.status = SLANotice.Status.FAILED
            notice.message = "站内通知写入失败"
    notice.save()
    return True


@transaction.atomic
def _evaluate(record_id, ticket_id, now):
    # 与工单挂起、恢复及完成保持相同的加锁顺序，锁后重新判断时点。
    ticket = Ticket.objects.select_for_update().filter(id=ticket_id).first()
    if ticket is None or (ticket.status_id and ticket.status.key in INACTIVE):
        return None
    record = (
        TicketSLARecord.objects.select_for_update()
        .filter(
            id=record_id,
            ticket=ticket,
            finished_at__isnull=True,
            paused_at__isnull=True,
        )
        .first()
    )
    if record is None:
        return None
    if record.due_at <= now:
        breached = not record.breached
        if breached:
            record.breached = True
            record.save(update_fields=["breached", "updated_at"])
        escalated = record.escalation_users and _notify(record, ticket, SLANotice.Kind.ESCALATION, now)
        return breached if breached or escalated else None
    if record.warning_at and record.warning_at <= now:
        return False if _notify(record, ticket, SLANotice.Kind.WARNING, now) else None
    return None


def scan(*, now=None, limit=100):
    now = now or timezone.now()
    notices = SLANotice.objects.filter(record_id=OuterRef("pk"))
    candidates = (
        TicketSLARecord.objects.filter(finished_at__isnull=True, paused_at__isnull=True)
        .exclude(ticket__status__key__in=INACTIVE)
        .annotate(
            has_warning=Exists(notices.filter(kind=SLANotice.Kind.WARNING)),
            has_escalation=Exists(notices.filter(kind=SLANotice.Kind.ESCALATION)),
        )
        .filter(
            (Q(due_at__lte=now) & (Q(breached=False) | (Q(has_escalation=False) & ~Q(escalation_users=[]))))
            | Q(warning_at__lte=now, due_at__gt=now, has_warning=False)
        )
        .order_by("due_at", "id")
        .values_list("id", "ticket_id")[:limit]
    )
    processed = breached = 0
    for record_id, ticket_id in list(candidates):
        result = _evaluate(record_id, ticket_id, now)
        if result is not None:
            processed += 1
            breached += int(result)
    return {"processed": processed, "breached": breached}
