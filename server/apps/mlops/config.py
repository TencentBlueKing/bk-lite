from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    "dispatch_pending_external_resource_cleanup": {
        "task": "apps.mlops.tasks.external_resource_cleanup.dispatch_pending_external_resource_cleanup",
        "schedule": crontab(minute="*"),
    },
    "dispatch_pending_timeseries_runtime_cleanup": {
        "task": "apps.mlops.tasks.runtime_cleanup.dispatch_pending_timeseries_runtime_cleanup",
        "schedule": crontab(minute="*"),
    },
}
