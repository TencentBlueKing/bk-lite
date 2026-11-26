from datetime import datetime, time, timedelta
from datetime import timezone as utc_zone
from zoneinfo import ZoneInfo

from django.utils import timezone

from apps.itsm.models import SLAPolicy, Ticket, TicketSLARecord


class ServiceClock:
    def __init__(self, config):
        self.zone = ZoneInfo(config["timezone"])
        days = config["work_days"]
        if not isinstance(days, list) or not days or any(type(day) is not int or day not in range(1, 8) for day in days):
            raise ValueError("工作日无效")
        self.days = set(days)
        self.start = time.fromisoformat(config["work_start"])
        self.end = time.fromisoformat(config["work_end"])
        if self.start.tzinfo or self.end.tzinfo or self.start >= self.end:
            raise ValueError("工作时间无效")

    def _windows(self, start):
        day = start.astimezone(self.zone).date()
        while True:
            if day.isoweekday() in self.days:
                yield (
                    datetime.combine(day, self.start, self.zone).astimezone(utc_zone.utc),
                    datetime.combine(day, self.end, self.zone).astimezone(utc_zone.utc),
                )
            day += timedelta(days=1)

    def add(self, start, duration):
        if duration <= timedelta():
            return start
        start = start.astimezone(utc_zone.utc)
        for opens, closes in self._windows(start):
            current = max(start, opens)
            if closes <= current:
                continue
            available = closes - current
            if duration <= available:
                return current + duration
            duration -= available

    def between(self, start, end):
        if end <= start:
            return timedelta()
        start = start.astimezone(utc_zone.utc)
        end = end.astimezone(utc_zone.utc)
        elapsed = timedelta()
        for opens, closes in self._windows(start):
            if opens >= end:
                break
            elapsed += max(timedelta(), min(end, closes) - max(start, opens))
        return elapsed


def calendar_config(calendar):
    return {field: getattr(calendar, field) for field in ("timezone", "work_days", "work_start", "work_end")}


def open_records(ticket: Ticket) -> None:
    policies = SLAPolicy.objects.filter(is_enabled=True, workflow=ticket.workflow, domain=ticket.domain).select_related("calendar")
    now = timezone.now()
    for policy in policies:
        if policy.calendar.domain != ticket.domain or TicketSLARecord.objects.filter(ticket=ticket, target=policy.target).exists():
            continue
        snapshot = calendar_config(policy.calendar)
        clock = ServiceClock(snapshot)
        due = clock.add(now, timedelta(minutes=policy.minutes))
        warning = clock.add(now, timedelta(minutes=policy.minutes - policy.warning_minutes)) if policy.warning_minutes else None
        TicketSLARecord.objects.create(
            ticket=ticket,
            policy=policy,
            target=policy.target,
            start_at=now,
            due_at=due,
            warning_at=warning,
            escalation_users=policy.escalation_users,
            calendar_snapshot=snapshot,
            domain=ticket.domain,
            created_by=ticket.creator,
            updated_by=ticket.creator,
        )


def pause(ticket: Ticket) -> None:
    now = timezone.now()
    ticket.sla_records.filter(finished_at__isnull=True, paused_at__isnull=True).update(paused_at=now)


def resume(ticket: Ticket) -> None:
    now = timezone.now()
    for record in ticket.sla_records.filter(finished_at__isnull=True, paused_at__isnull=False).select_related("policy__calendar"):
        clock = ServiceClock(record.calendar_snapshot or calendar_config(record.policy.calendar))
        paused_at = record.paused_at
        record.paused_seconds += int(clock.between(paused_at, now).total_seconds())
        if paused_at < record.due_at:
            record.due_at = clock.add(now, clock.between(paused_at, record.due_at))
            if record.warning_at:
                record.warning_at = clock.add(now, clock.between(paused_at, record.warning_at))
        record.paused_at = None
        record.save(update_fields=["paused_seconds", "due_at", "warning_at", "paused_at", "updated_at"])


def finish(ticket: Ticket, target: str) -> None:
    now = timezone.now()
    for record in ticket.sla_records.filter(target=target, finished_at__isnull=True):
        record.finished_at = now
        record.breached = record.breached or (record.paused_at or now) > record.due_at
        record.paused_at = None
        record.save(update_fields=["finished_at", "breached", "paused_at", "updated_at"])
