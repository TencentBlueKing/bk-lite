from apps.core.celery_schedule import beat_crontab

CELERY_BEAT_SCHEDULE = {
    "probe_aggregate_metric_origins": {
        "task": "apps.core.tasks.aggregate_origin.probe_aggregate_metric_origins",
        "schedule": beat_crontab(minute="*"),
    },
}
