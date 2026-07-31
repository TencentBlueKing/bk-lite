from celery.schedules import crontab


CELERY_BEAT_SCHEDULE = {
    "apm_reconcile_telemetry_catalog": {
        "task": "apps.apm.tasks.reconcile_telemetry_catalog",
        "schedule": crontab(minute="*"),
    },
    "apm_dispatch_policy_evaluations": {
        "task": "apps.apm.tasks.dispatch_apm_policy_evaluations",
        "schedule": crontab(minute="*"),
    },
    "apm_deliver_alert_outbox": {
        "task": "apps.apm.tasks.deliver_apm_alert_outbox",
        "schedule": crontab(minute="*"),
    },
}
