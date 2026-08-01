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
    "cleanup_expired_dashboard_report_pdf_artifacts": {
        "task": (
            "operation_analysis.cleanup_expired_dashboard_report_pdf_artifacts"
        ),
        "schedule": crontab(minute="*/15"),
    },
    "cleanup_expired_dashboard_report_executions": {
        "task": "operation_analysis.cleanup_expired_dashboard_report_executions",
        "schedule": crontab(hour=3, minute=20),
    },
}
