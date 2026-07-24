from django.db import transaction
from django.db.models import F

from apps.core.logger import celery_logger as logger
from apps.monitor.models import MonitorInstance, MonitorObject


class AutoDiscoveryLifecycleService:
    """将一次成功的 VM 发现结果应用为实例生命周期状态。"""

    EXPECTED_INTERVAL_SECONDS = 600

    @classmethod
    def reconcile(cls, metrics_instance_map, successful_monitor_object_ids, observed_at):
        # 延迟导入，避免 Celery task → 生命周期 → 删除服务 → 采集服务 → task 的启动期环。
        from apps.monitor.services.monitor_instance_removal import MonitorInstanceRemovalService

        observed_ids_by_object = {}
        for instance_id, item in metrics_instance_map.items():
            observed_ids_by_object.setdefault(item["monitor_object_id"], set()).add(instance_id)

        removal_ids = []
        object_ids = MonitorObject.objects.filter(
            id__in=successful_monitor_object_ids
        ).values_list("id", flat=True)
        for monitor_object_id in object_ids:
            with transaction.atomic():
                monitor_object = MonitorObject.objects.select_for_update().get(
                    pk=monitor_object_id
                )
                policy_owner = monitor_object
                if monitor_object.parent_id is not None:
                    policy_owner = MonitorObject.objects.select_for_update().get(
                        pk=monitor_object.parent_id
                    )
                previous_success_at = monitor_object.last_discovery_success_at
                interval_start = previous_success_at
                if (
                    policy_owner.cleanup_policy_effective_at is not None
                    and (
                        interval_start is None
                        or policy_owner.cleanup_policy_effective_at > interval_start
                    )
                ):
                    interval_start = policy_owner.cleanup_policy_effective_at
                elapsed_seconds = 0
                if interval_start is not None:
                    elapsed_seconds = max(
                        0,
                        min(
                            int((observed_at - interval_start).total_seconds()),
                            cls.EXPECTED_INTERVAL_SECONDS,
                        ),
                    )
                monitor_object.last_discovery_success_at = observed_at
                monitor_object.save(
                    update_fields=["last_discovery_success_at", "updated_at"]
                )

                observed_ids = observed_ids_by_object.get(monitor_object.id, set())
                instance_qs = MonitorInstance.objects.filter(
                    monitor_object_id=monitor_object.id,
                    auto=True,
                    is_deleted=False,
                )
                if observed_ids:
                    instance_qs.filter(id__in=observed_ids).update(
                        is_active=True,
                        last_seen_at=observed_at,
                        missing_duration_seconds=0,
                    )

                missing_qs = instance_qs.exclude(id__in=observed_ids)
                missing_qs.update(is_active=False)
                if policy_owner.cleanup_policy != MonitorObject.CLEANUP_POLICY_TIMEOUT:
                    missing_qs.update(missing_duration_seconds=0)
                    continue
                if elapsed_seconds:
                    missing_qs.update(
                        missing_duration_seconds=F("missing_duration_seconds") + elapsed_seconds
                    )
                threshold_seconds = policy_owner.cleanup_timeout_days * 24 * 60 * 60
                removal_ids.extend(
                    missing_qs.filter(missing_duration_seconds__gte=threshold_seconds).values_list(
                        "id", flat=True
                    )
                )

        for offset in range(0, len(removal_ids), MonitorInstanceRemovalService.MAX_BATCH_SIZE):
            batch = removal_ids[offset:offset + MonitorInstanceRemovalService.MAX_BATCH_SIZE]
            MonitorInstanceRemovalService.remove(batch)
        logger.info(
            "监控实例自动发现生命周期同步完成: 成功对象数=%s, 发现实例数=%s, 清理实例数=%s",
            len(successful_monitor_object_ids),
            len(metrics_instance_map),
            len(removal_ids),
        )
