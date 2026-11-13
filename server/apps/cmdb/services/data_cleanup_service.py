"""过期删除的每日巡检：按任务归属和上次采集时间删除，不依赖当次采集是否成功。"""
from datetime import timedelta

from django.utils import timezone

from apps.cmdb.collection.cleanup import cleanup_due, is_collection_target, parse_collect_time
from apps.cmdb.constants.constants import INSTANCE, DataCleanupStrategy
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.core.logger import cmdb_logger as logger
from apps.core.logger import safe_exception_info

EXPIRE_DAYS_MIN = 1
EXPIRE_DAYS_MAX = 365
_PAGE_SIZE = 500
_OWNED_FIELDS = [
    "_id",
    "inst_uuid",
    "inst_name",
    "model_id",
    "collect_task",
    "collect_time",
    "_collect_sources",
]


class DataCleanupService:
    parse_collect_time = staticmethod(parse_collect_time)

    @staticmethod
    def get_expire_threshold(expire_days: int) -> str:
        return (timezone.now() - timedelta(days=expire_days)).isoformat()

    @staticmethod
    def cleanup_expired_instances(task) -> dict:
        if not _expiration_enabled(task):
            return {"task_id": task.id, "deleted_count": 0, "skipped": True}
        if getattr(task, "model_id", None) == "pc":
            return _cleanup_expired_pc(task)
        return _cleanup_owned_instances(task)

    @staticmethod
    def run_daily_cleanup() -> dict:
        from apps.cmdb.models.collect_model import CollectModels

        tasks = CollectModels.objects.filter(
            data_cleanup_strategy=DataCleanupStrategy.AFTER_EXPIRATION,
            expire_days__gte=EXPIRE_DAYS_MIN,
            expire_days__lte=EXPIRE_DAYS_MAX,
        )
        results = []
        total_deleted = 0
        total_failed = 0
        delete_ids = []
        processed = 0
        for task in tasks.iterator():
            processed += 1
            try:
                result = DataCleanupService.cleanup_expired_instances(task)
            except Exception as exc:
                logger.error(
                    "[DataCleanup] task cleanup failed task_id=%s failed_stage=cleanup_expired_instances error_type=%s",
                    task.id,
                    type(exc).__name__,
                    exc_info=safe_exception_info(exc),
                )
                result = {"task_id": task.id, "deleted_count": 0, "failed_count": 1, "delete_ids": [], "skipped": False}
            results.append(result)
            total_deleted += result.get("deleted_count") or 0
            total_failed += result.get("failed_count") or 0
            delete_ids.extend(result.get("delete_ids") or [])
        logger.info(
            "[DataCleanup] daily cleanup finished tasks_processed=%s total_deleted=%s total_failed=%s",
            processed,
            total_deleted,
            total_failed,
        )
        return {
            "tasks_processed": processed,
            "total_deleted": total_deleted,
            "total_failed": total_failed,
            "results": results,
            "delete_ids": delete_ids,
        }


def _expiration_enabled(task) -> bool:
    if getattr(task, "data_cleanup_strategy", None) != DataCleanupStrategy.AFTER_EXPIRATION:
        return False
    try:
        days = int(task.expire_days)
    except (TypeError, ValueError):
        return False
    return EXPIRE_DAYS_MIN <= days <= EXPIRE_DAYS_MAX


def _cleanup_expired_pc(task) -> dict:
    from apps.cmdb.services.pc_discovery import cleanup_expired_pc_software

    observed = timezone.now()
    threshold = observed - timedelta(days=int(task.expire_days))
    result = cleanup_expired_pc_software(task, threshold, threshold.isoformat())
    deleted_ids = list(result.get("deleted_ids") or [])
    _schedule_deleted_models(["pc_software"] if deleted_ids else [])
    return {
        "task_id": task.id,
        "deleted_count": result.get("deleted_count", 0),
        "failed_count": result.get("failed_count", 0),
        "delete_ids": deleted_ids,
        "skipped": False,
    }


def _cleanup_owned_instances(task) -> dict:
    observed = timezone.now().isoformat()
    targets = [item for item in (getattr(task, "instances", None) or []) if isinstance(item, dict)]
    deleted = []
    failed = 0
    with GraphClient() as ag:
        for row in _query_owned_instances(ag, task.id):
            if str(row.get("collect_task")) != str(task.id):
                continue
            if is_collection_target(row, targets):
                continue
            if not cleanup_due(DataCleanupStrategy.AFTER_EXPIRATION, row.get("collect_time"), observed, int(task.expire_days)):
                continue
            if not row.get("model_id"):
                failed += 1
                continue
            try:
                removed = ag.delete_entity_if_unchanged(INSTANCE, row)
            except Exception as exc:
                failed += 1
                logger.warning(
                    "[DataCleanup] instance delete failed task_id=%s inst_id=%s failed_stage=conditional_delete error_type=%s",
                    task.id,
                    row.get("_id"),
                    type(exc).__name__,
                )
                continue
            if removed:
                deleted.append(row)
            else:
                failed += 1
    _write_expiration_audit(task, deleted)
    _schedule_deleted_models([row.get("model_id") for row in deleted])
    if failed:
        logger.warning(
            "[DataCleanup] expired instances kept task_id=%s failed_count=%s failed_stage=conditional_delete",
            task.id,
            failed,
        )
    return {
        "task_id": task.id,
        "deleted_count": len(deleted),
        "failed_count": failed,
        "delete_ids": [row["_id"] for row in deleted],
        "skipped": False,
    }


def _query_owned_instances(ag, task_id):
    found = {}
    for field_type, value in (("int=", int(task_id)), ("str=", str(task_id))):
        cursor = None
        while True:
            params = [{"field": "collect_task", "type": field_type, "value": value}]
            if cursor is not None:
                params.append({"field": "id", "type": "id>", "value": cursor})
            rows, _ = ag.query_entity(
                INSTANCE,
                params,
                page={"skip": 0, "limit": _PAGE_SIZE},
                fields=list(_OWNED_FIELDS),
                include_count=False,
            )
            rows = rows or []
            for row in rows:
                if isinstance(row, dict) and row.get("_id") is not None:
                    found[row["_id"]] = row
            if len(rows) < _PAGE_SIZE:
                break
            next_cursor = rows[-1].get("_id") if isinstance(rows[-1], dict) else None
            if next_cursor is None or (cursor is not None and next_cursor <= cursor):
                break
            cursor = next_cursor
    return list(found.values())


def _write_expiration_audit(task, deleted) -> None:
    if not deleted:
        return
    from apps.cmdb.constants.constants import OPERATOR_INSTANCE
    from apps.cmdb.models.change_record import COLLECT_AUTOMATION_CHANGE, DELETE_INST
    from apps.cmdb.utils.change_record import batch_create_change_record

    task_name = str(getattr(task, "name", "") or "")
    records = []
    for entity in deleted:
        inst_name = entity.get("inst_name") or entity.get("_id")
        records.append(
            {
                "inst_id": entity["_id"],
                "model_id": entity.get("model_id"),
                "before_data": entity,
                "model_object": OPERATOR_INSTANCE,
                "message": f"过期删除清理实例. 任务:{task_name} 模型:{entity.get('model_id')} 实例:{inst_name}",
            }
        )
    try:
        batch_create_change_record(
            INSTANCE,
            DELETE_INST,
            records,
            operator="system",
            scenario=COLLECT_AUTOMATION_CHANGE,
        )
    except Exception as exc:
        logger.error(
            "[DataCleanup] delete audit failed task_id=%s failed_stage=write_audit error_type=%s deleted_count=%s",
            getattr(task, "id", None),
            type(exc).__name__,
            len(deleted),
            exc_info=safe_exception_info(exc),
        )


def _schedule_deleted_models(model_ids) -> None:
    if not model_ids:
        return
    from apps.cmdb.services.auto_relation_reconcile import schedule_incoming_rule_full_sync_by_model_ids

    try:
        schedule_incoming_rule_full_sync_by_model_ids(model_ids)
    except Exception as exc:
        logger.error(
            "[DataCleanup] relation reschedule failed failed_stage=schedule_auto_relation error_type=%s",
            type(exc).__name__,
            exc_info=safe_exception_info(exc),
        )
