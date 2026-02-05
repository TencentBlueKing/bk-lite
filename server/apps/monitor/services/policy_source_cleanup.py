import logging
from typing import Iterable

from django.db import transaction

from apps.monitor.models import MonitorPolicy

logger = logging.getLogger("apps.monitor")

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

        queryset = MonitorPolicy.objects.filter(source__type="instance").only(
            "id", "source", "enable"
        )

        if not queryset.exists():
            return result

        updates = []

        for policy in queryset.iterator(chunk_size=BATCH_SIZE):
            source = policy.source
            if not source or source.get("type") != "instance":
                continue

            old_values = set(source.get("values", []))
            new_values = old_values - deleted_set

            if old_values == new_values:
                continue

            policy.source = {
                "type": "instance",
                "values": list(new_values),
            }

            if not new_values:
                policy.enable = False
                result["disabled_count"] += 1
                result["disabled_policy_ids"].append(policy.id)

            updates.append(policy)
            result["policy_ids"].append(policy.id)

            if len(updates) >= BATCH_SIZE:
                PolicySourceCleanupService._flush_updates(updates)
                updates = []

        if updates:
            PolicySourceCleanupService._flush_updates(updates)

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

        return result

    @staticmethod
    def _flush_updates(updates: list):
        if not updates:
            return
        with transaction.atomic():
            MonitorPolicy.objects.bulk_update(updates, ["source", "enable"])


def cleanup_policy_sources(instance_ids: Iterable[str]) -> dict:
    return PolicySourceCleanupService.cleanup_by_instance_ids(instance_ids)
