# -- coding: utf-8 --
# @File: __init__.py.py
# @Time: 2026/2/28 15:24
# @Author: windyzhao

# 导入所有任务，使 Celery autodiscover_tasks() 能够发现它们
from apps.alerts.tasks.tasks import (
    async_auto_assignment_for_alerts,
    beat_close_alert,
    check_and_send_reminders,
    cleanup_reminder_tasks,
    event_aggregation_alert,
    sync_no_dispatch_alert_notice_task,
    sync_notify,
    sync_shield,
)
