from celery import shared_task

from apps.cmdb.services.owner_handover import execute_saved_task


@shared_task(name="apps.cmdb.tasks.owner_handover.execute_owner_handover", ignore_result=True, max_retries=0)
def execute_owner_handover(task_id, execution_token):
    execute_saved_task(task_id, execution_token)
