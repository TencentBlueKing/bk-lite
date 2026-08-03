from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import monitor_logger as logger
from apps.monitor.models import (
    CollectConfig,
    MonitorAlert,
    MonitorInstance,
    MonitorObjectOrganizationRule,
    MonitorPolicy,
    PolicyInstanceBaseline,
)
from apps.monitor.services.alert_lifecycle_notify import AlertLifecycleNotifier
from apps.monitor.services.flow_onboarding import FlowOnboardingService
from apps.monitor.services.policy_source_cleanup import cleanup_policy_sources
from apps.rpc.node_mgmt import NodeMgmt


@dataclass(frozen=True)
class RemovalResult:
    removed_ids: tuple[str, ...]
    missing_ids: tuple[str, ...]
    cleaned_policy_ids: tuple[int, ...]
    disabled_policy_ids: tuple[int, ...]
    closed_alert_count: int = 0


class MonitorInstanceRemovalService:
    MAX_BATCH_SIZE = 500
    ALERT_BATCH_SIZE = 500

    @classmethod
    def remove(
        cls,
        instance_ids: Iterable[str],
        *,
        operator: str = "system",
        reason: str = "instance_deleted",
    ) -> RemovalResult:
        normalized_ids = cls._normalize_ids(instance_ids)
        if not normalized_ids:
            return RemovalResult((), (), (), ())
        if len(normalized_ids) > cls.MAX_BATCH_SIZE:
            raise BaseAppException(f"单次最多删除 {cls.MAX_BATCH_SIZE} 个监控实例")

        try:
            with transaction.atomic():
                instances = list(
                    MonitorInstance.objects.select_for_update()
                    .filter(id__in=normalized_ids)
                    .only("id", "cloud_region_id", "enabled_protocols", "monitor_object__name")
                    .select_related("monitor_object")
                    .order_by("id")
                )
                existing_ids = {str(instance.id) for instance in instances}
                removed_ids = tuple(instance_id for instance_id in normalized_ids if instance_id in existing_ids)
                missing_ids = tuple(instance_id for instance_id in normalized_ids if instance_id not in existing_ids)

                config_rows = CollectConfig.objects.filter(monitor_instance_id__in=removed_ids).values_list("id", "is_child")
                child_config_ids = []
                base_config_ids = []
                for config_id, is_child in config_rows:
                    (child_config_ids if is_child else base_config_ids).append(config_id)

                if child_config_ids or base_config_ids:
                    node_mgmt = NodeMgmt()
                    if child_config_ids:
                        node_mgmt.delete_child_configs(child_config_ids)
                    if base_config_ids:
                        node_mgmt.delete_configs(base_config_ids)

                closed_alert_count, closed_at = cls._close_active_alerts(
                    removed_ids,
                    operator=operator,
                    reason=reason,
                )
                if closed_alert_count:
                    transaction.on_commit(
                        lambda ids=removed_ids, end_time=closed_at: cls._notify_closed_alerts(
                            ids,
                            closed_at=end_time,
                            operator=operator,
                            reason=reason,
                        )
                    )
                PolicyInstanceBaseline.objects.filter(
                    monitor_instance_id__in=removed_ids
                ).delete()
                cleanup_result = cleanup_policy_sources(removed_ids)
                MonitorObjectOrganizationRule.objects.filter(monitor_instance_id__in=removed_ids).delete()

                refresh_region_ids = list(
                    dict.fromkeys(
                        instance.cloud_region_id
                        for instance in instances
                        if instance.cloud_region_id is not None
                        and instance.enabled_protocols
                        and instance.monitor_object.name in FlowOnboardingService.SUPPORTED_MONITOR_OBJECT_NAMES
                    )
                )
                MonitorInstance.objects.filter(id__in=removed_ids).delete()
                FlowOnboardingService._schedule_region_refresh(*refresh_region_ids)

            logger.info(f"物理删除监控实例成功: {list(removed_ids)}")
            return RemovalResult(
                removed_ids=removed_ids,
                missing_ids=missing_ids,
                cleaned_policy_ids=tuple(cleanup_result["policy_ids"]),
                disabled_policy_ids=tuple(cleanup_result["disabled_policy_ids"]),
                closed_alert_count=closed_alert_count,
            )
        except Exception as exc:
            logger.error(f"物理删除监控实例失败: {normalized_ids}", exc_info=True)
            raise BaseAppException("删除监控实例失败，请稍后重试") from exc

    @classmethod
    def _close_active_alerts(
        cls,
        instance_ids,
        *,
        operator: str,
        reason: str,
    ) -> tuple[int, datetime | None]:
        if not instance_ids:
            return 0, None

        closed_count = 0
        last_id = 0
        closed_at = timezone.now()
        while True:
            alerts = list(
                MonitorAlert.objects.select_for_update()
                .filter(
                    monitor_instance_id__in=instance_ids,
                    status="new",
                    id__gt=last_id,
                )
                .order_by("id")[: cls.ALERT_BATCH_SIZE]
            )
            if not alerts:
                break

            operation_log = {
                "action": "closed",
                "reason": reason,
                "operator": operator,
                "time": closed_at.isoformat(),
            }
            for alert in alerts:
                alert.status = "closed"
                alert.end_event_time = closed_at
                alert.operator = operator
                alert.operation_logs = (alert.operation_logs or []) + [operation_log]
                alert.alert_center_notified = False

            MonitorAlert.objects.bulk_update(
                alerts,
                fields=[
                    "status",
                    "end_event_time",
                    "operator",
                    "operation_logs",
                    "alert_center_notified",
                ],
                batch_size=cls.ALERT_BATCH_SIZE,
            )
            closed_count += len(alerts)
            last_id = alerts[-1].id

        return closed_count, closed_at

    @classmethod
    def _notify_closed_alerts(cls, instance_ids, *, closed_at, operator: str, reason: str) -> None:
        try:
            last_id = 0
            while True:
                alerts = list(
                    MonitorAlert.objects.filter(
                        monitor_instance_id__in=instance_ids,
                        status="closed",
                        end_event_time=closed_at,
                        id__gt=last_id,
                    ).order_by("id")[: cls.ALERT_BATCH_SIZE]
                )
                if not alerts:
                    break

                alerts_by_policy = defaultdict(list)
                for alert in alerts:
                    alerts_by_policy[alert.policy_id].append(alert)
                policies = MonitorPolicy.objects.in_bulk(alerts_by_policy)
                for policy_id, policy_alerts in alerts_by_policy.items():
                    AlertLifecycleNotifier(policies.get(policy_id)).notify_alerts(
                        policy_alerts,
                        action="closed",
                        operator=operator,
                        reason=reason,
                    )
                last_id = alerts[-1].id
        except Exception:
            logger.exception(
                "实例移除后的告警关闭通知失败，等待告警中心补偿: instance_count=%s, reason=%s",
                len(instance_ids),
                reason,
            )

    @staticmethod
    def _normalize_ids(instance_ids: Iterable[str]) -> tuple[str, ...]:
        normalized_ids = []
        seen_ids = set()
        for value in instance_ids or []:
            if value in (None, ""):
                continue
            instance_id = str(value)
            if instance_id in seen_ids:
                continue
            seen_ids.add(instance_id)
            normalized_ids.append(instance_id)
        return tuple(normalized_ids)
