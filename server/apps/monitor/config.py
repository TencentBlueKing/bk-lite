# -- coding: utf-8 --
# @File: config.py
# @Time: 2025/10/21
# @Author: GitHub Copilot
from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    'sync_instance_and_group': {
        'task': 'apps.monitor.tasks.grouping_rule.sync_instance_and_group',
        'schedule': crontab(minute='*/10'),  # 每10分钟执行一次
    },
}

