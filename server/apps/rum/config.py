# Celery beat schedule for RUM alert evaluation.

CELERY_BEAT_SCHEDULE = {
    "rum_evaluate_alert_policies": {
        "task": "apps.rum.tasks.evaluate_rum_alert_policies",
        "schedule": 30.0,
    },
}
