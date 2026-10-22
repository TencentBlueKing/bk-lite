from typing import Iterable

from django.db import transaction

from apps.core.logger import monitor_logger as logger
from apps.monitor.models import MonitorPolicy

BATCH_SIZE = 500


class PolicySourceCleanupService:
    @staticmethod
    def cleanup_by_instance_ids(instance_ids: Iterable[str]) -> dict:
        if not instance_ids:
            return {
                "cleaned_count": 0,
                "disabled_count": 0,
                "policy_ids": [],
                "disabled_policy_ids": [],
            }

        deleted_set = set(instance_ids)
        result = {
            "cleaned_count": 0,
            "disabled_count": 0,
            "policy_ids": [],
            "disabled_policy_ids": [],
        }

        queryset = MonitorPolicy.objects.filter(source__type="instance").only("id", "source")

        if not queryset.exists():
            return result

        # 扫描只圈定候选。写回前锁行重读，按当前 values 删除，避免旧快照覆盖并发保存。
        candidate_ids = []
        for policy in queryset.iterator(chunk_size=BATCH_SIZE):
            source = policy.source if isinstance(policy.source, dict) else None
            if not source or source.get("type") != "instance":
                continue
            values = source.get("values") or []
            if any(value in deleted_set for value in values):
                candidate_ids.append(policy.id)

        for start in range(0, len(candidate_ids), BATCH_SIZE):
            PolicySourceCleanupService._apply_locked_updates(
                candidate_ids[start : start + BATCH_SIZE],
                deleted_set,
                result,
            )

        result["cleaned_count"] = len(result["policy_ids"])

        if result["cleaned_count"] > 0:
            logger.info(
                f"清理策略实例引用: 共 {result['cleaned_count']} 个策略, "
                f"其中 {result['disabled_count']} 个因实例为空被禁用, "
                f"删除的实例数: {len(deleted_set)}"
            )

        if result["disabled_policy_ids"]:
            logger.warning(
                f"以下策略因监控实例全部被删除而自动禁用: {result['disabled_policy_ids']}"
            )
            PolicySourceCleanupService._disable_periodic_tasks(result["disabled_policy_ids"])

        return result

    @staticmethod
    def _disable_periodic_tasks(policy_ids: list):
        """自动禁用的策略同步停掉 Beat 派发，避免每个周期空投一次扫描任务。"""
        from django_celery_beat.models import PeriodicTask

        for start in range(0, len(policy_ids), BATCH_SIZE):
            names = [
                f"scan_policy_task_{policy_id}"
                for policy_id in policy_ids[start : start + BATCH_SIZE]
            ]
            PeriodicTask.objects.filter(name__in=names).update(enabled=False)

    @staticmethod
    def _apply_locked_updates(policy_ids: list, deleted_set: set, result: dict):
        with transaction.atomic():
            locked_policies = list(
                MonitorPolicy.objects.select_for_update()
                .filter(id__in=policy_ids)
                .only("id", "source", "enable")
                .order_by("id")
            )
            updates = []
            for policy in locked_policies:
                source = policy.source if isinstance(policy.source, dict) else {}
                if source.get("type") != "instance":
                    continue
                old_values = list(source.get("values") or [])
                new_values = [value for value in old_values if value not in deleted_set]
                if new_values == old_values:
                    continue

                policy.source = {
                    "type": "instance",
                    "values": new_values,
                }
                if not new_values:
                    policy.enable = False
                    result["disabled_count"] += 1
                    result["disabled_policy_ids"].append(policy.id)

                updates.append(policy)
                result["policy_ids"].append(policy.id)

            PolicySourceCleanupService._flush_updates(updates)

    @staticmethod
    def _flush_updates(updates: list):
        if not updates:
            return
        with transaction.atomic():
            MonitorPolicy.objects.bulk_update(updates, ["source", "enable"])


def cleanup_policy_sources(instance_ids: Iterable[str]) -> dict:
    return PolicySourceCleanupService.cleanup_by_instance_ids(instance_ids)
