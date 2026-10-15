"""旧每日清理入口：历史 Beat/排队消息只返回跳过，不再绕过采集快照删除。"""
from datetime import timedelta

from django.utils import timezone

from apps.cmdb.collection.cleanup import parse_collect_time


class DataCleanupService:
    parse_collect_time = staticmethod(parse_collect_time)

    @staticmethod
    def get_expire_threshold(expire_days: int) -> str:
        return (timezone.now() - timedelta(days=expire_days)).isoformat()

    @staticmethod
    def cleanup_expired_instances(task) -> dict:
        return {"task_id": task.id, "deleted_count": 0, "skipped": True}

    @staticmethod
    def run_daily_cleanup() -> dict:
        # 保留任务入口以消费升级前已排队的 Celery 消息。
        # 过期删除已统一到完整采集快照对账，不重放旧快照或只凭时间删资产。
        return {"tasks_processed": 0, "total_deleted": 0, "total_failed": 0, "results": [], "delete_ids": []}
