# -- coding: utf-8 --
# @File: __init__.py.py
# @Time: 2025/11/12 16:26
# @Author: windyzhao

# 导入所有任务，使 Celery autodiscover_tasks() 能够发现它们
from apps.cmdb.tasks.celery_tasks import (
    sync_cmdb_display_fields_task,
    sync_collect_task,
    sync_periodic_update_task_status,
    sync_public_enum_library_snapshots_task,
)
