# -- coding: utf-8 --
# @File: config.py
# @Time: 2025/5/9 14:56
# @Author: windyzhao
from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    "event_aggregation_alert": {
        "task": "apps.alerts.tasks.tasks.event_aggregation_alert",
        "schedule": crontab(minute="*"),
    },
    "beat_close_alert": {
        "task": "apps.alerts.tasks.tasks.beat_close_alert",
        "schedule": crontab(minute="*/5"),
    },
    "check_and_send_reminders": {
        "task": "apps.alerts.tasks.tasks.check_and_send_reminders",
        "schedule": crontab(minute="*"),
    },
    "cleanup_reminder_tasks": {
        "task": "apps.alerts.tasks.tasks.cleanup_reminder_tasks",
        "schedule": crontab(minute="0", hour="*"),
    }
}
