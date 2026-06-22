"""作业模块配置常量与 Celery Beat 调度。

魔法数字集中在此，避免散落在 service / view / task 中。
环境变量可覆盖，便于不同部署灵活调整。
"""

import os

from celery.schedules import crontab


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


# 多目标执行时的并发上限（ExecutionTaskBaseService.MAX_WORKERS）
EXECUTION_MAX_WORKERS = _int_env("JOB_EXECUTION_MAX_WORKERS", 10)

# 并发策略 = queue 时，上次未完成的延迟重试间隔（秒）
SCHEDULED_TASK_QUEUE_RETRY_COUNTDOWN = _int_env("JOB_SCHEDULED_TASK_QUEUE_RETRY_COUNTDOWN", 30)


CELERY_BEAT_SCHEDULE = {
    # 清理过期分发文件 - 每天 00:00 执行
    "cleanup-expired-distribution-files": {
        "task": "apps.job_mgmt.tasks.cleanup_expired_distribution_files_task",
        "schedule": crontab(hour="0", minute="0"),
    },
}
