# -- coding: utf-8 --
# @File: config.py
# @Time: 2025/4/24 11:06
# @Author: windyzhao
from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    'sync_periodic_update_task_status': {
        'task': 'apps.cmdb.celery_tasks.sync_periodic_update_task_status',
        'schedule': crontab(minute='*/5'),
    },
}
