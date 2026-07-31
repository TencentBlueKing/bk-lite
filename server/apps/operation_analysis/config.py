# -- coding: utf-8 --
from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    "scan_due_dashboard_report_subscriptions": {
        "task": "operation_analysis.scan_due_dashboard_report_subscriptions",
        "schedule": crontab(minute="*"),
    },
    "converge_timed_out_dashboard_report_executions": {
        "task": (
            "operation_analysis.converge_timed_out_dashboard_report_executions"
        ),
        "schedule": crontab(minute="*"),
    },
}
