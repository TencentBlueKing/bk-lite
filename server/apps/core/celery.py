from __future__ import absolute_import, unicode_literals

import json
import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")

app = Celery("bklite")
app.config_from_object("django.conf:settings")
app.autodiscover_tasks()


@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs):
    """将 CELERY_BEAT_SCHEDULE 同步到 django_celery_beat 数据库表"""
    from django.conf import settings

    if not getattr(settings, "IS_USE_CELERY", False):
        return

    beat_schedule = getattr(settings, "CELERY_BEAT_SCHEDULE", {})
    if not beat_schedule:
        return

    from django_celery_beat.models import CrontabSchedule, IntervalSchedule, PeriodicTask

    for task_name, task_config in beat_schedule.items():
        task_path = task_config.get("task")
        task_schedule = task_config.get("schedule")
        task_args = task_config.get("args", [])
        task_kwargs = task_config.get("kwargs", {})

        if isinstance(task_schedule, crontab):
            schedule_obj, _ = CrontabSchedule.objects.get_or_create(
                minute=task_schedule._orig_minute,
                hour=task_schedule._orig_hour,
                day_of_week=task_schedule._orig_day_of_week,
                day_of_month=task_schedule._orig_day_of_month,
                month_of_year=task_schedule._orig_month_of_year,
            )
            PeriodicTask.objects.update_or_create(
                name=task_name,
                defaults={
                    "task": task_path,
                    "crontab": schedule_obj,
                    "interval": None,
                    "args": json.dumps(task_args),
                    "kwargs": json.dumps(task_kwargs),
                    "enabled": True,
                },
            )
        elif isinstance(task_schedule, (int, float)):
            schedule_obj, _ = IntervalSchedule.objects.get_or_create(
                every=int(task_schedule),
                period=IntervalSchedule.SECONDS,
            )
            PeriodicTask.objects.update_or_create(
                name=task_name,
                defaults={
                    "task": task_path,
                    "interval": schedule_obj,
                    "crontab": None,
                    "args": json.dumps(task_args),
                    "kwargs": json.dumps(task_kwargs),
                    "enabled": True,
                },
            )
