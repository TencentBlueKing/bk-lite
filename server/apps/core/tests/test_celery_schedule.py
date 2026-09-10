from zoneinfo import ZoneInfo

import pytest

from apps.core.celery_schedule import beat_crontab
from config.components.locale import TIME_ZONE

pytestmark = pytest.mark.unit


def test_beat_crontab_defaults_to_project_timezone():
    schedule = beat_crontab(minute="*/5")

    assert schedule._orig_minute == "*/5"
    assert str(schedule.tz) == TIME_ZONE
    assert schedule.tz == ZoneInfo(TIME_ZONE)


def test_beat_crontab_accepts_explicit_timezone_name():
    schedule = beat_crontab(hour=2, minute=0, tz="Asia/Shanghai")

    assert schedule._orig_hour == 2
    assert schedule._orig_minute == 0
    assert str(schedule.tz) == "Asia/Shanghai"
