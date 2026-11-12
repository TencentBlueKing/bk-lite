from datetime import datetime, timedelta

from django.utils import timezone

from apps.itsm.models import SLAPolicy, Ticket, TicketSLARecord


def add_business_minutes(start: datetime, minutes: int, work_days: list[int], work_start: str, work_end: str) -> datetime:
    """从 start 起加上工作分钟。work_days 用 1-7 表示周一到周日。"""
    if minutes <= 0:
        return start
    start_hour, start_minute = (int(part) for part in work_start.split(":"))
    end_hour, end_minute = (int(part) for part in work_end.split(":"))
    cursor = start
    left = minutes
    guard = 0
    while left > 0 and guard < 366 * 24:
        guard += 1
        if cursor.isoweekday() not in work_days:
            cursor = _next_open(cursor, work_days, start_hour, start_minute)
            continue
        day_start = cursor.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
        day_end = cursor.replace(hour=end_hour, minute=end_minute, second=0, microsecond=0)
        if cursor < day_start:
            cursor = day_start
        if cursor >= day_end:
            cursor = _next_open(cursor, work_days, start_hour, start_minute)
            continue
        available = int((day_end - cursor).total_seconds() // 60)
        take = min(left, available)
        cursor += timedelta(minutes=take)
        left -= take
    return cursor


def business_minutes_between(start: datetime, end: datetime, work_days: list[int], work_start: str, work_end: str) -> int:
    if end <= start:
        return 0
    probe = start
    counted = 0
    while probe < end:
        nxt = add_business_minutes(probe, 1, work_days, work_start, work_end)
        if nxt <= probe or nxt > end:
            break
        counted += 1
        probe = nxt
    return counted


def open_records(ticket: Ticket) -> None:
    policies = SLAPolicy.objects.filter(is_enabled=True, workflow=ticket.workflow).select_related("calendar")
    now = timezone.now()
    for policy in policies:
        if TicketSLARecord.objects.filter(ticket=ticket, target=policy.target).exists():
            continue
        calendar = policy.calendar
        due = add_business_minutes(now, policy.minutes, calendar.work_days, calendar.work_start, calendar.work_end)
        TicketSLARecord.objects.create(
            ticket=ticket,
            policy=policy,
            target=policy.target,
            start_at=now,
            due_at=due,
            created_by=ticket.creator,
            updated_by=ticket.creator,
        )


def pause(ticket: Ticket) -> None:
    now = timezone.now()
    ticket.sla_records.filter(finished_at__isnull=True, paused_at__isnull=True).update(paused_at=now)


def resume(ticket: Ticket) -> None:
    now = timezone.now()
    for record in ticket.sla_records.filter(finished_at__isnull=True, paused_at__isnull=False).select_related("policy__calendar"):
        calendar = record.policy.calendar
        paused = business_minutes_between(record.paused_at, now, calendar.work_days, calendar.work_start, calendar.work_end)
        record.paused_seconds += paused * 60
        record.due_at = add_business_minutes(record.due_at, paused, calendar.work_days, calendar.work_start, calendar.work_end)
        record.paused_at = None
        record.save(update_fields=["paused_seconds", "due_at", "paused_at", "updated_at"])


def finish(ticket: Ticket, target: str) -> None:
    now = timezone.now()
    for record in ticket.sla_records.filter(target=target, finished_at__isnull=True):
        record.finished_at = now
        record.breached = now > record.due_at
        record.paused_at = None
        record.save(update_fields=["finished_at", "breached", "paused_at", "updated_at"])


def _next_open(cursor: datetime, work_days: list[int], hour: int, minute: int) -> datetime:
    probe = (cursor + timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0)
    for _ in range(8):
        if probe.isoweekday() in work_days:
            return probe
        probe += timedelta(days=1)
    return probe
