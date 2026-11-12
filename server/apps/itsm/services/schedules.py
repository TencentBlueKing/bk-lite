from django_celery_beat.models import CrontabSchedule, PeriodicTask

from apps.itsm.models.extend import ScheduledTask


def register_schedule(item: ScheduledTask) -> None:
    parts = (item.cron or "").split()
    if len(parts) != 5:
        PeriodicTask.objects.filter(name=f"itsm-schedule-{item.id}").update(enabled=False)
        return
    minute, hour, day, month, dow = parts
    cron, _created = CrontabSchedule.objects.get_or_create(
        minute=minute,
        hour=hour,
        day_of_month=day,
        month_of_year=month,
        day_of_week=dow,
    )
    PeriodicTask.objects.update_or_create(
        name=f"itsm-schedule-{item.id}",
        defaults={
            "crontab": cron,
            "task": "apps.itsm.tasks.scheduled_noop",
            "args": f"[{item.id}]",
            "enabled": item.is_enabled,
        },
    )
