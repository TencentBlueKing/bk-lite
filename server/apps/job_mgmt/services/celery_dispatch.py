"""Celery 派发统一封装。

历史代码在 view 内直接 ``task_func.delay(execution.id)`` 后保存 ``celery_task_id``，
broker 不可用时会抛出，留下 PENDING 孤立记录。本模块封装：

- 捕获派发异常；
- 失败时将执行记录置为 FAILED 并入日志；
- 成功时回填 ``celery_task_id``。
"""

from typing import Optional

from apps.core.logger import job_logger as logger
from apps.job_mgmt.constants import ExecutionStatus
from apps.job_mgmt.models import JobExecution


def dispatch_celery_task(task_func, execution: JobExecution) -> Optional[str]:
    """通过 Celery ``.delay()`` 派发任务并回填 ``celery_task_id``。

    Args:
        task_func: Celery shared_task 装饰过的函数（具备 ``.delay``）。
        execution: 已落库的 :class:`JobExecution` 对象。

    Returns:
        派发成功返回 Celery task id；broker 不可用等失败场景返回 ``None``，
        同时将 ``execution.status`` 标记为 :attr:`ExecutionStatus.FAILED`。
    """
    try:
        result = task_func.delay(execution.id)
    except Exception as e:
        logger.exception(f"[dispatch_celery_task] Celery 派发失败: execution_id={execution.id}, task={getattr(task_func, 'name', task_func)}, error={e}")
        execution.status = ExecutionStatus.FAILED
        execution.save(update_fields=["status", "updated_at"])
        return None

    execution.celery_task_id = result.id
    execution.save(update_fields=["celery_task_id", "updated_at"])
    return result.id
