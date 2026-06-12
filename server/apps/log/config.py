from celery.schedules import crontab

# 各 app 的 CELERY_BEAT_SCHEDULE 由 config/components/celery.py 自动合并
CELERY_BEAT_SCHEDULE = {
    "compensate_log_notice": {
        "task": "apps.log.tasks.policy.compensate_log_notice_task",
        "schedule": crontab(minute="*/5"),  # 每5分钟回扫一次发送失败的告警通知
    },
}
