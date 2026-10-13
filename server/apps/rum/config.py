# Celery beat schedule for RUM alert evaluation.

CELERY_BEAT_SCHEDULE = {
    "rum_evaluate_alert_policies": {
        "task": "apps.rum.tasks.evaluate_rum_alert_policies",
        "schedule": 30.0,
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
