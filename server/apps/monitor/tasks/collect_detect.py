from celery import shared_task

from apps.monitor.services.collect_detect import CollectDetectService


@shared_task
def run_collect_detect_task(task_id, runtime_payload):
    return CollectDetectService.run_task(task_id, runtime_payload)
