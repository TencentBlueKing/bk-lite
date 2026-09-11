from apps.core.celery_schedule import beat_crontab

CELERY_BEAT_SCHEDULE = {
    "apm_reconcile_telemetry_catalog": {
        "task": "apps.apm.tasks.reconcile_telemetry_catalog",
        "schedule": beat_crontab(minute="*"),
    },
    "apm_probe_runtime_dependencies": {
        "task": "apps.apm.tasks.probe_apm_runtime_dependencies",
        "schedule": beat_crontab(minute="*"),
    },
    "apm_dispatch_policy_evaluations": {
        "task": "apps.apm.tasks.dispatch_apm_policy_evaluations",
        "schedule": beat_crontab(minute="*"),
    },
    "apm_deliver_alert_outbox": {
        "task": "apps.apm.tasks.deliver_apm_alert_outbox",
        "schedule": beat_crontab(minute="*"),
    },
    "apm_persist_event_snapshot_payloads": {
        "task": "apps.apm.tasks.persist_apm_event_snapshot_payloads",
        "schedule": beat_crontab(minute="*"),
    },
    "apm_expire_event_snapshot_payloads": {
        "task": "apps.apm.tasks.expire_apm_event_snapshot_payloads",
        "schedule": beat_crontab(hour="3", minute="17"),
    },
}
