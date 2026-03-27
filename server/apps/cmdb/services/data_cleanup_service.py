from datetime import datetime, timedelta
from typing import Optional

import pytz
from django.utils import timezone

from apps.cmdb.constants.constants import INSTANCE, DataCleanupStrategy
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.cmdb.models.collect_model import CollectModels
from apps.core.logger import cmdb_logger as logger


class DataCleanupService:
    @staticmethod
    def parse_collect_time(collect_time_str: str) -> Optional[datetime]:
        if not collect_time_str:
            return None
        try:
            return datetime.fromisoformat(collect_time_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            logger.warning(f"Failed to parse collect_time: {collect_time_str}")
            return None

    @staticmethod
    def get_expire_threshold(expire_days: int) -> str:
        current_time = timezone.now()
        threshold = current_time - timedelta(days=expire_days)
        threshold_utc = threshold.astimezone(pytz.UTC)
        return threshold_utc.isoformat()

    @classmethod
    def cleanup_expired_instances(cls, task: CollectModels) -> dict:
        if task.expire_days <= 0:
            logger.info(f"Task {task.id} has expire_days={task.expire_days}, skipping cleanup")
            return {"task_id": task.id, "deleted_count": 0, "skipped": True}

        threshold_iso = cls.get_expire_threshold(task.expire_days)
        threshold_dt = datetime.fromisoformat(threshold_iso)
        logger.info(f"Task {task.id}: cleaning instances with collect_time < {threshold_iso}")

        with GraphClient() as ag:
            params = [
                {"field": "collect_task", "type": "int=", "value": task.id},
                {"field": "model_id", "type": "str=", "value": task.model_id},
            ]
            instances, _ = ag.query_entity(INSTANCE, params)

            expired_ids = []
            for instance in instances:
                collect_time_str = instance.get("collect_time")
                if not collect_time_str:
                    continue

                collect_time = cls.parse_collect_time(collect_time_str)
                if collect_time and collect_time < threshold_dt:
                    expired_ids.append(instance["_id"])

            deleted_count = 0
            if expired_ids:
                try:
                    ag.batch_delete_entity(INSTANCE, expired_ids)
                    deleted_count = len(expired_ids)
                    logger.info(f"Task {task.id}: batch deleted {deleted_count} expired instances")
                except Exception as e:
                    logger.error(f"Task {task.id}: batch delete failed: {e}")
                    return {
                        "task_id": task.id,
                        "model_id": task.model_id,
                        "deleted_count": 0,
                        "expired_ids":expired_ids,
                        "failed_count": len(expired_ids),
                        "threshold": threshold_iso,
                        "error": str(e),
                    }

        logger.info(f"Task {task.id}: cleanup completed, deleted={deleted_count}")
        return {
            "task_id": task.id,
            "model_id": task.model_id,
            "deleted_count": deleted_count,
            "threshold": threshold_iso,
        }

    @classmethod
    def run_daily_cleanup(cls) -> dict:
        tasks = CollectModels.objects.filter(
            data_cleanup_strategy=DataCleanupStrategy.AFTER_EXPIRATION,
            expire_days__gt=0,
        )

        results = []
        total_deleted = 0
        total_failed = 0
        delete_ids = []

        logger.info(f"Starting daily data cleanup, found {tasks.count()} tasks to process")

        for task in tasks:
            try:
                result = cls.cleanup_expired_instances(task)
                results.append(result)
                total_deleted += result.get("deleted_count", 0)
                total_failed += result.get("failed_count", 0)
                delete_ids.extend(result.get("expired_ids", []))
            except Exception as e:
                logger.error(f"Error cleaning up task {task.id}: {e}")
                results.append({"task_id": task.id, "error": str(e)})

        summary = {
            "tasks_processed": len(results),
            "total_deleted": total_deleted,
            "total_failed": total_failed,
            "results": results,
            "delete_ids":delete_ids
        }

        logger.info(f"Daily cleanup completed: {summary['tasks_processed']} tasks, {total_deleted} instances deleted, {total_failed} failed, delete_ids={delete_ids}")

        return summary
