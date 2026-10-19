from apps.core.celery_schedule import beat_crontab

CELERY_BEAT_SCHEDULE = {
    "recycle_expired_cmdb_monitor_tasks": {
        "task": "apps.module_link.tasks.recycle_expired_cmdb_monitor_tasks",
        "schedule": beat_crontab(hour="3", minute="30"),
    },
}
