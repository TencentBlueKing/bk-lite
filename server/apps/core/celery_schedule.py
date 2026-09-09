from zoneinfo import ZoneInfo

from django_celery_beat.tzcrontab import TzAwareCrontab

from config.components.locale import TIME_ZONE


def beat_crontab(
    minute="*",
    hour="*",
    day_of_week="*",
    day_of_month="*",
    month_of_year="*",
    tz=None,
):
    """Build a timezone-aware Celery crontab.

    Static CELERY_BEAT_SCHEDULE entries must pin timezone explicitly so
    django-celery-beat does not collapse UTC and local-wall-clock rows.
    """
    if tz is None:
        resolved_tz = ZoneInfo(TIME_ZONE)
    elif isinstance(tz, str):
        resolved_tz = ZoneInfo(tz)
    else:
        resolved_tz = tz
    return TzAwareCrontab(
        minute=minute,
        hour=hour,
        day_of_week=day_of_week,
        day_of_month=day_of_month,
        month_of_year=month_of_year,
        tz=resolved_tz,
    )
