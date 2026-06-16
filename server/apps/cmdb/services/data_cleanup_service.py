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
            logger.warning("[DataCleanup] 解析 collect_time 失败，跳过该实例 collect_time=%s", collect_time_str)
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
            logger.info("[DataCleanup] 任务未配置过期天数，跳过清理 task_id=%s, expire_days=%s", task.id, task.expire_days)
            return {"task_id": task.id, "deleted_count": 0, "skipped": True}

        threshold_iso = cls.get_expire_threshold(task.expire_days)
        threshold_dt = datetime.fromisoformat(threshold_iso)
        logger.info("[DataCleanup] 开始清理过期实例 task_id=%s, collect_time < %s", task.id, threshold_iso)

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
                    logger.info("[DataCleanup] 批量删除过期实例成功 task_id=%s, deleted_count=%s", task.id, deleted_count)
                except Exception as e:
                    logger.error(
                        "[DataCleanup] 批量删除过期实例失败 task_id=%s, expired_count=%s, error=%s",
                        task.id,
                        len(expired_ids),
                        e,
                        exc_info=True,
                    )
                    return {
                        "task_id": task.id,
                        "model_id": task.model_id,
                        "deleted_count": 0,
                        "expired_ids":expired_ids,
                        "failed_count": len(expired_ids),
                        "threshold": threshold_iso,
                        "error": str(e),
                    }

        logger.info("[DataCleanup] 过期实例清理完成 task_id=%s, deleted_count=%s", task.id, deleted_count)
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

        logger.info("[DataCleanup] 开始每日过期数据清理，待处理任务数 task_count=%s", tasks.count())

        for task in tasks:
            try:
                result = cls.cleanup_expired_instances(task)
                results.append(result)
                total_deleted += result.get("deleted_count", 0)
                total_failed += result.get("failed_count", 0)
                delete_ids.extend(result.get("expired_ids", []))
            except Exception as e:
                logger.error("[DataCleanup] 清理任务过期数据出错 task_id=%s, error=%s", task.id, e, exc_info=True)
                results.append({"task_id": task.id, "error": str(e)})

        summary = {
            "tasks_processed": len(results),
            "total_deleted": total_deleted,
            "total_failed": total_failed,
            "results": results,
            "delete_ids":delete_ids
        }

        logger.info(
            "[DataCleanup] 每日过期数据清理完成 tasks_processed=%s, total_deleted=%s, total_failed=%s, delete_ids=%s",
            summary["tasks_processed"],
            total_deleted,
            total_failed,
            delete_ids,
        )

        return summary
