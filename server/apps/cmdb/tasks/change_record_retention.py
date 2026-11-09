from celery import shared_task

from apps.cmdb.services.change_record_retention import run_cleanup


@shared_task(name="apps.cmdb.tasks.change_record_retention.cleanup_change_record_retention")
def cleanup_change_record_retention(trigger: str = "cron") -> dict:
    return run_cleanup(trigger)
