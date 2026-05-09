"""任务完成回调服务

通过 Celery 任务持久化回调请求，确保 worker 重启后仍可继续重试。
回调任务定义在 tasks.py 中（Celery autodiscover_tasks 只扫描 apps/*/tasks.py）。
"""

from celery import current_app

from apps.core.logger import job_logger as logger


def send_callback(execution) -> None:
    """
    任务完成后通过 Celery 异步任务回调通知调用方。

    仅在 execution.callback_url 存在时触发。
    回调任务持久化到 Celery broker，失败时由 Celery 内置重试机制处理（指数退避，最多 5 次）。
    """
    callback_url = getattr(execution, "callback_url", None)
    if not callback_url:
        return

    payload = {
        "task_id": execution.id,
        "status": execution.status,
        "total_count": execution.total_count,
        "success_count": execution.success_count,
        "failed_count": execution.failed_count,
        "finished_at": execution.finished_at.isoformat() if execution.finished_at else None,
    }

    logger.info(f"[callback] 提交回调任务: execution_id={execution.id}, url={callback_url}")
    current_app.send_task("apps.job_mgmt.tasks.do_callback_task", args=[callback_url, payload, execution.id])
