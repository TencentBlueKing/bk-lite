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

# 过期分发文件清理的对象存储并发上限；至少保留一个 worker。
DISTRIBUTION_FILE_CLEANUP_MAX_CONCURRENCY = max(1, _int_env("JOB_DISTRIBUTION_FILE_CLEANUP_MAX_CONCURRENCY", 10))

# 单批加载与删除的过期分发文件上限，避免大结果集和超长 id__in 参数。
DISTRIBUTION_FILE_CLEANUP_BATCH_SIZE = max(1, _int_env("JOB_DISTRIBUTION_FILE_CLEANUP_BATCH_SIZE", 500))

# 取消兜底先于真实 Ansible 回调提交时，暂缓终态副作用，允许后到回调纠正占位结果。
CALLBACK_CANCEL_RECONCILE_GRACE_SECONDS = _int_env("JOB_CALLBACK_CANCEL_RECONCILE_GRACE_SECONDS", 60)


CELERY_BEAT_SCHEDULE = {
    # 恢复 broker 入队失败、worker 崩溃留下的终态副作用
    "dispatch-pending-job-completion-outbox": {
        "task": "apps.job_mgmt.tasks.dispatch_pending_job_completion_outbox",
        "schedule": crontab(minute="*"),
    },
    # 清理过期分发文件 - 每天 00:00 执行
    "cleanup-expired-distribution-files": {
        "task": "apps.job_mgmt.tasks.cleanup_expired_distribution_files_task",
        "schedule": crontab(hour="0", minute="0"),
    },
}
