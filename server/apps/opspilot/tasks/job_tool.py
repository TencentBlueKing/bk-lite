"""作业检查与暂存文件清理。检查只查询原作业号，不调用模型。"""

from celery import shared_task

from apps.opspilot.services.job_tool_service import cleanup_staged_files, scan_job_watches


@shared_task(
    name="apps.opspilot.tasks.scan_opspilot_job_watches",
    queue="opspilot_maintenance",
)
def scan_opspilot_job_watches():
    return scan_job_watches()


@shared_task(
    name="apps.opspilot.tasks.cleanup_opspilot_job_staged_files",
    queue="opspilot_maintenance",
)
def cleanup_opspilot_job_staged_files():
    return cleanup_staged_files()
