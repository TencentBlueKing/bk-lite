from apps.core.celery_schedule import beat_crontab

CELERY_BEAT_SCHEDULE = {
    "rum_dispatch_policy_evaluations": {
        "task": "apps.rum.tasks.dispatch_rum_policy_evaluations",
        "schedule": beat_crontab(minute="*"),
    },
    "rum_deliver_alert_outbox": {
        "task": "apps.rum.tasks.deliver_rum_alert_outbox",
        "schedule": beat_crontab(minute="*"),
    },
    "rum_publish_pending_outbox": {
        "task": "apps.rum.tasks.publish_pending_rum_outbox",
        "schedule": 60.0,
    },
    "rum_reconcile_projection": {
        "task": "apps.rum.tasks.reconcile_rum_projection",
        "schedule": 600.0,
    },
}
