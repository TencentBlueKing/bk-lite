# # 定时任务配置
from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    # 清理过期分发文件 - 每天 02:00 执行
    "cleanup-expired-distribution-files": {
        "task": "apps.job_mgmt.tasks.cleanup_expired_distribution_files_task",
        "schedule": crontab(hour="2", minute="0"),
    },
}
