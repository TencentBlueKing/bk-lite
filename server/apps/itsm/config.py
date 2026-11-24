# 调度在对应任务落地后再写入。M1-02 只保留空表，避免 beat 指向尚未实现的任务。
CELERY_BEAT_SCHEDULE = {
    "itsm-schedule-tick": {
        "task": "apps.itsm.tasks.schedule_tick",
        "schedule": 15,
    },
    "itsm-sla-tick": {
        "task": "apps.itsm.tasks.sla_tick",
        "schedule": 60,
    },
    "itsm-email-poll": {
        "task": "apps.itsm.tasks.email_poll",
        "schedule": 300,
    },
    "itsm-trigger-notice-tick": {
        "task": "apps.itsm.tasks.trigger_notice_tick",
        "schedule": 30,
    },
    "itsm-auto-tick": {
        "task": "apps.itsm.tasks.auto_tick",
        "schedule": 30,
    },
}
