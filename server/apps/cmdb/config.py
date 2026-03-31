# -- coding: utf-8 --
# @File: config.py
# @Time: 2025/4/24 11:06
# @Author: windyzhao
from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    "sync_periodic_update_task_status": {
        "task": "apps.cmdb.tasks.celery_tasks.sync_periodic_update_task_status",
        "schedule": crontab(minute="*/5"),
    },
    "check_subscription_rules": {
        "task": "apps.cmdb.tasks.celery_tasks.check_subscription_rules",
        "schedule": crontab(minute="*/5"),
    },
    "daily_data_cleanup": {
        "task": "apps.cmdb.tasks.celery_tasks.daily_data_cleanup_task",
        "schedule": crontab(hour=2, minute=0),
    },
}
