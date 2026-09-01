# -- coding: utf-8 --
# @File: __init__.py.py
# @Time: 2025/11/12 16:26
# @Author: windyzhao

# 导入所有任务，使 Celery autodiscover_tasks() 能够发现它们
from apps.cmdb.tasks.celery_tasks import (  # noqa: F401
    check_subscription_rules,
    collect_node_mgmt_hosts,
    consume_change_record_mirror_outbox,
    consume_cmdb_operation_outbox,
    finalize_scan_execution,
    full_sync_auto_association_rule_task,
    recover_change_record_mirror_outbox_task,
    send_subscription_notifications,
    sync_cmdb_display_fields_task,
    sync_collect_task,
    sync_node_mgmt_hosts,
    sync_periodic_update_task_status,
    sync_public_enum_library_snapshots_task,
    trigger_first_collection,
    trigger_scan_execution,
)
from apps.cmdb.tasks.uuid_migration import ensure_uuid_migration_periodic_task, migrate_cmdb_instance_uuid_runtime  # noqa: F401
