from __future__ import absolute_import, unicode_literals

import json
import os
import sys

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")

app = Celery("bklite")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

AUTO_DISABLED_APP_MARKER_PREFIX = "[bklite:auto-disabled-app="


def _bklite_app_label(task_path: str) -> str | None:
    parts = task_path.split(".", 2)
    if len(parts) < 3 or parts[0] != "apps":
        return None
    return parts[1]


def _installed_bklite_app_labels(installed_apps: tuple[str, ...] | list[str]) -> set[str]:
    labels = set()
    for app_path in installed_apps:
        parts = app_path.split(".")
        if len(parts) >= 2 and parts[0] == "apps":
            labels.add(parts[1])
    return labels


def _auto_disabled_marker(app_label: str) -> str:
    return f"{AUTO_DISABLED_APP_MARKER_PREFIX}{app_label}]"


def _reconcile_tasks_for_installed_apps(periodic_task_model, installed_apps: tuple[str, ...] | list[str]) -> None:
    installed_labels = _installed_bklite_app_labels(installed_apps)

    auto_disabled = periodic_task_model.objects.filter(
        enabled=False,
        task__startswith="apps.",
        description__contains=AUTO_DISABLED_APP_MARKER_PREFIX,
    )
    for periodic_task in auto_disabled:
        app_label = _bklite_app_label(periodic_task.task)
        if app_label is None or app_label not in installed_labels:
            continue
        marker = _auto_disabled_marker(app_label)
        if periodic_task.description == marker:
            periodic_task.description = ""
        elif periodic_task.description.endswith(f"\n{marker}"):
            periodic_task.description = periodic_task.description.removesuffix(f"\n{marker}")
        else:
            continue
        periodic_task.enabled = True
        periodic_task.save(update_fields=["enabled", "description"])

    for periodic_task in periodic_task_model.objects.filter(enabled=True, task__startswith="apps."):
        app_label = _bklite_app_label(periodic_task.task)
        if app_label is None or app_label in installed_labels:
            continue
        marker = _auto_disabled_marker(app_label)
        separator = "\n" if periodic_task.description else ""
        periodic_task.description = f"{periodic_task.description}{separator}{marker}"
        periodic_task.enabled = False
        periodic_task.save(update_fields=["enabled", "description"])


@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs):
    """将 CELERY_BEAT_SCHEDULE 同步到 django_celery_beat 数据库表"""
    from django.conf import settings

    if "pytest" in sys.modules:
        return

    if not getattr(settings, "IS_USE_CELERY", False):
        return

    from django_celery_beat.models import CrontabSchedule, IntervalSchedule, PeriodicTask

    _reconcile_tasks_for_installed_apps(PeriodicTask, settings.INSTALLED_APPS)

    beat_schedule = getattr(settings, "CELERY_BEAT_SCHEDULE", {})
    if not beat_schedule:
        return

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
