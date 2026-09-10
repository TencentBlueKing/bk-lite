import importlib

import pytest
from celery.schedules import crontab

pytestmark = pytest.mark.unit

OWNED_BEAT_APPS = ("apm", "log", "monitor", "node_mgmt")


def test_owned_static_beat_crontabs_declare_timezone():
    missing = []
    for app_name in OWNED_BEAT_APPS:
        module = importlib.import_module(f"apps.{app_name}.config")
        schedule = getattr(module, "CELERY_BEAT_SCHEDULE", None) or {}
        for name, entry in schedule.items():
            task_schedule = entry.get("schedule")
            if isinstance(task_schedule, crontab) and getattr(task_schedule, "tz", None) is None:
                missing.append(f"{app_name}:{name}")

    assert missing == []
