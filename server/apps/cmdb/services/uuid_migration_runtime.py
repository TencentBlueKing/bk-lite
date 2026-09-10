"""CMDB 实例 UUID 清洗运行期完成判定。

维护命令 migrate_*_uuid_refs 写入各 stage 断点；运行期 Celery 任务据此快速跳过。
"""

from django.apps import apps as django_apps

from apps.cmdb.models.uuid_migration_state import CmdbUuidMigrationState

# 与 migrate_cmdb_instance_uuid_refs 各 _clean_* stage 名对齐
REQUIRED_CMDB_UUID_STAGES = (
    "graph_instances",
    "config_versions",
    "change_records",
    "subscriptions",
    "subscription_snapshots",
    "followed_assets",
    "custom_reporting_pending",
    "custom_reporting_cleanup",
    "collect_tasks",
    "collect_instances",
    "collect_result_snapshots",
    "node_mgmt_sync_details",
    "operation_targets",
    "operation_snapshots",
    "operation_outbox",
    "monitor_cmdb_ids",
    "node_cmdb_ids",
)

# 与 migrate_oa_cmdb_instance_uuid_refs 中 model_fields 对齐
REQUIRED_OA_UUID_MODEL_NAMES = (
    "Dashboard",
    "Topology",
    "Architecture",
    "Screen",
    "Report",
    "DashboardReportRenderSnapshot",
)

RUNTIME_DONE_STAGE = "uuid_runtime_done"


def _stage_completed(stage: str) -> bool:
    return CmdbUuidMigrationState.objects.filter(stage=stage, completed=True).exists()


def is_cmdb_uuid_migration_complete() -> bool:
    return all(_stage_completed(stage) for stage in REQUIRED_CMDB_UUID_STAGES)


def is_oa_uuid_migration_complete() -> bool:
    for model_name in REQUIRED_OA_UUID_MODEL_NAMES:
        try:
            django_apps.get_model("operation_analysis", model_name)
        except LookupError:
            continue
        if not _stage_completed(f"oa_uuid:{model_name}"):
            return False
    return True


def is_uuid_runtime_migration_complete() -> bool:
    """全部必需 stage 已完成才算收敛。uuid_runtime_done 只是完成标记，不能单独跳过新增 stage。"""
    return is_cmdb_uuid_migration_complete() and is_oa_uuid_migration_complete()


def mark_uuid_runtime_migration_complete() -> None:
    CmdbUuidMigrationState.objects.update_or_create(
        stage=RUNTIME_DONE_STAGE,
        defaults={"cursor": "0", "completed": True},
    )
